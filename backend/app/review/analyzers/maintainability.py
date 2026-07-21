"""Maintainability Analyzer — measures how easy the code will be to
maintain over time.

Factors
-------
1. Docstring coverage (function + class + module)
2. Comment ratio
3. Halstead effort (simplified — unique operators/operands)
4. Maintainability Index (MI) — a composite borrowed from SEI
5. Code-to-comment ratio
"""

from __future__ import annotations

import ast
import math
from pathlib import Path
from collections import Counter

from app.core.config import logger
from app.models.symbol import Symbol
from app.review.metrics import FileMetrics, RepositoryMetrics


class MaintainabilityAnalyzer:
    """Evaluates maintainability of source code.

    Uses a simplified Maintainability Index:

        MI = max(0, (171 - 5.2 * ln(Halstead_Volume)
                     - 0.23 * (Cyclomatic_Complexity)
                     - 16.2 * ln(Lines_of_Code)) * 100 / 171)

    We also compute:
        * Docstring coverage (% of functions/classes with docstrings)
        * Comment ratio (comment lines / total lines)
        * Halstead volume (simplified: unique tokens vs total tokens)
    """

    def analyze_file(
        self,
        file_path: Path,
        source: str,
        symbols: list[Symbol],
        file_metrics: FileMetrics,
    ) -> FileMetrics:
        """Augment an already-computed FileMetrics with maintainability data.

        Args:
            file_path: Path to the source file.
            source: Raw source code.
            symbols: Pre-extracted symbols.
            file_metrics: The partially-filled FileMetrics from ComplexityAnalyzer.

        Returns:
            The same FileMetrics with maintainability fields populated.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            logger.warning("Syntax error in %s — skipping maintainability analysis", file_path)
            return file_metrics

        lines = source.splitlines()

        # --- Docstring coverage ---
        total_callables = 0
        docstringed_callables = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                total_callables += 1
                if ast.get_docstring(node) is not None:
                    docstringed_callables += 1

        has_module_doc = ast.get_docstring(tree) is not None
        module_contrib = 1 if has_module_doc else 0

        docstring_coverage = (docstringed_callables + module_contrib) / max(total_callables + 1, 1)
        file_metrics.docstring_coverage = round(docstring_coverage, 4)
        file_metrics.has_module_docstring = has_module_doc

        # --- Comment ratio ---
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                comment_lines += 1
            elif stripped.startswith(('"""', "'''")) and stripped.endswith(('"""', "'''")):
                if len(stripped) > 6:
                    comment_lines += 1
            elif '"""' in stripped or "'''" in stripped:
                pass  # multiline docstrings counted elsewhere

        file_metrics.comment_lines = comment_lines

        # --- Halstead volume (simplified) ---
        halstead_volume = self._halstead_volume(source)

        # --- Maintainability Index ---
        loc = max(file_metrics.code_lines, 1)
        cc = max(int(file_metrics.average_complexity * max(len(file_metrics.functions), 1)), 1)

        try:
            mi_raw = (
                171
                - 5.2 * math.log(max(halstead_volume, 1))
                - 0.23 * cc
                - 16.2 * math.log(loc)
            )
            mi = max(0, mi_raw) * 100 / 171
        except (ValueError, OverflowError):
            mi = 0.0

        file_metrics.maintainability_index = round(mi, 1)

        return file_metrics

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _halstead_volume(self, source: str) -> float:
        """Compute a simplified Halstead volume.

        Uses Python's tokenizer to get a rough count of distinct
        operators and operands.
        """
        try:
            import tokenize
            from io import StringIO
        except ImportError:
            # Fallback: estimate from word count
            words = source.split()
            unique = len(set(words))
            total = len(words)
            if total == 0:
                return 0.0
            return total * math.log2(max(unique, 2))

        try:
            tokens = list(tokenize.generate_tokens(StringIO(source).readline))
        except Exception:
            return 0.0

        operators = 0
        operands = 0
        unique_operators = set()
        unique_operands = set()

        for tok in tokens:
            if tok.type == tokenize.OP:
                operators += 1
                unique_operators.add(tok.string)
            elif tok.type == tokenize.NAME and tok.string not in (
                "self", "cls", "True", "False", "None"
            ):
                operands += 1
                unique_operands.add(tok.string)

        if operators + operands == 0:
            return 0.0

        vocab = len(unique_operators) + len(unique_operands)
        length = operators + operands

        return length * math.log2(max(vocab, 2))

    @property
    def rating(self) -> str:
        """Placeholder — scores are computed per-file in the scoring engine."""
        return "not_implemented"
