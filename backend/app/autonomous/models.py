"""Data models for Sprint 9 — Autonomous Engineering.

The core types underlying every improvement EDITH proposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────

class OpportunityType(str, Enum):
    """Categories of improvement opportunities EDITH can detect."""

    HIGH_COMPLEXITY = "high_complexity"
    LONG_FUNCTION = "long_function"
    TOO_MANY_PARAMS = "too_many_params"
    DEEP_NESTING = "deep_nesting"
    MISSING_DOCSTRING = "missing_docstring"
    POOR_NAMING = "poor_naming"
    DEAD_CODE = "dead_code"
    DUPLICATION = "duplication"
    ARCHITECTURE_VIOLATION = "architecture_violation"
    LARGE_CLASS = "large_class"
    LOW_COHESION = "low_cohesion"
    COMPLEX_CONDITIONAL = "complex_conditional"
    MISSING_ERROR_HANDLING = "missing_error_handling"
    MAGIC_NUMBER = "magic_number"
    LONG_LINE = "long_line"
    INDENTATION_ISSUE = "indentation_issue"


class OpportunitySeverity(str, Enum):
    """How impactful fixing this opportunity would be."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PatchStatus(str, Enum):
    """Status of a generated improvement patch."""

    PENDING = "pending"
    SAFE = "safe"
    IMPROVES = "improves"
    REGRESSION = "regression"
    NEUTRAL = "neutral"


# ── Core models ──────────────────────────────────────────────────────

@dataclass
class Opportunity:
    """One concrete improvement opportunity found in the code.

    This is the input to the refactor generator — each opportunity
    describes *what* to improve and *where*.
    """

    type: OpportunityType
    severity: OpportunitySeverity
    file_path: str
    line: int = 0
    end_line: int = 0
    symbol_name: str = ""
    description: str = ""
    current_value: Optional[float] = None  # e.g. complexity=12, lines=85
    metric_name: str = ""                  # e.g. "cyclomatic_complexity"
    recommendation: str = ""               # e.g. "Extract the authentication logic"
    context_lines: list[str] = field(default_factory=list)  # surrounding code
    refactored_code: Optional[str] = None  # populated after generation

    @property
    def key(self) -> str:
        """Unique key for deduplication."""
        return f"{self.file_path}:{self.line}:{self.type.value}"

    @property
    def severity_score(self) -> int:
        _map = {
            OpportunitySeverity.CRITICAL: 5,
            OpportunitySeverity.HIGH: 4,
            OpportunitySeverity.MEDIUM: 3,
            OpportunitySeverity.LOW: 2,
            OpportunitySeverity.INFO: 1,
        }
        return _map.get(self.severity, 1)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line": self.line,
            "end_line": self.end_line,
            "symbol_name": self.symbol_name,
            "description": self.description,
            "current_value": self.current_value,
            "metric_name": self.metric_name,
            "recommendation": self.recommendation,
        }


@dataclass
class RefactoredCode:
    """Generated improved code for one opportunity."""

    opportunity_key: str
    original_code: str
    refactored_code: str
    explanation: str = ""
    preserves_behavior: bool = True


@dataclass
class Patch:
    """A single unified-diff patch for one file.

    Represents the exact change EDITH proposes.
    """

    file_path: str
    diff: str                        # unified diff text
    original_code: str               # the code being replaced
    new_code: str                    # the replacement code
    diff_lines_added: int = 0
    diff_lines_removed: int = 0

    # Review data
    status: PatchStatus = PatchStatus.PENDING
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    score_delta: float = 0.0
    dimension_deltas: dict[str, float] = field(default_factory=dict)

    # Impact prediction
    predicted_complexity_delta: float = 0.0
    predicted_maintainability_delta: float = 0.0
    predicted_lines_added: int = 0
    predicted_lines_removed: int = 0

    @property
    def is_improvement(self) -> bool:
        return self.score_delta > 0

    @property
    def summary(self) -> str:
        direction = "↑" if self.score_delta > 0 else "↓" if self.score_delta < 0 else "="
        return (
            f"{self.file_path}: {direction}{abs(self.score_delta):.1f} pts "
            f"({'+' if self.diff_lines_added > 0 else ''}{self.diff_lines_added},"
            f"-{self.diff_lines_removed})"
        )


@dataclass
class ImprovementResult:
    """Complete output of the autonomous improvement pipeline."""

    project_path: str
    project_name: str
    opportunities: list[Opportunity] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    overall_score_before: float = 0.0
    overall_score_after: float = 0.0
    total_opportunities: int = 0
    total_patches_generated: int = 0
    total_safe_patches: int = 0
    total_regressions: int = 0

    @property
    def impact_summary(self) -> str:
        if not self.patches:
            return "No improvements generated."
        lines: list[str] = []
        lines.append(f"Improvements for {self.project_name}")
        lines.append(f"  Opportunities found: {self.total_opportunities}")
        lines.append(f"  Patches generated:   {self.total_patches_generated}")
        lines.append(f"  Safe to apply:       {self.total_safe_patches}")
        lines.append(f"  Regressions:         {self.total_regressions}")
        lines.append(f"  Score delta:         {self.overall_score_after - self.overall_score_before:+.1f}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "project_name": self.project_name,
            "opportunities": [o.to_dict() for o in self.opportunities],
            "patches": [
                {
                    "file_path": p.file_path,
                    "summary": p.summary,
                    "status": p.status.value,
                    "score_delta": p.score_delta,
                    "is_improvement": p.is_improvement,
                }
                for p in self.patches
            ],
            "overall_score_before": self.overall_score_before,
            "overall_score_after": self.overall_score_after,
            "total_opportunities": self.total_opportunities,
            "total_patches_generated": self.total_patches_generated,
            "total_safe_patches": self.total_safe_patches,
            "total_regressions": self.total_regressions,
        }

    def text_report(self) -> str:
        """Generate a human-readable summary of all improvements."""
        sep = "=" * 55
        lines: list[str] = []
        lines.append(sep)
        lines.append(f"  AUTONOMOUS ENGINEERING REPORT")
        lines.append(f"  {self.project_name}")
        lines.append(sep)
        lines.append("")
        lines.append(f"  Overall Score:  {self.overall_score_before:.0f} → {self.overall_score_after:.0f}  "
                      f"({'↑' if self.overall_score_after >= self.overall_score_before else '↓'}"
                      f"{abs(self.overall_score_after - self.overall_score_before):.1f})")
        lines.append("")
        lines.append(f"  {self.total_opportunities} opportunities found")
        lines.append(f"  {self.total_patches_generated} patches generated")
        lines.append(f"  {self.total_safe_patches} safe to apply")
        lines.append(f"  {self.total_regressions} rejected (regression)")
        lines.append("")

        if self.patches:
            lines.append("  ── Patches ──")
            lines.append("")
            for p in self.patches:
                status_mark = {
                    PatchStatus.SAFE: "✓",
                    PatchStatus.IMPROVES: "✓",
                    PatchStatus.REGRESSION: "✗",
                    PatchStatus.NEUTRAL: "~",
                    PatchStatus.PENDING: "?",
                }.get(p.status, "?")
                lines.append(f"  {status_mark}  {p.file_path}")
                lines.append(f"     {p.summary}")
                lines.append(f"     Predicted: complexity {p.predicted_complexity_delta:+.0f}, "
                              f"maintainability {p.predicted_maintainability_delta:+.0f}")
                lines.append("")

        lines.append(sep)
        return "\n".join(lines)
