"""Candidate solution model — represents one proposed implementation.

Every candidate is an **engineering artifact** with:
    - An identity (``candidate_id``) for cross-referencing
    - A parent problem (``parent_problem_id``) for traceability
    - Estimates (tokens, runtime, memory) for ranking
    - Scores and trade-offs populated by later pipeline stages
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Counter for auto-incrementing candidate IDs
_candidate_counter: int = 0


def _next_candidate_id() -> int:
    global _candidate_counter
    _candidate_counter += 1
    return _candidate_counter


@dataclass
class CandidateSolution:
    """One candidate solution to an engineering problem.

    Attributes
    ----------
    candidate_id : int
        Globally unique identifier for this candidate (auto-incremented).
    parent_problem_id : int
        References the EngineeringProblem.problem_id this belongs to.
    title : str
        Short human-readable title (e.g. "Decorator-based middleware").
    description : str
        Longer explanation of the approach.
    code : str
        The proposed implementation code.
    reasoning : str
        Why this approach was chosen.
    files_modified : list[str]
        Paths of files this solution touches.

    --- Estimation fields (populated by generator) ---
    estimated_tokens : int
        Rough token count of the generated solution.
    estimated_runtime : str
        Human-readable estimate (e.g. "2-3 hours", "1 day").
    estimated_memory : str
        Memory impact (e.g. "+1.2 MB").

    --- Populated by later stages ---
    review_result : dict | None
        Output of the Review Engine (Sprint 7.3).
    rank_score : float
        Weighted score from the Ranking Engine (Sprint 7.4).
    dimension_scores : dict[str, float]
        Per-dimension scores from the Ranking Engine. Keys like
        "complexity", "maintainability", "performance", etc.
    strengths : list[str]
        Trade-offs identified by the Trade-off Engine (Sprint 7.5).
    weaknesses : list[str]
        Trade-offs identified by the Trade-off Engine (Sprint 7.5).
    metadata : dict
        Arbitrary key-value store for provider-specific data.
    """

    candidate_id: int = field(default_factory=_next_candidate_id)
    parent_problem_id: int = 0

    title: str = ""
    description: str = ""
    code: str = ""
    reasoning: str = ""
    files_modified: list[str] = field(default_factory=list)

    # --- Estimates ---
    estimated_tokens: int = 0
    estimated_runtime: str = ""
    estimated_memory: str = ""

    # --- Populated by later stages ---
    review_result: Optional[dict] = None
    rank_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # Kept for backward compatibility — delegates to candidate_id
    @property
    def id(self) -> int:
        return self.candidate_id

    @property
    def has_review(self) -> bool:
        return self.review_result is not None

    @property
    def has_rank(self) -> bool:
        return self.rank_score > 0

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "parent_problem_id": self.parent_problem_id,
            "title": self.title,
            "description": self.description,
            "code": self.code[:500],  # truncate for display
            "reasoning": self.reasoning,
            "files_modified": self.files_modified,
            "estimated_tokens": self.estimated_tokens,
            "estimated_runtime": self.estimated_runtime,
            "estimated_memory": self.estimated_memory,
            "rank_score": self.rank_score,
            "dimension_scores": self.dimension_scores,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "has_review": self.has_review,
        }
