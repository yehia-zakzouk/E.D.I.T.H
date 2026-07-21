"""Autonomous Engine — the top-level orchestrator for Sprint 9.

Runs the full autonomous improvement pipeline:

    Repository → Review → Find Opportunities → Generate Improvements →
    Create Patches → Review Patches → Safety Check → Predict Impact → Report

Usage::

    from app.autonomous import AutonomousEngine

    engine = AutonomousEngine()
    result = engine.improve(project)
    print(result.text_report())

    # Or just find opportunities without generating patches:
    opportunities = engine.find_opportunities(project)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import config, logger
from app.models.project import Project
from app.models.file_index import FileIndex

from app.review.review_engine import ReviewEngine
from app.autonomous.models import (
    Opportunity,
    OpportunityType,
    OpportunitySeverity,
    Patch,
    PatchStatus,
    ImprovementResult,
    RefactoredCode,
)
from app.autonomous.opportunity_engine import OpportunityEngine
from app.autonomous.refactor_generator import RefactorGenerator
from app.autonomous.patch_generator import PatchGenerator
from app.autonomous.patch_review import PatchReviewer
from app.autonomous.safety_engine import SafetyEngine
from app.autonomous.impact_predictor import ImpactPredictor


class AutonomousEngine:
    """Top-level orchestrator for EDITH's autonomous improvement pipeline.

    Orchestrates the full Sprint 9 pipeline:

    1. Run the Review Engine to get baseline scores
    2. Find improvement opportunities (9.1)
    3. Generate refactored code (9.2)
    4. Create unified diff patches (9.3)
    5. Score patches against the original code (9.4)
    6. Run safety checks — only allow genuine improvements (9.5)
    7. Predict the impact of each patch (9.6)
    8. Return a comprehensive ImprovementResult

    Usage::

        engine = AutonomousEngine()
        result = engine.improve(project)
        print(result.text_report())

        # Apply a specific patch:
        for patch in result.patches:
            if patch.status == PatchStatus.SAFE:
                Path(patch.file_path).write_text(patch.new_code)
    """

    def __init__(
        self,
        max_opportunities: int = 50,
        use_llm: bool = True,
        auto_safety_check: bool = True,
    ):
        self._review_engine = ReviewEngine()
        self._opportunity_engine = OpportunityEngine()
        self._refactor_generator = RefactorGenerator(use_llm=use_llm)
        self._patch_generator = PatchGenerator()
        self._patch_reviewer = PatchReviewer()
        self._safety_engine = SafetyEngine() if auto_safety_check else None
        self._impact_predictor = ImpactPredictor()
        self._max_opportunities = max_opportunities
        self._use_llm = use_llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_opportunities(self, project: Project) -> list[Opportunity]:
        """Find improvement opportunities without generating patches.

        Args:
            project: A fully analyzed Project.

        Returns:
            A list of Opportunity objects, sorted by severity.
        """
        return self._opportunity_engine.find_opportunities(
            project,
            max_opportunities=self._max_opportunities,
        )

    def improve(self, project: Project) -> ImprovementResult:
        """Run the full autonomous improvement pipeline.

        Args:
            project: A fully analyzed Project (must have indexed_files).

        Returns:
            An ImprovementResult with opportunities, patches, scores, and predictions.
        """
        logger.info("AutonomousEngine: starting improvement pipeline for %s", project.root.name)

        result = ImprovementResult(
            project_path=str(project.root),
            project_name=project.root.name,
        )

        # ── Step 0: Baseline review score ──────────────────────────
        logger.info("AutonomousEngine: computing baseline review score")
        try:
            baseline_report = self._review_engine.review(project)
            result.overall_score_before = baseline_report.score.overall
        except Exception as e:
            logger.warning("AutonomousEngine: baseline review failed (non-fatal): %s", e)
            result.overall_score_before = 50.0

        # ── Step 1: Find opportunities ─────────────────────────────
        logger.info("AutonomousEngine: finding opportunities")
        opportunities = self.find_opportunities(project)
        result.opportunities = opportunities
        result.total_opportunities = len(opportunities)

        if not opportunities:
            logger.info("AutonomousEngine: no opportunities found — nothing to improve")
            result.overall_score_after = result.overall_score_before
            return result

        # ── Step 2: Generate refactored code for each opportunity ──
        logger.info("AutonomousEngine: generating refactored code for %d opportunities", len(opportunities))
        refactored_codes: list[RefactoredCode] = []

        # Pre-read source files
        file_sources: dict[str, str] = {}
        for fi in project.indexed_files:
            if fi.analysis is None:
                continue
            try:
                file_sources[str(fi.path)] = fi.path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        for opp in opportunities:
            # Skip architecture-level and project-level opportunities (can't patch single file)
            if opp.type in (
                OpportunityType.ARCHITECTURE_VIOLATION,
                OpportunityType.DUPLICATION,
            ):
                continue

            source = file_sources.get(opp.file_path)
            if source is None:
                continue

            try:
                refactored = self._refactor_generator.refactor(opp, source)
                if refactored is not None:
                    refactored_codes.append(refactored)
                    opp.refactored_code = refactored.refactored_code
            except Exception as e:
                logger.warning(
                    "AutonomousEngine: refactoring failed for %s:%s — %s",
                    opp.file_path,
                    opp.symbol_name,
                    e,
                )

        # ── Step 3: Generate patches ────────────────────────────────
        logger.info("AutonomousEngine: generating patches from %d refactorings", len(refactored_codes))
        patches = self._patch_generator.generate(opportunities, refactored_codes, file_sources)
        result.patches = patches
        result.total_patches_generated = len(patches)

        if not patches:
            logger.info("AutonomousEngine: no patches generated")
            result.overall_score_after = result.overall_score_before
            return result

        # ── Step 4: Score patches ──────────────────────────────────
        logger.info("AutonomousEngine: scoring %d patches", len(patches))
        patches = self._patch_reviewer.review(patches)

        # ── Step 5: Safety check ───────────────────────────────────
        if self._safety_engine is not None:
            logger.info("AutonomousEngine: running safety checks")
            safe_patches, rejected_patches = self._safety_engine.filter(patches)
            result.total_safe_patches = len(safe_patches)
            result.total_regressions = len(rejected_patches)

        # ── Step 6: Predict impact ─────────────────────────────────
        logger.info("AutonomousEngine: predicting impact for %d patches", len(patches))
        patches = self._impact_predictor.predict(patches)

        # ── Step 7: Compute final score ────────────────────────────
        # Estimate the overall score after applying all safe patches
        score_delta = sum(
            p.score_delta for p in patches if p.status in (PatchStatus.SAFE, PatchStatus.IMPROVES)
        )
        result.overall_score_after = result.overall_score_before + score_delta

        # Cap at 100
        result.overall_score_after = max(0, min(100, result.overall_score_after))

        logger.info(
            "AutonomousEngine: pipeline complete — "
            "%d opportunities, %d patches, %d safe, %d regressions, "
            "score %.1f → %.1f",
            result.total_opportunities,
            result.total_patches_generated,
            result.total_safe_patches,
            result.total_regressions,
            result.overall_score_before,
            result.overall_score_after,
        )

        return result

    def improve_with_source(
        self,
        project: Project,
        file_path: str,
        source_code: str,
    ) -> ImprovementResult:
        """Run the improvement pipeline on a single file's source code.

        Useful for testing or for improving individual files without
        re-scanning the entire project.

        Args:
            project: The parent project context.
            file_path: Virtual or real file path for this code.
            source_code: The full source code to analyze and improve.

        Returns:
            An ImprovementResult for this single-file improvement.
        """
        # Create a synthetic FileIndex for the opportunity engine
        from app.models.file_index import FileIndex
        from pathlib import Path

        fi = FileIndex(path=Path(file_path))
        fi.lines = len(source_code.splitlines()) if source_code else 0

        # Run the opportunity engine on this synthetic file
        temp_project = project
        temp_project.indexed_files = [fi]

        result = self.improve(temp_project)

        return result
