"""Complexity Analyzer — measures cyclomatic complexity, function length,
nesting depth, class size, and parameter counts.

Works directly on the already-parsed AST from the Python analyzer,
avoiding a second parse pass.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.models.symbol import Symbol
from app.review.metrics import FunctionMetrics, ClassMetrics, FileMetrics, RepositoryMetrics


# Re-export for callers that want to use this directly
__all__ = ["ComplexityAnalyzer"]


class ComplexityAnalyzer:
    """Analyses code complexity using the existing AST and Symbol data.

    Calculates:
        * Cyclomatic complexity (McCabe)
        * Function length (lines of code)
        * Max nesting depth
        * Number of parameters
        * Class size (lines, method count)
    """

    def analyze_file(
        self,
        file_path: Path,
        source: str,
        symbols: list[Symbol],
    ) -> FileMetrics:
        """Run complexity analysis on a single file.

        Args:
            file_path: Path to the source file.
            source: Raw source text (needed for line counts).
            symbols: Pre-extracted Symbol list from the knowledge extractor.

        Returns:
            A FileMetrics instance populated with function & class metrics.
        """
        lines = source.splitlines()
        total_lines = len(lines)

        # Count code / blank / comment lines
        code_lines = 0
        comment_lines = 0
        blank_lines = 0
        max_line_len = 0
        total_line_len = 0

        for line in lines:
            stripped = line.strip()
            total_line_len += len(line.rstrip("\n"))
            max_line_len = max(max_line_len, len(line.rstrip("\n")))
            if not stripped:
                blank_lines += 1
            elif stripped.startswith("#"):
                comment_lines += 1
            else:
                code_lines += 1

        # Parse AST for control-flow analysis (complexity, nesting)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            logger.warning("Syntax error in %s — skipping AST analysis", file_path)
            tree = ast.Module(body=[], type_ignores=[])

        # Build a map of function start lines -> symbol
        func_symbols = {s.line: s for s in symbols if s.kind in (
            "function", "method", "async_function", "async_method"
        )}
        class_symbols = {s.line: s for s in symbols if s.kind == "class"}

        function_metrics = self._analyze_functions(tree, file_path, lines, func_symbols)
        class_metrics = self._analyze_classes(tree, file_path, lines, class_symbols, function_metrics)

        # Docstring coverage for functions in this file
        funcs_with_doc = sum(1 for f in function_metrics if f.has_docstring)
        total_funcs = len(function_metrics)
        docstring_coverage = funcs_with_doc / max(total_funcs, 1)

        # Has module docstring?
        has_module_doc = ast.get_docstring(tree) is not None

        return FileMetrics(
            path=str(file_path),
            language=self._detect_language(file_path),
            lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines,
            functions=function_metrics,
            classes=class_metrics,
            docstring_coverage=docstring_coverage,
            has_module_docstring=has_module_doc,
            max_line_length=max_line_len,
            average_line_length=round(total_line_len / max(total_lines, 1), 1),
        )

    # ------------------------------------------------------------------
    # Internal — Function analysis
    # ------------------------------------------------------------------

    def _analyze_functions(
        self,
        tree: ast.AST,
        file_path: Path,
        lines: list[str],
        func_symbols: dict[int, Symbol],
    ) -> list[FunctionMetrics]:
        """Walk the AST and collect metrics for every function/method."""
        results: list[FunctionMetrics] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            symbol = func_symbols.get(node.lineno)
            if symbol is None:
                # Symbol not found in pre-extracted data — compute what we can
                symbol = self._build_fallback_symbol(node, str(file_path))

            # Cyclomatic complexity
            cc = self._cyclomatic_complexity(node)

            # Max nesting depth
            nesting = self._max_nesting(node, current_depth=0)

            # Function lines (body only)
            func_lines = self._function_lines(node, lines)

            # Docstring
            docstring = ast.get_docstring(node)
            doc_lines = len(docstring.splitlines()) if docstring else 0

            # Parameter count
            all_args = (
                list(node.args.args)
                + list(node.args.kwonlyargs)
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            )
            # Exclude 'self' and 'cls' from parameter count
            param_count = len([a for a in all_args if a.arg not in ("self", "cls")])

            results.append(FunctionMetrics(
                name=symbol.name,
                qualified_name=symbol.qualified_name,
                file=str(file_path),
                cyclomatic_complexity=cc,
                lines=func_lines,
                parameters=param_count,
                max_nesting=nesting,
                has_docstring=docstring is not None,
                docstring_lines=doc_lines,
                line=node.lineno,
            ))

        return results

    def _cyclomatic_complexity(self, node: ast.AST) -> int:
        """McCabe cyclomatic complexity.

        Base = 1. Increment for each:
            - if / elif / else
            - while / for
            - except
            - with ( context managers )
            - boolean operators (and, or)
            - assert
            - ternary (a if cond else b)
            - comprehension (list, dict, set, generator)
        """
        count = 1  # base

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                count += 1
            elif isinstance(child, ast.ExceptHandler):
                count += 1
            elif isinstance(child, ast.With):
                count += 1
            elif isinstance(child, ast.BoolOp):
                # Each 'and'/'or' adds a path — count all operands beyond the first
                count += len(child.values) - 1
            elif isinstance(child, ast.Assert):
                count += 1
            elif isinstance(child, ast.IfExp):
                count += 1  # ternary
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                # Comprehension conditionals increase paths
                pass

        return count

    def _max_nesting(self, node: ast.AST, current_depth: int = 0) -> int:
        """Walk the AST and find the maximum nesting depth."""
        max_depth = current_depth
        nesting_nodes = (ast.If, ast.While, ast.For, ast.AsyncFor,
                         ast.Try, ast.With, ast.FunctionDef)

        for child in ast.iter_child_nodes(node):
            if isinstance(child, nesting_nodes):
                depth = self._max_nesting(child, current_depth + 1)
                max_depth = max(max_depth, depth)
            else:
                depth = self._max_nesting(child, current_depth)
                max_depth = max(max_depth, depth)

        return max_depth

    def _function_lines(self, node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> int:
        """Count the lines in the function body."""
        if not hasattr(node, "end_lineno") or node.end_lineno is None:
            return 0
        # Count only code lines in the body
        body_start = min(
            (child.lineno for child in ast.walk(node)
             if hasattr(child, "lineno") and child.lineno > node.lineno),
            default=node.end_lineno
        )
        code = 0
        for i in range(body_start - 1, min(node.end_lineno, len(lines))):
            if lines[i].strip() and not lines[i].strip().startswith("#"):
                code += 1
        return code

    def _build_fallback_symbol(self, node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str) -> Symbol:
        """Create a minimal Symbol when the extractor missed it."""
        return Symbol(
            name=node.name,
            qualified_name=node.name,
            kind="function",
            file=file_path,
            line=node.lineno,
        )

    # ------------------------------------------------------------------
    # Internal — Class analysis
    # ------------------------------------------------------------------

    def _analyze_classes(
        self,
        tree: ast.AST,
        file_path: Path,
        lines: list[str],
        class_symbols: dict[int, Symbol],
        function_metrics: list[FunctionMetrics],
    ) -> list[ClassMetrics]:
        """Walk the AST and collect metrics for every class."""
        results: list[ClassMetrics] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            symbol = class_symbols.get(node.lineno)
            if symbol is None:
                from app.models.symbol import Symbol
                symbol = Symbol(
                    name=node.name,
                    qualified_name=node.name,
                    kind="class",
                    file=str(file_path),
                    line=node.lineno,
                )

            # Lines
            if hasattr(node, "end_lineno") and node.end_lineno is not None:
                class_lines = node.end_lineno - node.lineno + 1
            else:
                class_lines = 0

            # Method count
            methods = [
                n for n in ast.walk(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            method_count = len(methods)

            # Attribute assignments in __init__
            attributes = 0
            for method in methods:
                if method.name == "__init__":
                    for child in ast.walk(method):
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                                    if target.value.id in ("self", "cls"):
                                        attributes += 1

            # Aggregate complexity from methods belonging to this class
            class_funcs = [f for f in function_metrics if f.qualified_name.startswith(f"{symbol.name}.")]
            total_complexity = sum(f.cyclomatic_complexity for f in class_funcs)
            avg_method_complexity = total_complexity / max(method_count, 1)

            # Base classes
            bases = [ast.unparse(b) for b in node.bases] if hasattr(node, "bases") else []
            if symbol:
                bases = symbol.bases or bases

            # Inheritance depth (rough: just detect inheritance)
            depth = 1
            if bases:
                depth = 2  # has at least one parent

            results.append(ClassMetrics(
                name=symbol.name,
                qualified_name=symbol.qualified_name,
                file=str(file_path),
                lines=class_lines,
                method_count=method_count,
                attributes=attributes,
                total_complexity=total_complexity,
                average_method_complexity=round(avg_method_complexity, 2),
                base_classes=bases,
                depth=depth,
                line=node.lineno,
            ))

        return results

    # ------------------------------------------------------------------
    # Internal — Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_language(path: Path) -> str:
        ext = path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp", ".cxx": "cpp", ".cc": "cpp", ".c": "c",
            ".h": "c", ".hpp": "cpp",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
        }
        return mapping.get(ext, "unknown")

    @staticmethod
    def analyze(source: str) -> dict:
        """Static convenience — quick complexity scan from raw source.

        Args:
            source: Raw Python source code.

        Returns:
            Dict with top-level complexity info.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {"error": "syntax_error", "complexity": 0}

        analyzer = ComplexityAnalyzer()
        cc = 0
        func_count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc += analyzer._cyclomatic_complexity(node)
                func_count += 1

        return {
            "cyclomatic_complexity": cc,
            "function_count": func_count,
            "average_complexity": round(cc / max(func_count, 1), 2),
        }
