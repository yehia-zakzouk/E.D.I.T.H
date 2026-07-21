"""Engineering Knowledge Base (Sprint 8.4) — EDITH's own memory.

Every time EDITH solves a problem, it stores:
    - The topic (e.g. "authentication")
    - What solutions were proposed
    - Which was chosen and why
    - Average scores
    - Common mistakes

When a new request arrives for a similar topic, EDITH doesn't start from zero.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.config import logger


@dataclass
class KnowledgeEntry:
    """A single piece of engineering knowledge."""
    id: int = 0
    topic: str = ""
    category: str = "general"
    observation: str = ""
    confidence: float = 1.0
    sample_count: int = 1
    pattern_data: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class KnowledgeBase:
    """EDITH's engineering memory — stores and retrieves knowledge about topics.

    Usage::

        kb = KnowledgeBase(connection)
        kb.record_observation("authentication", "Users prefer DI over singletons", confidence=0.8)
        entries = kb.get_knowledge("authentication")
    """

    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    # ------------------------------------------------------------------
    # Record knowledge
    # ------------------------------------------------------------------

    def record_observation(
        self,
        topic: str,
        observation: str,
        category: str = "general",
        confidence: float = 1.0,
        pattern_data: Optional[dict] = None,
    ) -> int:
        """Record a new piece of engineering knowledge.

        If an existing entry for this topic+observation exists, its confidence
        and sample count are updated instead.
        """
        cursor = self.conn.cursor()

        # Check if this observation already exists
        cursor.execute(
            "SELECT id, sample_count, confidence FROM knowledge_entries WHERE topic = ? AND observation = ?",
            (topic.lower(), observation),
        )
        existing = cursor.fetchone()

        if existing:
            new_count = existing["sample_count"] + 1
            new_confidence = min(1.0, existing["confidence"] + 0.1)
            cursor.execute(
                """
                UPDATE knowledge_entries
                SET sample_count = ?, confidence = ?, updated_at = datetime('now'),
                    pattern_data = ?
                WHERE id = ?
                """,
                (new_count, new_confidence, json.dumps(pattern_data or {}), existing["id"]),
            )
            entry_id = existing["id"]
        else:
            cursor.execute(
                """
                INSERT INTO knowledge_entries (topic, category, observation, confidence, pattern_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (topic.lower(), category, observation, confidence, json.dumps(pattern_data or {})),
            )
            entry_id = cursor.lastrowid

        self.conn.commit()
        return entry_id

    def record_solution_preference(
        self,
        topic: str,
        chosen_approach: str,
        rejected_approach: str,
        reason: str = "",
    ) -> None:
        """Record a preference signal (chosen vs rejected approach)."""
        self.record_observation(
            topic=topic,
            observation=f"Prefer {chosen_approach} over {rejected_approach}: {reason}",
            category="preference",
            confidence=0.7,
            pattern_data={
                "chosen": chosen_approach,
                "rejected": rejected_approach,
                "reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # Retrieve knowledge
    # ------------------------------------------------------------------

    def get_knowledge(
        self, topic: str, min_confidence: float = 0.3, limit: int = 20,
    ) -> list[KnowledgeEntry]:
        """Get all knowledge entries for a topic, filtered by confidence."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM knowledge_entries
            WHERE topic = ? AND confidence >= ?
            ORDER BY confidence DESC, sample_count DESC
            LIMIT ?
            """,
            (topic.lower(), min_confidence, limit),
        )
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_knowledge_by_category(
        self, category: str, limit: int = 20,
    ) -> list[KnowledgeEntry]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM knowledge_entries
            WHERE category = ?
            ORDER BY confidence DESC, sample_count DESC
            LIMIT ?
            """,
            (category, limit),
        )
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_top_knowledge(self, limit: int = 20) -> list[KnowledgeEntry]:
        """Get the highest-confidence knowledge across all topics."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM knowledge_entries
            ORDER BY confidence DESC, sample_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_topics(self) -> list[str]:
        """Get all distinct topics in the knowledge base."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT topic FROM knowledge_entries ORDER BY topic")
        return [row["topic"] for row in cursor.fetchall()]

    def get_topic_summary(self, topic: str) -> dict:
        """Get a summary of what EDITH knows about a topic."""
        entries = self.get_knowledge(topic)
        if not entries:
            return {"topic": topic, "entries": 0, "observations": []}

        return {
            "topic": topic,
            "entries": len(entries),
            "average_confidence": round(
                sum(e.confidence for e in entries) / len(entries), 2
            ),
            "observations": [
                {
                    "observation": e.observation,
                    "confidence": e.confidence,
                    "samples": e.sample_count,
                    "category": e.category,
                }
                for e in entries[:10]
            ],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"],
            topic=row["topic"],
            category=row["category"],
            observation=row["observation"],
            confidence=row["confidence"],
            sample_count=row["sample_count"],
            pattern_data=json.loads(row["pattern_data"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
