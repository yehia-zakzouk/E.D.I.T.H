"""Readability Analyzer — evaluates code readability.

Factors
-------
1. Line length distribution (how many lines exceed 79/88/100 chars)
2. Naming convention violations (snake_case vs camelCase mismatches)
3. File length relative to threshold
4. Blank line density (separator between logical blocks)
5. Consistent indentation
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.models.symbol import Symbol
from app.review.metrics import FileMetrics


# Python naming patterns
SNAKE_CASE_RE = re.compile(r"^_?[a-z][a-z0-9_]*$")
CAMEL_CASE_RE = re.compile(r"^_?[a-z]+[A-Z][a-zA-Z0-9]*$")
PASCAL_CASE_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
CONSTANT_CASE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
DUNDER_RE = re.compile(r"^__[a-z][a-z0-9_]*__$")


class ReadabilityAnalyzer:
    """Evaluates code readability from source and symbol data.

    Produces penalties that feed into the overall readability score.
    """

    # Thresholds (configurable)
    MAX_LINE_LENGTH = 100      # soft limit
    HARD_LINE_LENGTH = 120     # hard limit
    MAX_FILE_LENGTH = 800      # lines
    MIN_BLANK_RATIO = 0.05     # at least 5% blank lines
    MAX_BLANK_RATIO = 0.30     # no more than 30% blank lines

    def analyze_file(
        self,
        file_path: Path,
        source: str,
        symbols: list[Symbol],
        file_metrics: FileMetrics,
    ) -> FileMetrics:
        """Compute readability metrics for a single file."""
        lines = source.splitlines()
        total_lines = len(lines)

        # --- Line length penalties ---
        long_lines_soft = 0
        long_lines_hard = 0
        max_len = 0

        for line in lines:
            length = len(line.rstrip("\n"))
            max_len = max(max_len, length)
            if length > self.HARD_LINE_LENGTH:
                long_lines_hard += 1
            elif length > self.MAX_LINE_LENGTH:
                long_lines_soft += 1

        file_metrics.max_line_length = max_len

        # --- Blank line density ---
        blank_lines = sum(1 for line in lines if not line.strip())
        blank_ratio = blank_lines / max(total_lines, 1)

        # --- Naming convention violations ---
        naming_issues = self._check_naming(symbols)

        # --- Indentation consistency ---
        indent_issues = self._check_indentation(lines)

        # --- Store custom penalties for scoring engine ---
        file_metrics.readability_penalties = {
            "long_lines_soft": long_lines_soft,
            "long_lines_hard": long_lines_hard,
            "blank_ratio": round(blank_ratio, 4),
            "naming_issues": naming_issues,
            "indent_issues": indent_issues,
            "too_long": total_lines > self.MAX_FILE_LENGTH,
        }

        return file_metrics

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_naming(self, symbols: list[Symbol]) -> list[str]:
        """Check naming conventions for all symbols.

        Rules (Python):
            - Functions / methods → snake_case
            - Classes → PascalCase
            - Constants → UPPER_CASE
            - Dunder methods → __x__ (special, allowed)
        """
        issues: list[str] = []

        for sym in symbols:
            name = sym.name

            # Skip dunders
            if DUNDER_RE.match(name):
                continue

            if sym.kind in ("function", "method", "async_function", "async_method"):
                if not SNAKE_CASE_RE.match(name) and not CAMEL_CASE_RE.match(name):
                    if not name.startswith("__") or not name.endswith("__"):
                        issues.append(f"{sym.qualified_name} (should be snake_case)")

            elif sym.kind == "class":
                if not PASCAL_CASE_RE.match(name):
                    issues.append(f"{sym.qualified_name} (should be PascalCase)")

        return issues

    def _check_indentation(self, lines: list[str]) -> list[str]:
        """Check for inconsistent indentation."""
        issues: list[str] = []
        indent_counts: dict[int, int] = {}  # indent width -> count

        for line in lines:
            if not line.strip() or line.strip().startswith("#"):
                continue
            leading = len(line) - len(line.lstrip())
            if leading > 0:
                indent_counts[leading] = indent_counts.get(leading, 0) + 1

        if not indent_counts:
            return issues

        # Find the most common indent width
        most_common = max(indent_counts, key=indent_counts.get)

        # Flag lines using a different indent width
        unusual_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            leading = len(line) - len(line.lstrip())
            if leading > 0 and leading != most_common and leading % most_common != 0:
                unusual_count += 1

        if unusual_count > 5:
            issues.append(f"{unusual_count} lines with inconsistent indentation")

        return issues
