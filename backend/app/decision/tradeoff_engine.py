"""Trade-off Engine (Sprint 7.5) — generates side-by-side comparisons
showing which candidate wins on each dimension and by how much.

Every comparison is grounded in **actual measured metrics**, not invented by an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.decision.candidate import CandidateSolution
from app.decision.ranking_engine import RankedCandidate, RankingResult


@dataclass
class DimensionComparison:
    """Which candidate leads on a single dimension, and by how much."""

    dimension: str
    leader_title: str
    leader_score: float
    runner_up_title: str
    runner_up_score: float
    gap: float  # absolute difference
    gap_pct: float  # percentage difference relative to runner-up


@dataclass
class TradeoffReport:
    """Complete trade-off analysis between candidates."""

    comparisons: list[DimensionComparison] = field(default_factory=list)
    text: str = ""

    def to_dict(self) -> dict:
        return {
            "comparisons": [
                {
                    "dimension": c.dimension,
                    "leader": c.leader_title,
                    "leader_score": c.leader_score,
                    "runner_up": c.runner_up_title,
                    "runner_up_score": c.runner_up_score,
                    "gap": c.gap,
                    "gap_pct": round(c.gap_pct, 1),
                }
                for c in self.comparisons
            ],
            "summary": self.text,
        }


class TradeoffEngine:
    """Compares candidates side-by-side on each quality dimension.

    Usage::

        engine = TradeoffEngine()
        report = engine.analyze(ranking_result)
        print(report.text)
    """

    def analyze(self, ranking_result: RankingResult) -> TradeoffReport:
        """Build a side-by-side comparison from a ranking result.

        For each dimension, finds which candidate leads and by how much.
        """
        ranked = ranking_result.ranked
        if len(ranked) < 2:
            return TradeoffReport(
                text="Only one candidate — no trade-offs to compare."
            )

        # Collect all dimension names across all candidates
        all_dims: set[str] = set()
        for rc in ranked:
            all_dims.update(rc.candidate.dimension_scores.keys())

        comparisons: list[DimensionComparison] = []

        for dim in sorted(all_dims):
            # Find which candidate leads on this dimension
            scored: list[tuple[float, RankedCandidate]] = []
            for rc in ranked:
                score = rc.candidate.dimension_scores.get(dim, 0)
                scored.append((score, rc))
            scored.sort(key=lambda x: x[0], reverse=True)

            leader_score, leader = scored[0]
            runner_up_score, runner_up = scored[1]
            gap = round(leader_score - runner_up_score, 1)
            gap_pct = round((gap / max(runner_up_score, 0.1)) * 100, 1)

            comparisons.append(DimensionComparison(
                dimension=dim,
                leader_title=leader.candidate.title,
                leader_score=leader_score,
                runner_up_title=runner_up.candidate.title,
                runner_up_score=runner_up_score,
                gap=gap,
                gap_pct=gap_pct,
            ))

        # ── Build human-readable text report ───────────────────────
        text = self._build_text(comparisons, ranking_result)

        return TradeoffReport(comparisons=comparisons, text=text)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_text(
        self,
        comparisons: list[DimensionComparison],
        ranking: RankingResult,
    ) -> str:
        """Generate the side-by-side comparison text."""
        lines: list[str] = []
        sep = "-" * 50

        lines.append(sep)
        lines.append("  TRADE-OFF ANALYSIS")
        lines.append(sep)
        lines.append("")

        if ranking.winner:
            lines.append(f"  Winner:  {ranking.winner.candidate.title}")
            lines.append(f"  Score:   {ranking.winner.weighted_score}")
            lines.append("")

        lines.append(f"  Priority: {ranking.priority_label}")
        lines.append("")

        # Per-dimension breakdown
        lines.append("  ── Dimension Leaders ──")
        lines.append("")

        for comp in comparisons:
            # Arrow indicator: ▲ for the leader, ▼ for behind
            gain_sym = "▲" if comp.gap >= 0 else "▼"
            lines.append(
                f"  {comp.dimension:18s}  "
                f"{comp.leader_title[:35]:35s}  "
                f"{gain_sym} {comp.leader_score:.0f}  "
                f"(−{comp.runner_up_score:.0f} for {comp.runner_up_title[:20]})"
            )

        lines.append("")
        lines.append("  ── Detailed Comparison ──")
        lines.append("")

        for comp in comparisons:
            if comp.gap >= 5:
                direction = "better" if comp.leader_score > comp.runner_up_score else "worse"
                lines.append(
                    f"  • {comp.leader_title[:30]} is **{comp.gap_pct:.0f}%** {direction} "
                    f"on {comp.dimension} "
                    f"({comp.leader_score:.0f} vs {comp.runner_up_score:.0f})"
                )

        # Strengths and weaknesses per candidate
        lines.append("")
        lines.append("  ── Candidate Profiles ──")
        lines.append("")

        for rc in ranking.ranked:
            c = rc.candidate
            lines.append(f"  [{rc.rank}] {c.title}")
            lines.append(f"      Score:  {rc.weighted_score}  |  "
                         f"Files: {len(c.files_modified)}  |  "
                         f"Est: {c.estimated_runtime}")

            # Best and worst dimensions
            dims = c.dimension_scores or {}
            if dims:
                best = max(dims, key=dims.get)
                worst = min(dims, key=dims.get)
                lines.append(f"      Best:   {best} ({dims[best]:.0f})")
                lines.append(f"      Worst:  {worst} ({dims[worst]:.0f})")

            if rc.rationale:
                lines.append(f"      Note:   {rc.rationale}")
            lines.append("")

        if ranking.spread:
            lines.append(f"  Spread between 1st and 2nd: {ranking.spread} points")
            if ranking.spread < 5:
                lines.append("  ⇒ Very close — either choice is defensible.")
            elif ranking.spread < 15:
                lines.append("  ⇒ Moderate gap — the winner has a clear edge.")
            else:
                lines.append("  ⇒ Decisive win — the leader dominates.")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)
