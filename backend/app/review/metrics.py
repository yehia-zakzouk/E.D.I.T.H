"""Data models for EDITH's engineering-review metrics.

Hierarchy
---------
FunctionMetrics  →  one per function/method
ClassMetrics     →  one per class
FileMetrics      →  aggregates per file, includes all function & class metrics
RepositoryMetrics → top-level summary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Function-level
# ------------------------------------------------------------------

@dataclass
class FunctionMetrics:
    """Metrics measured for a single function or method."""

    name: str
    qualified_name: str
    file: str

    # Complexity
    cyclomatic_complexity: int = 1
    lines: int = 0
    parameters: int = 0
    max_nesting: int = 0

    # Maintainability
    has_docstring: bool = False
    docstring_lines: int = 0

    # Debug info
    line: int = 0

    @property
    def complexity_rating(self) -> str:
        """Human-friendly rating for cyclomatic complexity."""
        cc = self.cyclomatic_complexity
        if cc <= 5:
            return "low"
        if cc <= 10:
            return "moderate"
        if cc <= 20:
            return "high"
        return "very high"

    @property
    def is_long_function(self) -> bool:
        """Functions longer than 60 lines are flagged."""
        return self.lines > 60

    @property
    def has_too_many_params(self) -> bool:
        """More than 5 parameters is flagged."""
        return self.parameters > 5


# ------------------------------------------------------------------
# Class-level
# ------------------------------------------------------------------

@dataclass
class ClassMetrics:
    """Metrics measured for a single class."""

    name: str
    qualified_name: str
    file: str

    # Size
    lines: int = 0
    method_count: int = 0
    attributes: int = 0  # number of assignments in __init__ etc.

    # Complexity
    total_complexity: int = 0
    average_method_complexity: float = 0.0

    # Inheritance
    base_classes: list[str] = field(default_factory=list)
    depth: int = 1  # inheritance depth (1 = no parent)

    line: int = 0

    @property
    def is_large_class(self) -> bool:
        """Classes larger than 400 lines are flagged."""
        return self.lines > 400

    @property
    def has_too_few_methods(self) -> bool:
        """Classes with few methods relative to size."""
        return self.method_count < 2 and self.lines > 100


# ------------------------------------------------------------------
# File-level
# ------------------------------------------------------------------

@dataclass
class FileMetrics:
    """Metrics for a single file, aggregating its functions & classes."""

    path: str
    language: Optional[str] = None
    lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0

    functions: list[FunctionMetrics] = field(default_factory=list)
    classes: list[ClassMetrics] = field(default_factory=list)

    # File-level derived
    docstring_coverage: float = 0.0  # 0.0 – 1.0
    has_module_docstring: bool = False

    # Duplication (populated later)
    duplicate_lines: int = 0
    duplicate_blocks: int = 0

    # Maintainability
    maintainability_index: float = 0.0

    # Readability
    max_line_length: int = 0
    average_line_length: float = 0.0
    readability_penalties: dict = field(default_factory=dict)

    @property
    def function_count(self) -> int:
        return len(self.functions)

    @property
    def class_count(self) -> int:
        return len(self.classes)

    @property
    def average_complexity(self) -> float:
        if not self.functions:
            return 0.0
        return sum(f.cyclomatic_complexity for f in self.functions) / len(self.functions)

    @property
    def average_function_length(self) -> float:
        if not self.functions:
            return 0.0
        return sum(f.lines for f in self.functions) / len(self.functions)

    @property
    def worst_function(self) -> Optional[FunctionMetrics]:
        """Return the function with highest cyclomatic complexity."""
        if not self.functions:
            return None
        return max(self.functions, key=lambda f: f.cyclomatic_complexity)

    @property
    def largest_class(self) -> Optional[ClassMetrics]:
        """Return the largest class by line count."""
        if not self.classes:
            return None
        return max(self.classes, key=lambda c: c.lines)


# ------------------------------------------------------------------
# Repository-level
# ------------------------------------------------------------------

@dataclass
class RepositoryMetrics:
    """Aggregate metrics across the entire repository."""

    files: list[FileMetrics] = field(default_factory=list)

    # ---- Aggregated values ----
    total_files: int = 0
    total_lines: int = 0
    total_code_lines: int = 0
    total_comment_lines: int = 0
    total_symbols: int = 0

    # Complexity
    average_complexity: float = 0.0
    worst_function: Optional[str] = None
    worst_function_complexity: int = 0
    worst_function_file: Optional[str] = None

    # Size
    average_function_length: float = 0.0
    largest_class: Optional[str] = None
    largest_class_lines: int = 0
    longest_file: Optional[str] = None
    longest_file_lines: int = 0

    # Maintainability
    overall_docstring_coverage: float = 0.0
    comment_ratio: float = 0.0

    # Duplication
    total_duplicate_lines: int = 0
    total_duplicate_blocks: int = 0

    # Arch
    total_classes: int = 0
    total_functions: int = 0
    total_methods: int = 0

    def aggregate(self) -> RepositoryMetrics:
        """Recompute all aggregate fields from the file list."""
        if not self.files:
            return self

        self.total_files = len(self.files)
        self.total_lines = sum(f.lines for f in self.files)
        self.total_code_lines = sum(f.code_lines for f in self.files)
        self.total_comment_lines = sum(f.comment_lines for f in self.files)

        all_functions: list[FunctionMetrics] = []
        all_classes: list[ClassMetrics] = []
        total_docstring_ratio = 0.0
        files_with_functions = 0

        for fm in self.files:
            all_functions.extend(fm.functions)
            all_classes.extend(fm.classes)
            if fm.functions:
                files_with_functions += 1
                total_docstring_ratio += fm.docstring_coverage

        self.total_symbols = len(all_functions) + len(all_classes)

        # Complexity
        if all_functions:
            self.average_complexity = sum(f.cyclomatic_complexity for f in all_functions) / len(all_functions)
            worst = max(all_functions, key=lambda f: f.cyclomatic_complexity)
            self.worst_function = worst.qualified_name
            self.worst_function_complexity = worst.cyclomatic_complexity
            self.worst_function_file = worst.file

            self.average_function_length = sum(f.lines for f in all_functions) / len(all_functions)
        else:
            self.average_function_length = 0.0

        # Largest class
        if all_classes:
            largest = max(all_classes, key=lambda c: c.lines)
            self.largest_class = largest.qualified_name
            self.largest_class_lines = largest.lines

        # Longest file
        if self.files:
            longest = max(self.files, key=lambda f: f.lines)
            self.longest_file = longest.path
            self.longest_file_lines = longest.lines

        # Maintainability
        if files_with_functions > 0:
            self.overall_docstring_coverage = total_docstring_ratio / files_with_functions
        if self.total_lines > 0:
            self.comment_ratio = self.total_comment_lines / max(self.total_lines, 1)

        # Duplication
        self.total_duplicate_lines = sum(f.duplicate_lines for f in self.files)
        self.total_duplicate_blocks = sum(f.duplicate_blocks for f in self.files)

        # Counts
        self.total_classes = len(all_classes)
        self.total_functions = len([f for f in all_functions if "." not in f.qualified_name])
        self.total_methods = len([f for f in all_functions if "." in f.qualified_name])

        return self
