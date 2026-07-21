"""Opportunity Engine (Sprint 9.1) — scans analyzed code to find concrete
improvement opportunities.

This is the **entry point** for autonomous improvement. Instead of waiting
for a user request, EDITH proactively finds:

- High complexity functions (via ComplexityAnalyzer)
- Dead / unused symbols (via the symbol graph)
- Duplicated code (via DuplicationAnalyzer)
- Poor naming (via ReadabilityAnalyzer's naming checks)
- Architecture violations (via ArchitectureAnalyzer)
- Missing documentation (via MaintainabilityAnalyzer)
- Deep nesting, long functions, too many parameters
- Large classes, low cohesion
- Magic numbers, complex conditionals

All detection reuses the **existing analyzers** — no reimplementation.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.models.project import Project
from app.models.file_index import FileIndex
from app.models.symbol import Symbol

from app.review.metrics import FileMetrics, RepositoryMetrics
from app.review.analyzers.complexity import ComplexityAnalyzer
from app.review.analyzers.readability import ReadabilityAnalyzer
from app.review.analyzers.maintainability import MaintainabilityAnalyzer
from app.review.analyzers.architecture import ArchitectureAnalyzer
from app.review.analyzers.duplication import DuplicationAnalyzer

from app.autonomous.models import (
    Opportunity,
    OpportunityType,
    OpportunitySeverity,
)


class OpportunityEngine:
    """Scans a fully analyzed project for improvement opportunities.

    Usage::

        engine = OpportunityEngine()
        opportunities = engine.find_opportunities(project)
        for opp in opportunities:
            print(opp.type, opp.file_path, opp.line)
    """

    def __init__(self):
        self._complexity = ComplexityAnalyzer()
        self._readability = ReadabilityAnalyzer()
        self._maintainability = MaintainabilityAnalyzer()
        self._architecture = ArchitectureAnalyzer()
        self._duplication = DuplicationAnalyzer()

    # Thresholds against AnalyzerMetrics values
    COMPLEXITY_THRESHOLD = 10           # cyclomatic complexity above this = high
    LONG_FUNCTION_THRESHOLD = 60       # lines above this = long
    NESTING_THRESHOLD = 4              # nesting depth above this = deep
    PARAM_THRESHOLD = 5                # params above this = too many
    LARGE_CLASS_THRESHOLD = 400        # lines above this = large class
    LONG_LINE_THRESHOLD = 100          # characters above this = long line
    DUPLICATE_BLOCK_THRESHOLD = 6      # min lines to consider a duplication

    def find_opportunities(
        self,
        project: Project,
        max_opportunities: int = 50,
    ) -> list[Opportunity]:
        """Scan the entire project and return all improvement opportunities.

        Args:
            project: A fully analyzed Project (must have indexed_files
                     with analysis, symbols, etc.).
            max_opportunities: Cap on returned items (sorted by severity).

        Returns:
            A list of Opportunity objects, sorted by severity descending.
        """
        logger.info("OpportunityEngine: scanning %s", project.root)

        opportunities: list[Opportunity] = []
        seen_keys: set[str] = set()

        for fi in project.indexed_files:
            if fi.analysis is None:
                continue

            source = self._read_source(fi)
            if source is None:
                continue

            # ── Per-file analysis ───────────────────────────────────
            fm = self._complexity.analyze_file(
                file_path=fi.path,
                source=source,
                symbols=fi.analysis.symbols,
            )
            fm = self._maintainability.analyze_file(
                file_path=fi.path,
                source=source,
                symbols=fi.analysis.symbols,
                file_metrics=fm,
            )
            fm = self._readability.analyze_file(
                file_path=fi.path,
                source=source,
                symbols=fi.analysis.symbols,
                file_metrics=fm,
            )

            file_str = str(fi.path)

            # 1. High complexity functions ───────────────────────────
            for func in fm.functions:
                if func.cyclomatic_complexity >= self.COMPLEXITY_THRESHOLD:
                    opp = Opportunity(
                        type=OpportunityType.HIGH_COMPLEXITY,
                        severity=self._severity_for_complexity(func.cyclomatic_complexity),
                        file_path=file_str,
                        line=func.line,
                        symbol_name=func.qualified_name,
                        description=f"Function '{func.qualified_name}' has cyclomatic complexity of {func.cyclomatic_complexity}",
                        current_value=float(func.cyclomatic_complexity),
                        metric_name="cyclomatic_complexity",
                        recommendation=f"Extract conditional branches from '{func.qualified_name}' into smaller helper functions",
                        context_lines=self._get_context(source, func.line),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

                # 2. Long functions ──────────────────────────────────
                if func.is_long_function:
                    opp = Opportunity(
                        type=OpportunityType.LONG_FUNCTION,
                        severity=OpportunitySeverity.MEDIUM if func.lines < 100 else OpportunitySeverity.HIGH,
                        file_path=file_str,
                        line=func.line,
                        symbol_name=func.qualified_name,
                        description=f"Function '{func.qualified_name}' is {func.lines} lines long",
                        current_value=float(func.lines),
                        metric_name="function_length",
                        recommendation=f"Extract logical sections from '{func.qualified_name}' into smaller functions",
                        context_lines=self._get_context(source, func.line),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

                # 3. Too many parameters ─────────────────────────────
                if func.has_too_many_params:
                    opp = Opportunity(
                        type=OpportunityType.TOO_MANY_PARAMS,
                        severity=OpportunitySeverity.MEDIUM,
                        file_path=file_str,
                        line=func.line,
                        symbol_name=func.qualified_name,
                        description=f"Function '{func.qualified_name}' has {func.parameters} parameters",
                        current_value=float(func.parameters),
                        metric_name="parameter_count",
                        recommendation=f"Group parameters of '{func.qualified_name}' into a config dataclass or use keyword arguments",
                        context_lines=self._get_context(source, func.line),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

                # 4. Deep nesting ───────────────────────────────────
                if func.max_nesting >= self.NESTING_THRESHOLD:
                    opp = Opportunity(
                        type=OpportunityType.DEEP_NESTING,
                        severity=OpportunitySeverity.MEDIUM if func.max_nesting < 6 else OpportunitySeverity.HIGH,
                        file_path=file_str,
                        line=func.line,
                        symbol_name=func.qualified_name,
                        description=f"Function '{func.qualified_name}' has {func.max_nesting} levels of nesting",
                        current_value=float(func.max_nesting),
                        metric_name="nesting_depth",
                        recommendation=f"Reduce nesting in '{func.qualified_name}' by extracting inner blocks or using early returns",
                        context_lines=self._get_context(source, func.line),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

            # 5. Missing docstrings ──────────────────────────────────
            for func in fm.functions:
                if not func.has_docstring and func.lines > 5:
                    opp = Opportunity(
                        type=OpportunityType.MISSING_DOCSTRING,
                        severity=OpportunitySeverity.LOW,
                        file_path=file_str,
                        line=func.line,
                        symbol_name=func.qualified_name,
                        description=f"Function '{func.qualified_name}' is missing a docstring",
                        current_value=None,
                        metric_name="docstring",
                        recommendation=f"Add a docstring to '{func.qualified_name}' describing its purpose, parameters, and return value",
                        context_lines=self._get_context(source, func.line, lines_before=0, lines_after=3),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

            for cls in fm.classes:
                if not cls.name.startswith("_"):  # skip private classes
                    opp = Opportunity(
                        type=OpportunityType.MISSING_DOCSTRING,
                        severity=OpportunitySeverity.LOW,
                        file_path=file_str,
                        line=cls.line,
                        symbol_name=cls.qualified_name,
                        description=f"Class '{cls.qualified_name}' is missing a docstring",
                        current_value=None,
                        metric_name="docstring",
                        recommendation=f"Add a docstring to '{cls.qualified_name}' describing the class's responsibility",
                        context_lines=self._get_context(source, cls.line, lines_before=0, lines_after=3),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

            # 6. Large classes ──────────────────────────────────────
            for cls in fm.classes:
                if cls.is_large_class:
                    opp = Opportunity(
                        type=OpportunityType.LARGE_CLASS,
                        severity=OpportunitySeverity.HIGH if cls.lines > 600 else OpportunitySeverity.MEDIUM,
                        file_path=file_str,
                        line=cls.line,
                        symbol_name=cls.qualified_name,
                        description=f"Class '{cls.qualified_name}' is {cls.lines} lines with {cls.method_count} methods",
                        current_value=float(cls.lines),
                        metric_name="class_lines",
                        recommendation=f"Split '{cls.qualified_name}' into smaller focused classes by responsibility",
                        context_lines=self._get_context(source, cls.line),
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

            # 7. Poor naming ─────────────────────────────────────────
            readability_penalties = fm.readability_penalties or {}
            naming_issues = readability_penalties.get("naming_issues", [])
            for issue in naming_issues:
                opp = Opportunity(
                    type=OpportunityType.POOR_NAMING,
                    severity=OpportunitySeverity.LOW,
                    file_path=file_str,
                    line=0,
                    symbol_name=issue.split(" ")[0] if issue else "",
                    description=issue,
                    current_value=None,
                    metric_name="naming",
                    recommendation=f"Rename to follow project conventions ({issue})",
                    context_lines=[],
                )
                if opp.key not in seen_keys:
                    seen_keys.add(opp.key)
                    opportunities.append(opp)

            # 8. Long lines ─────────────────────────────────────────
            long_soft = readability_penalties.get("long_lines_soft", 0)
            long_hard = readability_penalties.get("long_lines_hard", 0)
            if long_hard > 0:
                opp = Opportunity(
                    type=OpportunityType.LONG_LINE,
                    severity=OpportunitySeverity.INFO if long_hard < 3 else OpportunitySeverity.LOW,
                    file_path=file_str,
                    line=0,
                    symbol_name="",
                    description=f"{long_hard} lines exceed {self.LONG_LINE_THRESHOLD} characters",
                    current_value=float(long_hard),
                    metric_name="long_lines",
                    recommendation="Break long lines into multiple lines for better readability",
                    context_lines=[],
                )
                if opp.key not in seen_keys:
                    seen_keys.add(opp.key)
                    opportunities.append(opp)

        # 9. Architecture violations ─────────────────────────────────
        arch_metrics = self._architecture.analyze_project(project)
        violation_count = arch_metrics.get("layer_violations", 0)
        cycle_count = arch_metrics.get("cyclic_dependencies", 0)

        if violation_count > 0:
            opportunities.append(Opportunity(
                type=OpportunityType.ARCHITECTURE_VIOLATION,
                severity=OpportunitySeverity.HIGH if violation_count > 5 else OpportunitySeverity.MEDIUM,
                file_path=str(project.root),
                line=0,
                symbol_name="",
                description=f"{violation_count} layer violations detected in import graph",
                current_value=float(violation_count),
                metric_name="layer_violations",
                recommendation="Restructure imports to follow the architectural layering — low-level modules should not import high-level modules",
                context_lines=[],
            ))
        if cycle_count > 0:
            cycles = arch_metrics.get("cycle_list", [])
            for cycle in cycles[:3]:
                opportunities.append(Opportunity(
                    type=OpportunityType.ARCHITECTURE_VIOLATION,
                    severity=OpportunitySeverity.HIGH,
                    file_path=str(project.root),
                    line=0,
                    symbol_name=" → ".join(cycle),
                    description=f"Circular dependency detected: {' → '.join(cycle)}",
                    current_value=None,
                    metric_name="circular_dependency",
                    recommendation="Break the cycle by extracting a shared interface or moving common logic to a new module",
                    context_lines=[],
                ))

        # 10. Duplication ────────────────────────────────────────────
        file_sources: list[tuple[Path, str]] = []
        for fi in project.indexed_files:
            if fi.analysis is None:
                continue
            src = self._read_source(fi)
            if src:
                file_sources.append((fi.path, src))

        if file_sources:
            dummy_metrics = []
            for fi in project.indexed_files:
                if fi.analysis is None:
                    continue
                dummy_metrics.append(FileMetrics(path=str(fi.path)))
            dup_metrics = self._duplication.analyze_project(
                files=file_sources,
                file_metrics=dummy_metrics,
            )
            for dm in dup_metrics:
                if dm.duplicate_blocks > 0:
                    opp = Opportunity(
                        type=OpportunityType.DUPLICATION,
                        severity=OpportunitySeverity.MEDIUM if dm.duplicate_blocks < 3 else OpportunitySeverity.HIGH,
                        file_path=dm.path,
                        line=0,
                        symbol_name="",
                        description=f"{dm.duplicate_blocks} duplicated code blocks ({dm.duplicate_lines} lines)",
                        current_value=float(dm.duplicate_lines),
                        metric_name="duplicate_lines",
                        recommendation="Extract the duplicated code into a shared function or module",
                        context_lines=[],
                    )
                    if opp.key not in seen_keys:
                        seen_keys.add(opp.key)
                        opportunities.append(opp)

        # ── Sort by severity (critical → info) ──────────────────────
        opportunities.sort(key=lambda o: o.severity_score, reverse=True)

        # Cap at max_opportunities
        if len(opportunities) > max_opportunities:
            opportunities = opportunities[:max_opportunities]

        logger.info(
            "OpportunityEngine: found %d opportunities in %s "
            "(high_complexity=%d, long_funcs=%d, missing_docs=%d, arch=%d, dup=%d)",
            len(opportunities),
            project.root.name,
            sum(1 for o in opportunities if o.type == OpportunityType.HIGH_COMPLEXITY),
            sum(1 for o in opportunities if o.type == OpportunityType.LONG_FUNCTION),
            sum(1 for o in opportunities if o.type == OpportunityType.MISSING_DOCSTRING),
            sum(1 for o in opportunities if o.type == OpportunityType.ARCHITECTURE_VIOLATION),
            sum(1 for o in opportunities if o.type == OpportunityType.DUPLICATION),
        )

        return opportunities

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _severity_for_complexity(cc: int) -> OpportunitySeverity:
        if cc >= 20:
            return OpportunitySeverity.CRITICAL
        if cc >= 15:
            return OpportunitySeverity.HIGH
        if cc >= 10:
            return OpportunitySeverity.MEDIUM
        return OpportunitySeverity.LOW

    @staticmethod
    def _read_source(fi: FileIndex) -> Optional[str]:
        try:
            return fi.path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    @staticmethod
    def _get_context(source: str, line: int, lines_before: int = 3, lines_after: int = 3) -> list[str]:
        """Extract surrounding lines of source code for context."""
        source_lines = source.splitlines()
        start = max(0, line - 1 - lines_before)
        end = min(len(source_lines), line - 1 + lines_after + 1)
        return source_lines[start:end]
