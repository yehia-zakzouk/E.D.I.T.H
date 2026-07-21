"""Engineering problem model — the structured representation of a user's
engineering request.

The ProblemAnalyzer transforms free-text questions into this structured form.
Every downstream stage (generator, reviewer, ranker, trade-off analyser, LLM)
reads this to understand what the user actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# Counter for auto-incrementing problem IDs
_problem_counter: int = 0


def _next_problem_id() -> int:
    global _problem_counter
    _problem_counter += 1
    return _problem_counter


# ------------------------------------------------------------------
# Enums — structured classification
# ------------------------------------------------------------------

class ProblemGoal(str, Enum):
    """The high-level goal of the engineering request."""

    NEW_FEATURE = "new_feature"
    REFACTOR = "refactor"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    BUG_FIX = "bug_fix"
    ARCHITECTURE_CHANGE = "architecture_change"
    SECURITY_IMPROVEMENT = "security_improvement"
    DOCUMENTATION = "documentation"
    CODE_REVIEW = "code_review"
    DEPENDENCY_UPDATE = "dependency_update"
    TEST_IMPROVEMENT = "test_improvement"
    GENERAL_QUESTION = "general_question"


class ProblemScope(str, Enum):
    """How broadly the change touches the codebase."""

    SINGLE_FUNCTION = "single_function"
    SINGLE_FILE = "single_file"
    MULTIPLE_FILES = "multiple_files"
    MODULE = "module"
    ARCHITECTURE_WIDE = "architecture_wide"


class AffectedLayer(str, Enum):
    """Architectural layers a change might touch."""

    API = "api"
    DATABASE = "database"
    MODELS = "models"
    SERVICES = "services"
    MIDDLEWARE = "middleware"
    CONFIGURATION = "configuration"
    TESTS = "tests"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    UI = "ui"
    SECURITY = "security"
    UNKNOWN = "unknown"


# ------------------------------------------------------------------
# Main model
# ------------------------------------------------------------------

@dataclass
class EngineeringProblem:
    """A structured representation of an engineering request.

    This is the output of ProblemAnalyzer.analyze() and the input to
    every downstream stage.

    Each problem gets a unique ``problem_id`` so candidates can reference
    their parent. Over time this enables a dataset of ``problem →
    candidates → user-choice`` decisions.
    """

    # --- Identity ---
    problem_id: int = field(default_factory=_next_problem_id)

    # --- Original request ---
    question: str = ""
    target: Optional[str] = None  # extracted symbol/file name, e.g. "authenticate"

    # --- Classification ---
    goal: ProblemGoal = ProblemGoal.GENERAL_QUESTION
    scope: ProblemScope = ProblemScope.SINGLE_FUNCTION
    affected_layers: list[AffectedLayer] = field(default_factory=lambda: [AffectedLayer.UNKNOWN])

    # --- Constraints ---
    must_preserve_behavior: bool = True
    constraints: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)

    # --- Risk & complexity assessment ---
    complexity: str = "low"  # "low" | "medium" | "high"
    risk: str = "low"       # "low" | "medium" | "high"

    # --- Context extracted from the repo ---
    relevant_files: list[str] = field(default_factory=list)
    relevant_symbols: list[str] = field(default_factory=list)
    project_languages: list[str] = field(default_factory=list)
    project_frameworks: list[str] = field(default_factory=list)
    build_system: Optional[str] = None

    # --- Reasoning (why the analyzer classified it this way) ---
    reasoning: str = ""

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def is_single_target(self) -> bool:
        """Whether the change is limited to one function or file."""
        return self.scope in (ProblemScope.SINGLE_FUNCTION, ProblemScope.SINGLE_FILE)

    @property
    def is_architecture_change(self) -> bool:
        return self.scope == ProblemScope.ARCHITECTURE_WIDE

    @property
    def is_critical(self) -> bool:
        return self.risk == "high" or self.complexity == "high"

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "question": self.question,
            "target": self.target,
            "goal": self.goal.value,
            "scope": self.scope.value,
            "affected_layers": [l.value for l in self.affected_layers],
            "must_preserve_behavior": self.must_preserve_behavior,
            "constraints": self.constraints,
            "preferences": self.preferences,
            "complexity": self.complexity,
            "risk": self.risk,
            "relevant_files": self.relevant_files[:10],
            "relevant_symbols": self.relevant_symbols[:15],
            "project_languages": self.project_languages,
            "project_frameworks": self.project_frameworks,
            "build_system": self.build_system,
            "reasoning": self.reasoning,
        }

    def summary(self) -> str:
        """One-line summary for logging / display."""
        layers = ", ".join(l.value for l in self.affected_layers if l != AffectedLayer.UNKNOWN)
        return (
            f"[#{self.problem_id}][{self.goal.value}] "
            f"scope={self.scope.value} "
            f"complexity={self.complexity} risk={self.risk} "
            f"layers=[{layers}]  target={self.target}"
        )
