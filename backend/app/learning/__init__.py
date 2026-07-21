"""EDITH Learning Package (Sprint 8.4–8.6) — EDITH builds engineering
knowledge over time through pattern mining, statistics, and personalization.

Packages
--------
learning/
    knowledge_base.py         — Engineering memory (8.4)
    pattern_engine.py         — Statistical pattern mining (8.5)
    recommendation_memory.py  — Personalization & memory (8.6, 8.9)
    statistics.py             — Stats utilities
"""

from app.learning.knowledge_base import KnowledgeBase
from app.learning.pattern_engine import PatternEngine
from app.learning.recommendation_memory import RecommendationMemory

__all__ = ["KnowledgeBase", "PatternEngine", "RecommendationMemory"]
