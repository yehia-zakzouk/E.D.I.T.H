"""Duplication Analyzer — detects repeated code.

Uses a token-sequence fingerprinting approach:
    1. Normalize each line (strip whitespace, remove comments)
    2. Build a fingerprint for each N-line sliding window
    3. Hash-join to find duplicate blocks across files

This is kept intentionally simple — production-grade duplication detection
would use an AST-based approach. For EDITH's review engine, this gives
a useful signal without external dependencies.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from app.core.config import logger
from app.review.metrics import FileMetrics, RepositoryMetrics


class DuplicationAnalyzer:
    """Detects duplicated code blocks across files in a project."""

    MIN_BLOCK_LINES = 6       # minimum lines to consider a "block"
    MIN_SIMILARITY = 0.85     # line similarity ratio to count as duplicate

    def analyze_project(
        self,
        files: list[tuple[Path, str]],
        file_metrics: list[FileMetrics],
    ) -> list[FileMetrics]:
        """Run duplication analysis across all files.

        Args:
            files: List of (path, source_text) tuples.
            file_metrics: Partially-filled FileMetrics list (same order).

        Returns:
            Updated FileMetrics with duplication data.
        """
        if len(files) < 2:
            # No duplication possible with 0 or 1 file
            return file_metrics

        # Build fingerprints for each file
        fingerprints: dict[int, list[dict]] = defaultdict(list)  # hash -> [file_index, start_line, ...]

        for idx, (path, source) in enumerate(files):
            normalized_lines = self._normalize_lines(source)
            if len(normalized_lines) < self.MIN_BLOCK_LINES:
                continue

            # Slide a window over the normalized lines
            for start in range(len(normalized_lines) - self.MIN_BLOCK_LINES + 1):
                block = normalized_lines[start:start + self.MIN_BLOCK_LINES]
                block_hash = hash(tuple(block))
                fingerprints[block_hash].append({
                    "file_idx": idx,
                    "start_line": start + 1,  # 1-based
                    "block": block,
                })

        # Find hashes shared across different files
        duplicate_files: dict[int, set[int]] = defaultdict(set)  # file_idx -> set of other file_idxs
        duplicate_line_counts: dict[int, int] = defaultdict(int)

        for block_hash, occurrences in fingerprints.items():
            if len(occurrences) < 2:
                continue

            # Group by file index
            file_groups: dict[int, list[dict]] = defaultdict(list)
            for occ in occurrences:
                file_groups[occ["file_idx"]].append(occ)

            file_idxs = list(file_groups.keys())
            for i in range(len(file_idxs)):
                for j in range(i + 1, len(file_idxs)):
                    f1 = file_idxs[i]
                    f2 = file_idxs[j]
                    duplicate_files[f1].add(f2)
                    duplicate_files[f2].add(f1)
                    duplicate_line_counts[f1] += self.MIN_BLOCK_LINES
                    duplicate_line_counts[f2] += self.MIN_BLOCK_LINES

        # Write results back into FileMetrics
        for idx, fm in enumerate(file_metrics):
            if idx in duplicate_line_counts:
                fm.duplicate_lines = duplicate_line_counts[idx]
                fm.duplicate_blocks = duplicate_line_counts[idx] // self.MIN_BLOCK_LINES

        return file_metrics

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _normalize_lines(self, source: str) -> list[str]:
        """Normalize source lines for comparison.

        Strips:
            - Leading/trailing whitespace
            - Comments
            - Blank lines
            - Variable names (replaced with placeholder)
        """
        lines = source.splitlines()
        normalized: list[str] = []

        # Simple variable-name normalization patterns
        var_pattern = re.compile(r"\b[a-z_][a-z0-9_]{0,20}\b(?=\s*[=:])")

        for line in lines:
            stripped = line.strip()

            # Skip blank lines, comments, and docstring-heavy lines
            if not stripped:
                continue
            if stripped.startswith(("#", '"""', "'''")):
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                # Keep imports, they're distinctive
                normalized.append(stripped)
                continue

            # Normalize variable names in assignment contexts
            stripped = var_pattern.sub("_VAR_", stripped)

            # Normalize string literals
            stripped = re.sub(r"'[^']*'", "'_STR_'", stripped)
            stripped = re.sub(r'"[^"]*"', '"_STR_"', stripped)

            # Normalize numbers
            stripped = re.sub(r'\b\d+\b', '_NUM_', stripped)

            normalized.append(stripped)

        return normalized
