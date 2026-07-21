"""Problem Analyzer — the first stage of EDITH's multi-solution pipeline.

Transforms free-text engineering requests into structured ``EngineeringProblem``
objects. Everything downstream (generator, reviewer, ranker, LLM) reads
this structured representation instead of raw text.

Design principles
-----------------
1. **No LLM call** — classification uses keyword/pattern matching and
   project context, keeping latency under 10 ms.
2. **Deterministic** — same question + same project = same problem.
   Determinism lets us cache, compare, and test.
3. **Extensible** — new goals, scopes, and layers can be added by
   extending the pattern lists.
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.config import logger
from app.models.project import Project
from app.models.file_index import FileIndex
from app.ai.context_engine import _extract_keywords as _shared_extract_keywords

from app.decision.problem import (
    EngineeringProblem,
    ProblemGoal,
    ProblemScope,
    AffectedLayer,
)


# ------------------------------------------------------------------
# Goal patterns — ordered from most specific to most general
# ------------------------------------------------------------------

_GOAL_PATTERNS: list[tuple[list[str], ProblemGoal]] = [
    # BUG_FIX — check before REFACTOR since "fix" might also match
    (["bug", "bugfix", "bug fix", "fix bug", "crash", "broken",
      "error occurs", "failing", "doesn't work", "not working",
      "incorrect", "wrong result", "issue"], ProblemGoal.BUG_FIX),

    # PERFORMANCE_OPTIMIZATION
    (["optimize", "optimization", "faster", "performance", "slow",
      "speed up", "bottleneck", "latency", "memory leak",
      "cpu usage", "throughput", "inefficient"], ProblemGoal.PERFORMANCE_OPTIMIZATION),

    # NEW_FEATURE — checked before SECURITY so "Add JWT auth" → NEW_FEATURE (not security fix)
    (["add ", "implement ", "create ", "build ",
      "new feature", "new endpoint", "new api", "new command",
      "introduce", "support for", "ability to"], ProblemGoal.NEW_FEATURE),

    # SECURITY_IMPROVEMENT
    (["vulnerability", "xss", "csrf", "sql injection", "encrypt",
      "hash password", "fix security", "security fix",
      "security issue", "security hole", "hardening"], ProblemGoal.SECURITY_IMPROVEMENT),

    # TEST_IMPROVEMENT
    (["test", "unit test", "integration test", "test coverage",
      "spec", "assertion", "pytest", "unittest"], ProblemGoal.TEST_IMPROVEMENT),

    # REFACTOR
    (["refactor", "restructure", "clean up", "cleanup", "reorganize",
      "simplify", "reduce duplication", "extract", "inline",
      "improve code", "technical debt", "rework"], ProblemGoal.REFACTOR),

    # ARCHITECTURE_CHANGE
    (["architecture", "redesign", "re-architect", "modularize",
      "decouple", "split", "migrate to"], ProblemGoal.ARCHITECTURE_CHANGE),

    # DEPENDENCY_UPDATE
    (["update dependency", "upgrade", "downgrade", "bump version",
      "new version", "outdated", "replace library", "migrate from"],
     ProblemGoal.DEPENDENCY_UPDATE),

    # DOCUMENTATION
    (["document", "docstring", "README", "documentation", "comment",
      "describe", "explain code", "write docs"], ProblemGoal.DOCUMENTATION),

    # CODE_REVIEW
    (["review", "code quality", "code smell", "review this"], ProblemGoal.CODE_REVIEW),
]


# ------------------------------------------------------------------
# Scope patterns
# ------------------------------------------------------------------

_SCOPE_PATTERNS: list[tuple[list[str], ProblemScope]] = [
    (["function ", "method ", "this function", "this method",
      "optimize this", "refactor this"], ProblemScope.SINGLE_FUNCTION),
    (["file ", "class ", "this file", "this class",
      "single file", "one file"], ProblemScope.SINGLE_FILE),
    (["module ", "package ", "component"], ProblemScope.MODULE),
    (["architecture", "entire project", "whole project",
      "restructure", "reorganize all"], ProblemScope.ARCHITECTURE_WIDE),
]


# ------------------------------------------------------------------
# Layer detection keywords
# ------------------------------------------------------------------

_LAYER_KEYWORDS: list[tuple[list[str], AffectedLayer]] = [
    (["api", "endpoint", "route", "rest", "graphql", "handler"], AffectedLayer.API),
    (["database", "db", "sql", "orm", "query", "model", "schema",
      "migration", "table", "collection"], AffectedLayer.DATABASE),
    (["model", "entity", "dto", "data class"], AffectedLayer.MODELS),
    (["service", "business logic", "use case"], AffectedLayer.SERVICES),
    (["middleware", "interceptor", "filter", "hook",
      "event bus", "pipeline"], AffectedLayer.MIDDLEWARE),
    (["config", "env", "setting", "environment"], AffectedLayer.CONFIGURATION),
    (["test", "spec", "pytest", "unittest"], AffectedLayer.TESTS),
    (["deploy", "docker", "ci", "cd", "kubernetes", "helm"], AffectedLayer.DEPLOYMENT),
    (["doc", "readme", "documentation"], AffectedLayer.DOCUMENTATION),
    (["ui", "frontend", "template", "component"], AffectedLayer.UI),
    (["auth", "secure", "permission", "oauth", "jwt"], AffectedLayer.SECURITY),
]


# ------------------------------------------------------------------
# Complexity/risk heuristics
# ------------------------------------------------------------------

_COMPLEXITY_HIGH_KEYWORDS = [
    "complex", "large", "difficult", "massive", "many files",
    "multiple modules", "all", "entire",
]

_RISK_HIGH_KEYWORDS = [
    "critical", "production", "breaking", "migration",
    "security", "auth", "data loss", "downtime",
]


class ProblemAnalyzer:
    """Classifies user engineering requests into structured problems.

    Usage::

        analyzer = ProblemAnalyzer()
        problem = analyzer.analyze("Add JWT authentication", project)

        print(problem.goal.value)      # "new_feature"
        print(problem.complexity)      # "medium"
        print(problem.affected_layers) # [API, SECURITY, DATABASE]
    """

    def analyze(
        self,
        question: str,
        project: Optional[Project] = None,
        target: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> EngineeringProblem:
        """Analyze an engineering request and produce a structured problem.

        Args:
            question: The user's free-text request.
            project: Optional analyzed Project for context-aware classification.
            target: Optional pre-extracted target symbol/file name.
            context: Optional pre-built context dict from ContextEngine
                     (avoid re-searching when reusing existing context).

        Returns:
            An EngineeringProblem populated with classification, scope,
            affected layers, constraints, and relevant files.
        """
        q_lower = question.lower().strip()

        # ── 1. Classify goal ───────────────────────────────────────
        goal = self._detect_goal(q_lower)

        # ── 2. Detect scope ────────────────────────────────────────
        scope = self._detect_scope(q_lower, goal)

        # ── 3. Detect affected layers ──────────────────────────────
        layers = self._detect_layers(q_lower)

        # ── 4. Assess complexity / risk ────────────────────────────
        complexity = self._assess_complexity(q_lower, scope, layers)
        risk = self._assess_risk(q_lower, layers, goal)

        # ── 5. Extract constraints ─────────────────────────────────
        constraints = self._extract_constraints(q_lower, goal)

        # ── 6. Extract preferences ─────────────────────────────────
        preferences = self._extract_preferences(q_lower)

        # ── 7. Gather project context ──────────────────────────────
        proj_langs: list[str] = []
        proj_frameworks: list[str] = []
        build_system: Optional[str] = None
        relevant_files: list[str] = []
        relevant_symbols: list[str] = []

        if project is not None:
            proj_langs = project.languages
            proj_frameworks = project.frameworks
            build_system = project.build_system

            # If context was pre-built, reuse it
            if context and "relevant_files" in context:
                relevant_files = [f["path"] for f in context["relevant_files"][:10]]
                relevant_symbols = context.get("relevant_symbols", [])[:15]
            else:
                # Quick scan: find files whose path/name matches the question
                keywords = _shared_extract_keywords(question, target)
                for fi in project.indexed_files:
                    if fi.analysis is None:
                        continue
                    path_lower = str(fi.path).lower()

                    # Score this file
                    path_score = sum(1 for kw in keywords if kw in path_lower)
                    if path_score > 0:
                        relevant_files.append(str(fi.path))

                    # Check symbol names
                    for sym in fi.analysis.symbols:
                        sym_lower = sym.name.lower()
                        if any(kw in sym_lower for kw in keywords):
                            relevant_symbols.append(sym.qualified_name)

                relevant_files = relevant_files[:10]
                relevant_symbols = relevant_symbols[:15]

        # ── 8. Build reasoning string ──────────────────────────────
        reasoning = self._build_reasoning(goal, scope, layers, complexity, risk)

        # ── 9. Determine must_preserve_behavior ─────────────────────
        must_preserve = not (
            goal in (ProblemGoal.NEW_FEATURE, ProblemGoal.ARCHITECTURE_CHANGE,
                     ProblemGoal.DOCUMENTATION)
        )

        return EngineeringProblem(
            question=question,
            target=target,
            goal=goal,
            scope=scope,
            affected_layers=layers,
            must_preserve_behavior=must_preserve,
            constraints=constraints,
            preferences=preferences,
            complexity=complexity,
            risk=risk,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
            project_languages=proj_langs,
            project_frameworks=proj_frameworks,
            build_system=build_system,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Internal — goal detection
    # ------------------------------------------------------------------

    def _detect_goal(self, q_lower: str) -> ProblemGoal:
        """Classify the overarching goal of the request."""
        for keywords, goal in _GOAL_PATTERNS:
            if any(kw in q_lower for kw in keywords):
                return goal
        return ProblemGoal.GENERAL_QUESTION

    # ------------------------------------------------------------------
    # Internal — scope detection
    # ------------------------------------------------------------------

    def _detect_scope(self, q_lower: str, goal: ProblemGoal) -> ProblemScope:
        """Estimate how broadly the change touches the codebase."""
        for keywords, scope in _SCOPE_PATTERNS:
            if any(kw in q_lower for kw in keywords):
                return scope

        # Default by goal
        if goal == ProblemGoal.PERFORMANCE_OPTIMIZATION:
            return ProblemScope.SINGLE_FUNCTION
        if goal == ProblemGoal.BUG_FIX:
            return ProblemScope.SINGLE_FILE
        if goal in (ProblemGoal.NEW_FEATURE, ProblemGoal.ARCHITECTURE_CHANGE):
            return ProblemScope.MULTIPLE_FILES
        if goal == ProblemGoal.DOCUMENTATION:
            return ProblemScope.MULTIPLE_FILES

        return ProblemScope.SINGLE_FILE

    # ------------------------------------------------------------------
    # Internal — layer detection
    # ------------------------------------------------------------------

    def _detect_layers(self, q_lower: str) -> list[AffectedLayer]:
        """Identify which architectural layers the change touches."""
        detected: set[AffectedLayer] = set()

        for keywords, layer in _LAYER_KEYWORDS:
            if any(kw in q_lower for kw in keywords):
                detected.add(layer)

        if not detected:
            detected.add(AffectedLayer.UNKNOWN)

        return list(detected)

    # ------------------------------------------------------------------
    # Internal — complexity & risk
    # ------------------------------------------------------------------

    def _assess_complexity(
        self,
        q_lower: str,
        scope: ProblemScope,
        layers: list[AffectedLayer],
    ) -> str:
        """Estimate implementation complexity."""
        # High complexity signals
        if scope == ProblemScope.ARCHITECTURE_WIDE:
            return "high"
        if scope == ProblemScope.MODULE and len(layers) > 2:
            return "high"
        if any(kw in q_lower for kw in _COMPLEXITY_HIGH_KEYWORDS):
            return "high"

        # Medium complexity
        if scope in (ProblemScope.MULTIPLE_FILES, ProblemScope.MODULE):
            return "medium"
        if len(layers) > 2:
            return "medium"

        return "low"

    def _assess_risk(
        self,
        q_lower: str,
        layers: list[AffectedLayer],
        goal: ProblemGoal,
    ) -> str:
        """Estimate the risk of this change."""
        # High risk signals
        if goal == ProblemGoal.SECURITY_IMPROVEMENT:
            return "high"
        if AffectedLayer.DATABASE in layers and AffectedLayer.API in layers:
            return "high"
        if any(kw in q_lower for kw in _RISK_HIGH_KEYWORDS):
            return "high"

        # Medium risk
        if goal in (ProblemGoal.ARCHITECTURE_CHANGE, ProblemGoal.DEPENDENCY_UPDATE):
            return "medium"
        if AffectedLayer.MIDDLEWARE in layers:
            return "medium"

        return "low"

    # ------------------------------------------------------------------
    # Internal — constraints & preferences
    # ------------------------------------------------------------------

    def _extract_constraints(self, q_lower: str, goal: ProblemGoal) -> list[str]:
        """Extract explicit constraints from the request."""
        constraints: list[str] = []

        # Must preserve behavior is the default — handled by the caller

        if "without changing" in q_lower or "must not break" in q_lower:
            constraints.append("Must not break existing functionality")

        if "backward compatible" in q_lower:
            constraints.append("Must be backward compatible")

        if "minimal changes" in q_lower or "small change" in q_lower:
            constraints.append("Prefer minimal changes")

        if "no new dependencies" in q_lower:
            constraints.append("No new external dependencies")

        if "compatible with" in q_lower:
            # Extract what it should be compatible with
            match = re.search(r"compatible with (\S+)", q_lower)
            if match:
                constraints.append(f"Must be compatible with {match.group(1)}")

        return constraints

    def _extract_preferences(self, q_lower: str) -> list[str]:
        """Extract user preferences from the request."""
        preferences: list[str] = []

        if "fast" in q_lower or "speed" in q_lower:
            preferences.append("Optimize for performance")

        if "readable" in q_lower or "clear" in q_lower or "simple" in q_lower:
            preferences.append("Optimize for readability")

        if "maintainable" in q_lower:
            preferences.append("Optimize for maintainability")

        if "secure" in q_lower:
            preferences.append("Optimize for security")

        if "minimal" in q_lower or "small" in q_lower:
            preferences.append("Optimize for minimal code changes")

        return preferences

    # ------------------------------------------------------------------
    # Internal — reasoning
    # ------------------------------------------------------------------

    def _build_reasoning(
        self,
        goal: ProblemGoal,
        scope: ProblemScope,
        layers: list[AffectedLayer],
        complexity: str,
        risk: str,
    ) -> str:
        """Generate a human-readable explanation of the classification."""
        parts: list[str] = []

        parts.append(f"Detected goal: {goal.value}")
        parts.append(f"Estimated scope: {scope.value}")

        layer_names = [l.value for l in layers if l != AffectedLayer.UNKNOWN]
        if layer_names:
            parts.append(f"Affected layers: {', '.join(layer_names)}")

        parts.append(f"Complexity: {complexity}")
        parts.append(f"Risk: {risk}")

        return ". ".join(parts)

    # ------------------------------------------------------------------
    # Internal — keyword extraction
    # ------------------------------------------------------------------


