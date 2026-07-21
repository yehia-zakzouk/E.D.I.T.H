"""Pattern Engine (Sprint 8.5) — mines statistical patterns from EDITH's
decision history and knowledge base.

No machine learning is required — just simple statistics:
    - Count-based: "FastAPI + SQLAlchemy → DI preferred 8/10 times"
    - Ratio-based: "Users choose maintainability 72% of the time"
    - Correlation: "Projects with low docstring coverage also have high complexity"
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.history.decision_history import DecisionHistory
from app.learning.knowledge_base import KnowledgeBase


@dataclass
class Pattern:
    """A discovered engineering pattern."""
    description: str = ""
    confidence: float = 0.0
    sample_count: int = 0
    evidence: list[str] = field(default_factory=list)


class PatternEngine:
    """Discovers statistical patterns from EDITH's stored decisions.

    Usage::

        engine = PatternEngine(knowledge_base, decision_history)
        patterns = engine.mine_preferences()
        for p in patterns:
            print(p.description)
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        decision_history: DecisionHistory,
    ):
        self._kb = knowledge_base
        self._dh = decision_history

    # ------------------------------------------------------------------
    # Mining
    # ------------------------------------------------------------------

    def mine_preferences(self) -> list[Pattern]:
        """Mine user preference patterns from decision history."""
        patterns: list[Pattern] = []

        # Count choices by goal type
        goal_counts: dict[str, int] = defaultdict(int)
        chosen_approaches: dict[str, list[str]] = defaultdict(list)

        for problem in self._dh.get_recent_problems(limit=100):
            goal = problem.goal or "unknown"
            goal_counts[goal] += 1

        for goal, count in sorted(goal_counts.items(), key=lambda x: x[1], reverse=True):
            if count >= 3:
                patterns.append(Pattern(
                    description=f"Goal '{goal}' appears {count} times in decision history",
                    confidence=min(0.9, count / 10),
                    sample_count=count,
                ))

        return patterns

    def mine_technology_affinity(self) -> list[Pattern]:
        """Discover technology affinity patterns from knowledge base."""
        patterns: list[Pattern] = []

        # Look at preference-type observations
        prefs = self._kb.get_knowledge_by_category("preference", limit=50)
        if not prefs:
            return patterns

        # Group by topic
        by_topic: dict[str, list] = defaultdict(list)
        for entry in prefs:
            by_topic[entry.topic].append(entry)

        for topic, entries in by_topic.items():
            total = len(entries)
            if total < 2:
                continue

            avg_conf = sum(e.confidence for e in entries) / total
            patterns.append(Pattern(
                description=f"Topic '{topic}' has {total} preference observations "
                           f"(avg confidence: {avg_conf:.1f})",
                confidence=avg_conf,
                sample_count=total,
                evidence=[e.observation for e in entries[:3]],
            ))

        return patterns

    def mine_all(self) -> list[Pattern]:
        """Run all pattern mining strategies."""
        patterns: list[Pattern] = []
        patterns.extend(self.mine_preferences())
        patterns.extend(self.mine_technology_affinity())
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns
