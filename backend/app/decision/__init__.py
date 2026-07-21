"""EDITH Decision Engine — multi-solution analysis pipeline.

Given an engineering problem, EDITH proposes multiple valid implementations,
objectively evaluates them, explains trade-offs, and recommends the best one.

Pipeline
--------
Request → Intent Detector → Context Engine → **Problem Analyzer** →
**Candidate Generator** → **Review Runner** → **Ranking Engine** →
**Trade-off Engine** → **Recommendation** → Prompt Builder → LLM → UI

Sprint 7.3–7.6 delivers the complete pipeline:
    - ``ReviewRunner`` — evaluates each candidate's code through the Review Engine
    - ``RankingEngine`` — ranks candidates by weighted scores with user priorities
    - ``TradeoffEngine`` — side-by-side comparison on every dimension
    - ``RecommendationEngine`` — LLM interprets metrics, doesn't invent them

Usage::

    from app.decision import (
        ProblemAnalyzer, get_generator,
        ReviewRunner, RankingEngine,
        TradeoffEngine, RecommendationEngine,
    )

    analyzer = ProblemAnalyzer()
    problem = analyzer.analyze("Add JWT authentication", project)

    generator = get_generator()
    candidates = generator.generate(problem)

    runner = ReviewRunner()
    candidates = runner.evaluate(candidates)

    ranker = RankingEngine()
    ranking = ranker.rank(candidates, priority="maintainability")

    tradeoffs = TradeoffEngine().analyze(ranking)

    recommendation = RecommendationEngine().recommend(ranking, tradeoffs)
    print(recommendation)
"""

from app.decision.problem import EngineeringProblem, ProblemGoal, ProblemScope, AffectedLayer
from app.decision.candidate import CandidateSolution
from app.decision.problem_analyzer import ProblemAnalyzer
from app.decision.generator import (
    BaseGenerator,
    OpenAIGenerator,
    MockGenerator,
    get_generator,
    GenerationError,
)
from app.decision.review_runner import ReviewRunner
from app.decision.ranking_engine import RankingEngine, RankingResult, RankedCandidate, PRIORITY_PRESETS
from app.decision.tradeoff_engine import TradeoffEngine, TradeoffReport
from app.decision.recommendation import RecommendationEngine

__all__ = [
    # Sprint 7.1
    "EngineeringProblem",
    "ProblemGoal",
    "ProblemScope",
    "AffectedLayer",
    "ProblemAnalyzer",
    # Sprint 7.2
    "CandidateSolution",
    "BaseGenerator",
    "OpenAIGenerator",
    "MockGenerator",
    "get_generator",
    "GenerationError",
    # Sprint 7.3
    "ReviewRunner",
    # Sprint 7.4
    "RankingEngine",
    "RankingResult",
    "RankedCandidate",
    "PRIORITY_PRESETS",
    # Sprint 7.5
    "TradeoffEngine",
    "TradeoffReport",
    # Sprint 7.6
    "RecommendationEngine",
]
