"""Recommendation Engine (Sprint 7.6) — the final stage where an LLM
receives the structured ranking + trade-off data and writes a professional
engineering recommendation.

The key architectural principle: the LLM **explains** — it doesn't **invent**.
All scores, trade-offs, and metrics come from the deterministic pipeline.
The LLM only interprets them in natural language.
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.config import config, logger
from app.decision.ranking_engine import RankingResult
from app.decision.tradeoff_engine import TradeoffReport


# Prompt template that feeds structured data to the LLM
RECOMMENDATION_PROMPT = """You are EDITH's engineering recommendation system. Based on objective code analysis, write a professional recommendation.

## Ranking Results

**Priority:** {priority}
**Spread (1st vs 2nd):** {spread}

### Ranked Solutions

{ranked_table}

## Trade-off Analysis

{tradeoffs}

## Instructions

Write a concise, professional engineering recommendation. Structure it as:

1. **Recommendation** — Which solution is best and why. Reference the actual scores.
2. **Key Trade-offs** — The most important differences between the top candidates. Use numbers.
3. **Context** — When a different choice might be better (e.g., if performance is critical, choose X instead).

Rules:
- Be specific. Reference scores and metrics.
- Don't invent data. Only use what's provided above.
- If the spread is very small (< 5 pts), acknowledge that either choice is defensible.
- If one solution clearly dominates, say so plainly.
- Write in a professional, direct style — no marketing language.
- 3-5 paragraphs maximum.
"""


class RecommendationEngine:
    """Generates AI-powered recommendations from ranking + trade-off data.

    The LLM receives structured metrics and explains them — it doesn't guess.

    Usage::

        engine = RecommendationEngine()
        recommendation = engine.recommend(ranking_result, tradeoff_report)
        print(recommendation)
    """

    def __init__(self):
        self._provider = None

    def recommend(
        self,
        ranking: RankingResult,
        tradeoffs: TradeoffReport,
    ) -> str:
        """Generate a recommendation from ranking + trade-off data.

        Returns the recommendation text. If no LLM is available, falls
        back to a deterministic summary.
        """
        if not ranking.ranked:
            return "No candidates to evaluate — cannot generate a recommendation."

        # ── Try LLM first ──────────────────────────────────────────
        try:
            return self._llm_recommendation(ranking, tradeoffs)
        except Exception as e:
            logger.warning("RecommendationEngine: LLM failed (%s), using fallback", e)
            return self._fallback_recommendation(ranking, tradeoffs)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _llm_recommendation(
        self,
        ranking: RankingResult,
        tradeoffs: TradeoffReport,
    ) -> str:
        """Ask the LLM to write a recommendation from the structured data."""
        provider = self._get_provider()
        if provider is None:
            return self._fallback_recommendation(ranking, tradeoffs)

        prompt = self._build_prompt(ranking, tradeoffs)
        return provider.ask(prompt, temperature=0.3, max_tokens=1024)

    def _build_prompt(
        self,
        ranking: RankingResult,
        tradeoffs: TradeoffReport,
    ) -> str:
        """Build a prompt with structured data for the LLM."""
        # Ranked table
        rows: list[str] = []
        for rc in ranking.ranked:
            c = rc.candidate
            dims_str = ", ".join(
                f"{k}={v:.0f}" for k, v in c.dimension_scores.items()
            )
            rows.append(
                f"  #{rc.rank}  {c.title[:40]:40s}  "
                f"Score={rc.weighted_score:.1f}  "
                f"[{dims_str}]"
            )
        ranked_table = "\n".join(rows)

        # Trade-offs text
        tradeoffs_text = tradeoffs.text or "No trade-off data available."

        return RECOMMENDATION_PROMPT.format(
            priority=ranking.priority_label,
            spread=f"{ranking.spread} pts" if ranking.spread else "N/A",
            ranked_table=ranked_table,
            tradeoffs=tradeoffs_text,
        )

    # ------------------------------------------------------------------
    # Fallback (deterministic, no LLM)
    # ------------------------------------------------------------------

    def _fallback_recommendation(
        self,
        ranking: RankingResult,
        tradeoffs: TradeoffReport,
    ) -> str:
        """Generate a deterministic recommendation when no LLM is available."""
        lines: list[str] = []
        sep = "=" * 55

        lines.append(sep)
        lines.append("  EDITH RECOMMENDATION")
        lines.append(sep)
        lines.append("")

        if ranking.winner:
            w = ranking.winner
            c = w.candidate
            lines.append(f"  Recommended:  {c.title}")
            lines.append(f"  Score:        {w.weighted_score}/100")
            lines.append("")

            # Explain why it won
            dims = c.dimension_scores or {}
            if dims:
                best = max(dims, key=dims.get)
                worst = min(dims, key=dims.get)
                lines.append(
                    f"  This solution excels at '{best}' ({dims[best]:.0f}/100) "
                    f"and its weakest area is '{worst}' ({dims[worst]:.0f}/100)."
                )

            if ranking.runner_up:
                ru = ranking.runner_up
                gap = ranking.spread
                lines.append("")

                if gap < 5:
                    lines.append(
                        f"  The margin over the runner-up ({ru.candidate.title}) "
                        f"is only {gap} point{'s' if gap != 1 else ''} — "
                        "either choice is defensible."
                    )
                else:
                    lines.append(
                        f"  It leads the runner-up ({ru.candidate.title}) "
                        f"by {gap} points, a clear margin."
                    )

        if ranking.ranked:
            lines.append("")
            lines.append("  ── All Candidates ──")
            for rc in ranking.ranked:
                c = rc.candidate
                dims_str = ", ".join(
                    f"{k}={v:.0f}" for k, v in c.dimension_scores.items()
                )
                lines.append(
                    f"  #{rc.rank}  {c.title[:40]:40s}  "
                    f"{rc.weighted_score:5.1f}  |  {dims_str}"
                )

        lines.append("")
        lines.append(sep)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_provider(self):
        """Lazy-init the AI provider."""
        if self._provider is None:
            try:
                from app.main import create_provider as _create
                self._provider = _create()
            except Exception:
                try:
                    api_key = config.ai.api_key
                    if api_key:
                        from app.ai.openai_provider import OpenAIProvider
                        self._provider = OpenAIProvider()
                except Exception:
                    pass
        return self._provider
