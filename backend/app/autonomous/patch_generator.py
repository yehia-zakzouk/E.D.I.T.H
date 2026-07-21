"""Patch Generator (Sprint 9.3) — converts "old code → new code" into
production-ready unified diff patches that can be directly applied.

Instead of showing "here's new code," EDITH generates:

    def login(request):
    -   if not request.user:
    -       raise PermissionError
    +   authenticate(request)
        return process(request)

The patches follow the unified diff format (``diff -u old new``).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.autonomous.models import (
    Opportunity,
    OpportunityType,
    Patch,
    PatchStatus,
    RefactoredCode,
)


class PatchGenerator:
    """Converts refactored code into unified diff patches.

    Usage::

        generator = PatchGenerator()
        patches = generator.generate(opportunities, refactored_codes, project)
        for patch in patches:
            print(patch.diff)
    """

    def generate(
        self,
        opportunities: list[Opportunity],
        refactored_codes: list[RefactoredCode],
        file_sources: dict[str, str],  # file_path → full source
    ) -> list[Patch]:
        """Generate patches for all refactored opportunities.

        Args:
            opportunities: The original opportunities (for context).
            refactored_codes: The corresponding refactored code for each.
            file_sources: Map of file path → full source text.

        Returns:
            A list of Patch objects (one per file that was changed).
        """
        logger.info("PatchGenerator: generating patches for %d refactorings", len(refactored_codes))

        # Group refactorings by file
        file_refactors: dict[str, list[RefactoredCode]] = {}
        for refactored in refactored_codes:
            opp_key = refactored.opportunity_key
            # Find the matching opportunity to get the file path
            matching = [o for o in opportunities if o.key == opp_key]
            if not matching:
                continue
            file_path = matching[0].file_path
            file_refactors.setdefault(file_path, []).append(refactored)

        patches: list[Patch] = []

        for file_path, refactors in file_refactors.items():
            original_source = file_sources.get(file_path)
            if original_source is None:
                logger.warning("PatchGenerator: source not found for %s", file_path)
                continue

            # Apply all refactorings to this file sequentially
            new_source = original_source
            for refactored in refactors:
                if refactored.refactored_code:
                    # If the refactored code is a snippet, try to find-and-replace
                    # in the full source. Otherwise, replace the whole file.
                    snippet = refactored.refactored_code
                    original_snippet = refactored.original_code

                    if snippet and len(snippet) < len(new_source) * 0.8:
                        # It's a snippet — find and replace
                        if original_snippet in new_source:
                            new_source = new_source.replace(original_snippet, snippet, 1)
                        else:
                            # Try normalized matching
                            norm_original = _normalize(original_snippet)
                            norm_new = _normalize(snippet)
                            if norm_original in _normalize(new_source):
                                new_source = _smart_replace(new_source, original_snippet, snippet)
                            else:
                                logger.debug(
                                    "PatchGenerator: snippet not found in source for %s",
                                    file_path,
                                )
                                new_source = snippet  # fallback: replace entire file
                    else:
                        # It's the whole file — replace entirely
                        new_source = snippet

            if new_source == original_source:
                logger.debug("PatchGenerator: no changes for %s", file_path)
                continue

            # ── Generate unified diff ─────────────────────────────
            diff = self._make_diff(file_path, original_source, new_source)

            # Count added/removed lines
            added = 0
            removed = 0
            for line in diff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1

            patch = Patch(
                file_path=file_path,
                diff=diff,
                original_code=original_source,
                new_code=new_source,
                diff_lines_added=added,
                diff_lines_removed=removed,
                status=PatchStatus.PENDING,
            )

            patches.append(patch)

        logger.info(
            "PatchGenerator: generated %d patches covering %d refactorings",
            len(patches),
            len(refactored_codes),
        )

        return patches

    @staticmethod
    def _make_diff(file_path: str, original: str, new: str) -> str:
        """Generate a unified diff between original and new source.

        The result can be saved to a ``.patch`` file and applied with
        ``git apply`` or ``patch -p1``.
        """
        original_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        # Use the file name for the diff header
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=3,  # context lines
        )

        return "".join(diff)

    @staticmethod
    def save_patch_file(patch: Patch, output_dir: Path) -> Path:
        """Save a single patch to a ``.patch`` file.

        Returns the path to the saved file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create a safe filename
        safe_name = patch.file_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        patch_path = output_dir / f"{safe_name}.patch"

        patch_path.write_text(patch.diff, encoding="utf-8")
        return patch_path


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Strip all whitespace for fuzzy matching."""
    return re.sub(r"\s+", "", text)


def _smart_replace(full_text: str, old: str, new: str) -> str:
    """Replace *old* with *new* in *full_text*, even if whitespace differs."""
    # Try direct replacement first
    result = full_text.replace(old, new, 1)
    if result != full_text:
        return result

    # Fuzzy replacement: split into lines, match by normalized content
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    full_lines = full_text.splitlines()

    if not old_lines or not full_lines:
        return full_text

    # Look for the first line of old in full_text
    first_old_stripped = old_lines[0].strip()
    for i, line in enumerate(full_lines):
        if line.strip() == first_old_stripped:
            # Check if subsequent lines match
            match = True
            for j in range(min(len(old_lines), len(full_lines) - i)):
                if old_lines[j].strip() != full_lines[i + j].strip():
                    match = False
                    break
            if match:
                # Replace the matched block
                full_lines[i:i + len(old_lines)] = new_lines
                return "\n".join(full_lines)

    return full_text
