"""EDITH Autonomous Engineering — Sprint 9.

EDITH improves code autonomously, not just analyzes it.

Pipeline
--------
Repository → Review → Opportunity Engine → Find Weaknesses →
Refactor Generator → Generate Improvements →
Patch Generator → Create Diffs →
Patch Review → Score Patches →
Safety Engine → Validate Improvements →
Impact Predictor → Estimate Impact →
Present Patches → User Approves

Usage::

    from app.autonomous import AutonomousEngine

    engine = AutonomousEngine()
    result = engine.improve(project)
    print(result.summary())
    for patch in result.patches:
        print(patch.diff)
"""

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
from app.autonomous.orchestrator import AutonomousEngine

__all__ = [
    # Models
    "Opportunity",
    "OpportunityType",
    "OpportunitySeverity",
    "Patch",
    "PatchStatus",
    "ImprovementResult",
    "RefactoredCode",
    # Components
    "OpportunityEngine",
    "RefactorGenerator",
    "PatchGenerator",
    "PatchReviewer",
    "SafetyEngine",
    "ImpactPredictor",
    # Orchestrator
    "AutonomousEngine",
]
