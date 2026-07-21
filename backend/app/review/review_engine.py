"""Review Engine — the main orchestrator for EDITH's code-review pipeline.

Pipeline
--------
1. For each file → run ComplexityAnalyzer, then enrich with Maintainability
   and Readability analyzers.
2. Across all files → run ArchitectureAnalyzer and DuplicationAnalyzer.
3. Aggregate per-file metrics into RepositoryMetrics.
4. Run the ScoringEngine → ReviewScore.
5. Generate a ReviewReport (text + structured).
6. (Optional) Feed the report to an LLM for natural-language interpretation.

Usage::

    from app.review.review_engine import ReviewEngine

    engine = ReviewEngine()
    report = engine.review(project)

    print(report.text)           # formatted text report
    print(report.score.overall)  # 0–100 score
    print(report.to_dict())      # structured dict for LLM
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import config, logger
from app.models.project import Project
from app.models.file_index import FileIndex

from app.review.metrics import FileMetrics, RepositoryMetrics
from app.review.analyzers.complexity import ComplexityAnalyzer
from app.review.analyzers.maintainability import MaintainabilityAnalyzer
from app.review.analyzers.readability import ReadabilityAnalyzer
from app.review.analyzers.architecture import ArchitectureAnalyzer
from app.review.analyzers.duplication import DuplicationAnalyzer
from app.review.scoring import ScoringEngine, ReviewScore
from app.review.report import ReviewReport, ReportGenerator


# Sentinel for lazy-loading the LLM provider
_NO_PROVIDER = object()


class ReviewEngine:
    """Orchestrates the full engineering review pipeline.

    Parameters
    ----------
    use_llm : bool
        Whether to enhance the review with an LLM interpretation.
    """

    def __init__(
        self,
        use_llm: bool = False,
        weights: Optional[dict[str, float]] = None,
    ):
        self._complexity = ComplexityAnalyzer()
        self._maintainability = MaintainabilityAnalyzer()
        self._readability = ReadabilityAnalyzer()
        self._architecture = ArchitectureAnalyzer()
        self._duplication = DuplicationAnalyzer()
        self._scoring = ScoringEngine(weights=weights)
        self._report_gen = ReportGenerator()
        self._use_llm = use_llm
        self._provider = _NO_PROVIDER

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review(self, project: Project) -> ReviewReport:
        """Run the full review pipeline on a project.

        Args:
            project: A fully analyzed Project (must have indexed_files
                     with analysis data).

        Returns:
            A ReviewReport with scores, metrics, text, and recommendations.
        """
        logger.info("Starting engineering review for %s", project.root.name)

        if not project.indexed_files:
            return self._empty_report(project.root.name)

        # ---- Phase 1: Per-file analysis ----
        file_metrics_list: list[FileMetrics] = []
        file_sources: list[tuple[Path, str]] = []

        for fi in project.indexed_files:
            if fi.analysis is None:
                continue

            source = self._read_source(fi)
            if source is None:
                continue

            # 1a. Complexity analysis
            fm = self._complexity.analyze_file(
                file_path=fi.path,
                source=source,
                symbols=fi.analysis.symbols,
            )

            # 1b. Maintainability
            fm = self._maintainability.analyze_file(
                file_path=fi.path,
                source=source,
                symbols=fi.analysis.symbols,
                file_metrics=fm,
            )

            # 1c. Readability
            fm = self._readability.analyze_file(
                file_path=fi.path,
                source=source,
                symbols=fi.analysis.symbols,
                file_metrics=fm,
            )

            file_metrics_list.append(fm)
            file_sources.append((fi.path, source))

        # ---- Phase 2: Cross-file analysis ----
        # 2a. Duplication (requires all sources)
        file_metrics_list = self._duplication.analyze_project(
            files=file_sources,
            file_metrics=file_metrics_list,
        )

        # 2b. Architecture (requires the full project)
        arch_metrics = self._architecture.analyze_project(project)

        # ---- Phase 3: Aggregation ----
        repo_metrics = RepositoryMetrics(files=file_metrics_list)
        repo_metrics.aggregate()

        # ---- Phase 4: Scoring ----
        score = self._scoring.score(repo_metrics)

        # ---- Phase 5: Report ----
        report = self._report_gen.generate(
            project_name=project.root.name,
            metrics=repo_metrics,
            score=score,
        )

        # ---- Phase 6: (Optional) LLM enhancement ----
        if self._use_llm:
            report = self._enhance_with_llm(report)

        logger.info(
            "Review complete: score=%s, strengths=%d, weaknesses=%d",
            report.score.overall,
            len(report.score.strengths),
            len(report.score.weaknesses),
        )

        return report

    def score_only(self, project: Project) -> ReviewScore:
        """Run the pipeline but return only the score (cheaper)."""
        report = self.review(project)
        return report.score

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_source(self, fi: FileIndex) -> Optional[str]:
        """Read the source text of a file, returning None on failure."""
        try:
            return fi.path.read_text(
                encoding=config.parser.encoding,
                errors=config.parser.errors,
            )
        except Exception:
            logger.warning("Could not read %s — skipping", fi.path)
            return None

    def _empty_report(self, project_name: str) -> ReviewReport:
        """Return a minimal report when there's nothing to review."""
        metrics = RepositoryMetrics()
        metrics.aggregate()
        score = self._scoring.score(metrics)
        return self._report_gen.generate(
            project_name=project_name,
            metrics=metrics,
            score=score,
        )

    def _enhance_with_llm(self, report: ReviewReport) -> ReviewReport:
        """Feed the structured report to an LLM for enhanced interpretation.

        This method augments the basic analysis with AI-generated insights.
        """
        # Lazy-init the provider
        if self._provider is _NO_PROVIDER:
            self._provider = self._create_provider()

        if self._provider is None:
            return report  # no provider available, return as-is

        prompt = self._build_llm_prompt(report)

        try:
            llm_response = self._provider.ask(prompt)

            # Append LLM insights to the report text
            if llm_response and llm_response.strip():
                report.text += "\n\n" + "=" * 55 + "\n"
                report.text += "  AI INSIGHTS\n"
                report.text += "=" * 55 + "\n\n"
                report.text += llm_response.strip() + "\n"
        except Exception:
            logger.exception("LLM enhancement failed (non-fatal)")

        return report

    def _build_llm_prompt(self, report: ReviewReport) -> str:
        """Build a prompt for the LLM to interpret review results."""
        d = report.to_dict()

        prompt = f"""You are EDITH's AI review interpreter. Given the following engineering metrics, provide an expert analysis.

Project: {d['project']}
Overall Score: {d['overall_score']}/100 ({d['rating']})

Dimension Scores:
"""
        for dim in d["dimensions"]:
            prompt += f"  - {dim['name']}: {dim['score']}/100 ({dim['rating']})\n"

        prompt += f"""
Strengths:
{chr(10).join('  - ' + s for s in d['strengths'])}

Weaknesses:
{chr(10).join('  - ' + w for w in d['weaknesses'])}

Metrics:
{chr(10).join(f'  - {k}: {v}' for k, v in d['metrics'].items() if v is not None)}

Please provide:
1. A brief executive summary (2-3 sentences)
2. The top 3 most impactful changes the team should prioritize
3. Any context-specific insights based on the metrics

Be specific, constructive, and actionable. Assume the team is competent and wants concrete guidance.
"""
        return prompt

    @staticmethod
    def _create_provider():
        """Try to create an AI provider for LLM enhancement.

        Delegates to ``create_provider`` from ``app.main`` to avoid
        duplicating the shared provider-creation logic.
        """
        try:
            from app.main import create_provider as _create
            return _create()
        except Exception:
            logger.debug("Could not create AI provider (is EDITH running as a library?)")
            # Fallback: try directly
            try:
                api_key = config.ai.api_key
                if api_key:
                    from app.ai.openai_provider import OpenAIProvider
                    return OpenAIProvider()
            except Exception:
                pass
            return None
