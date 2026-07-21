"""Ranking Engine (Sprint 7.4) — ranks candidate solutions by weighted scores.

Users can specify priorities (e.g. "optimize for speed") which overrides
the default weights and changes the ranking automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.decision.candidate import CandidateSolution


# ── Default priority weights ──────────────────────────────────────
# These represent a balanced, neutral stance.
DEFAULT_PRIORITY_WEIGHTS: dict[str, float] = {
    "complexity": 0.20,
    "maintainability": 0.25,
    "readability": 0.20,
    "architecture": 0.20,
    "documentation": 0.10,
    "performance": 0.05,
}

# ── Presets for common user preferences ───────────────────────────
# Each preset maps a dimension to a boosted weight.
# Dimensions not mentioned keep their proportional share of remaining weight.
PRIORITY_PRESETS: dict[str, dict[str, float]] = {
    "performance": {
        "performance": 0.30,
        "complexity": 0.15,
        "maintainability": 0.15,
        "readability": 0.10,
        "architecture": 0.15,
        "documentation": 0.05,
    },
    "maintainability": {
        "maintainability": 0.35,
        "architecture": 0.20,
        "readability": 0.15,
        "complexity": 0.15,
        "documentation": 0.10,
        "performance": 0.05,
    },
    "simplicity": {
        "complexity": 0.30,
        "readability": 0.25,
        "maintainability": 0.20,
        "architecture": 0.10,
        "documentation": 0.10,
        "performance": 0.05,
    },
    "security": {
        "architecture": 0.30,
        "complexity": 0.20,
        "maintainability": 0.15,
        "readability": 0.10,
        "documentation": 0.15,
        "performance": 0.10,
    },
}


@dataclass
class RankedCandidate:
    """A candidate with its ranking position and explanation."""

    candidate: CandidateSolution
    rank: int
    weighted_score: float
    breakdown: dict[str, float]  # dimension_name → contribution to final score
    rationale: str = ""


@dataclass
class RankingResult:
    """Complete ranking output with metadata."""

    ranked: list[RankedCandidate]
    weights_used: dict[str, float]
    priority_label: str = "balanced"
    spread: float = 0.0  # difference between 1st and 2nd

    @property
    def winner(self) -> Optional[RankedCandidate]:
        return self.ranked[0] if self.ranked else None

    @property
    def runner_up(self) -> Optional[RankedCandidate]:
        return self.ranked[1] if len(self.ranked) > 1 else None

    def summary(self) -> str:
        lines: list[str] = []
        lines.append(f"Ranking (priority: {self.priority_label})")
        lines.append("-" * 40)
        for rc in self.ranked:
            lines.append(
                f"  #{rc.rank}  {rc.candidate.title[:50]:50s}  "
                f"{rc.weighted_score:5.1f}"
            )
        spread_str = f"Spread: {self.spread:.1f} pts" if self.spread else ""
        if spread_str:
            lines.append(f"\n  {spread_str}")
        return "\n".join(lines)


class RankingEngine:
    """Ranks candidates by weighted scores with user-configurable priorities.

    Usage::

        engine = RankingEngine()
        result = engine.rank(candidates, priority="performance")
        print(result.winner.candidate.title)
        print(result.summary())
    """

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self._default_weights = weights or DEFAULT_PRIORITY_WEIGHTS.copy()

    def rank(
        self,
        candidates: list[CandidateSolution],
        priority: str = "balanced",
        custom_weights: Optional[dict[str, float]] = None,
    ) -> RankingResult:
        """Rank candidates by their dimension scores.

        Args:
            candidates: List of evaluated candidates (must have dimension_scores).
            priority: One of ``"balanced"``, ``"performance"``, ``"maintainability"``,
                      ``"simplicity"``, ``"security"``, or ``"custom"``.
            custom_weights: Only used when ``priority="custom"``.

        Returns:
            A RankingResult with ranked candidates and metadata.
        """
        if not candidates:
            return RankingResult(
                ranked=[],
                weights_used=self._default_weights,
                priority_label=priority,
            )

        # ── Resolve weights ────────────────────────────────────────
        if priority == "custom" and custom_weights:
            weights = custom_weights
        elif priority in PRIORITY_PRESETS:
            weights = PRIORITY_PRESETS[priority]
        else:
            weights = self._default_weights

        weighted_candidates: list[tuple[float, CandidateSolution, dict[str, float]]] = []

        for candidate in candidates:
            dims = candidate.dimension_scores or {}

            # Compute weighted score and per-dimension breakdown
            total = 0.0
            breakdown: dict[str, float] = {}
            for dim, weight in weights.items():
                # Try the dimension name directly, then fall back
                score = dims.get(dim, 50.0)  # default 50 if missing
                contribution = score * weight
                breakdown[dim] = round(contribution, 2)
                total += contribution

            weighted_candidates.append((total, candidate, breakdown))

        # ── Sort descending by weighted score ──────────────────────
        weighted_candidates.sort(key=lambda x: x[0], reverse=True)

        ranked: list[RankedCandidate] = []
        for rank, (score, candidate, breakdown) in enumerate(weighted_candidates, 1):
            rationale = self._build_rationale(candidate, breakdown, weights, rank)
            ranked.append(RankedCandidate(
                candidate=candidate,
                rank=rank,
                weighted_score=round(score, 1),
                breakdown=breakdown,
                rationale=rationale,
            ))
            # Store rank score back on the candidate
            candidate.rank_score = round(score, 1)

        # ── Compute spread ─────────────────────────────────────────
        spread = 0.0
        if len(ranked) >= 2:
            spread = round(ranked[0].weighted_score - ranked[1].weighted_score, 1)

        logger.info(
            "RankingEngine: ranked %d candidates (priority=%s, winner=%s, spread=%.1f)",
            len(ranked),
            priority,
            ranked[0].candidate.title if ranked else "N/A",
            spread,
        )

        return RankingResult(
            ranked=ranked,
            weights_used=weights,
            priority_label=priority,
            spread=spread,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_rationale(
        candidate: CandidateSolution,
        breakdown: dict[str, float],
        weights: dict[str, float],
        rank: int,
    ) -> str:
        """Generate a short explanation of why this candidate scored as it did."""
        parts: list[str] = []

        if rank == 1:
            # Find what made it win
            best_dim = max(breakdown, key=breakdown.get)
            parts.append(f"Best in '{best_dim}' (contributed {breakdown[best_dim]:.1f} pts)")
        else:
            # Find what held it back
            dims = candidate.dimension_scores or {}
            worst_dim = min(dims, key=dims.get)
            worst_score = dims.get(worst_dim, 0)
            if worst_score < 60:
                parts.append(f"Weak in '{worst_dim}' ({worst_score:.0f}/100)")

        # Check which weight had the most impact
        top_weight = max(weights, key=weights.get)
        if weights.get(top_weight, 0) > 0.25:
            parts.append(f"'{top_weight}' weighted heavily ({weights[top_weight]:.0%})")

        return ". ".join(parts) if parts else "Standard ranking"
