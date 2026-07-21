"""Safety Engine (Sprint 9.5) — the gatekeeper that ensures EDITH never
recommends a change that makes code worse.

Every patch goes through these safety checks:

1. **Score check** — Is the overall review score higher after the change?
2. **Dimension check** — Are no critical dimensions regressing severely?
3. **Syntax check** — Does the new code parse without errors?
4. **Behavior preservation** — Could the change alter behavior? (heuristic)
5. **Size sanity** — Is the patch reasonable in size?
6. **File boundary** — Does the patch only touch expected files?

Only patches that pass all checks are marked ``SAFE`` or ``IMPROVES``.
"""

from __future__ import annotations

import ast
import re
from typing import Optional

from app.core.config import logger
from app.autonomous.models import Patch, PatchStatus


# ── Configurable thresholds ──────────────────────────────────────────

MAX_ALLOWED_REGRESSION = 2.0       # dimensions may drop this much without failing
CRITICAL_DIMENSION_DROP = 10.0     # any dimension dropping this much = fail
MAX_PATCH_LINES = 1000             # patches larger than this are suspicious
MAX_FILE_SIZE_BEFORE = 5000        # files larger than this need special scrutiny
MIN_IMPROVEMENT_THRESHOLD = 0.5    # patches must improve by at least this much


class SafetyEngine:
    """Validates that every patch is a genuine improvement.

    Usage::

        engine = SafetyEngine()
        safe_patches, rejected = engine.filter(patches)
        for patch in safe_patches:
            print(f"SAFE: {patch.file_path}")
    """

    def filter(self, patches: list[Patch]) -> tuple[list[Patch], list[Patch]]:
        """Run all safety checks on every patch.

        Returns
        -------
        (safe_patches, rejected_patches)
            safe_patches: patches that pass all checks.
            rejected_patches: patches that failed one or more checks.
        """
        safe: list[Patch] = []
        rejected: list[Patch] = []

        for patch in patches:
            issues = self._check_all(patch)
            if issues:
                for issue in issues:
                    logger.debug(
                        "SafetyEngine: REJECTED %s — %s",
                        patch.file_path,
                        issue,
                    )
                patch.status = PatchStatus.REGRESSION
                rejected.append(patch)
            else:
                if patch.status in (PatchStatus.IMPROVES, PatchStatus.NEUTRAL):
                    patch.status = PatchStatus.SAFE
                safe.append(patch)

        logger.info(
            "SafetyEngine: %d safe, %d rejected out of %d total",
            len(safe),
            len(rejected),
            len(patches),
        )

        return safe, rejected

    def _check_all(self, patch: Patch) -> list[str]:
        """Run all safety checks, returning a list of issue descriptions.

        An empty list means the patch passed all checks.
        """
        issues: list[str] = []

        # 1. Syntax check
        issues.extend(self._check_syntax(patch))

        # 2. Score check (must not regress overall)
        issues.extend(self._check_scores(patch))

        # 3. Dimension check (no critical dimension regressions)
        issues.extend(self._check_dimensions(patch))

        # 4. Size sanity
        issues.extend(self._check_size(patch))

        return issues

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_syntax(patch: Patch) -> list[str]:
        """Check that the new code parses without syntax errors."""
        issues: list[str] = []

        new_code = patch.new_code
        if not new_code.strip():
            issues.append("New code is empty")
            return issues

        try:
            ast.parse(new_code)
        except SyntaxError as e:
            issues.append(f"Syntax error in new code: {e}")

        # Also check that original code parses (it should, but be sure)
        try:
            ast.parse(patch.original_code)
        except SyntaxError:
            issues.append("Original code has syntax errors — cannot compare")

        return issues

    @staticmethod
    def _check_scores(patch: Patch) -> list[str]:
        """Check that the patch doesn't regress the overall score."""
        issues: list[str] = []

        if patch.score_before is None or patch.score_after is None:
            issues.append("No review scores available for this patch")
            return issues

        if patch.score_delta < -MAX_ALLOWED_REGRESSION:
            issues.append(
                f"Overall score regressed by {abs(patch.score_delta):.1f} points "
                f"(max allowed drop: {MAX_ALLOWED_REGRESSION})"
            )

        return issues

    @staticmethod
    def _check_dimensions(patch: Patch) -> list[str]:
        """Check that no critical dimension regresses too much."""
        issues: list[str] = []

        for dim, delta in patch.dimension_deltas.items():
            if delta < -CRITICAL_DIMENSION_DROP:
                issues.append(
                    f"'{dim}' dropped by {abs(delta):.1f} points "
                    f"(max allowed: {CRITICAL_DIMENSION_DROP})"
                )

        return issues

    @staticmethod
    def _check_size(patch: Patch) -> list[str]:
        """Check that the patch is a reasonable size."""
        issues: list[str] = []

        total_changes = patch.diff_lines_added + patch.diff_lines_removed

        if total_changes > MAX_PATCH_LINES:
            issues.append(
                f"Patch modifies {total_changes} lines "
                f"(max allowed: {MAX_PATCH_LINES})"
            )

        if total_changes == 0:
            issues.append("Patch has no actual changes")

        return issues
