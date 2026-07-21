"""Enhanced Context Engine — the heart of EDITH's AI integration.

Instead of dumping the whole repository into the prompt, the Context Engine:
1. Determines the user's intent (via IntentDetector)
2. Searches symbols, files, and the graph for relevant matches
3. Fetches source code for highly relevant files
4. Returns a structured context dictionary
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import logger
from app.models.project import Project
from app.models.file_analysis import FileAnalysis
from app.models.symbol import Symbol
from app.graph.edges import EdgeType
from app.graph.nodes import NodeType
from app.ai.intent_detector import Intent, IntentDetector
from app.ai.conversation_memory import ConversationMemory


class ContextEngine:
    """Builds a rich, structured context dictionary from the project's
    indexed knowledge (symbols, files, graph) based on a user's question.

    Usage::

        engine = ContextEngine()
        ctx = engine.build_context("explain DatabaseManager", project)
    """

    def __init__(self, memory: Optional[ConversationMemory] = None):
        self._detector = IntentDetector()
        self._memory = memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_context(
        self,
        question: str,
        project: Project,
        intent: Optional[Intent] = None,
        target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a context dictionary for the given question and project.

        Returns a dict with keys:
            question, intent, target,
            relevant_files, relevant_symbols,
            relevant_relationships, source_snippets,
            graph_context, conversation_context
        """
        logger.debug("ContextEngine: building context for '%s'", question)

        # 1. Detect intent if not provided
        if intent is None:
            intent, target = self._detector.detect(question)
        logger.debug("  intent=%s  target=%s", intent.value, target)

        # 2. Gather knowledge from all three stores
        files_and_symbols = self._search_keywords(question, target, project)
        graph_context = self._build_graph_context(files_and_symbols, project)
        relationships = self._find_relationships(files_and_symbols, project)
        source_snippets = self._fetch_snippets(files_and_symbols, project)

        # 3. Build the final context dict
        context: Dict[str, Any] = {
            "question": question,
            "intent": intent.value,
            "target": target,
        }

        # Files & symbols
        if files_and_symbols:
            context["relevant_files"] = [
                {
                    "path": str(f["file"]),
                    "score": f["score"],
                    "symbols": [_symbol_to_dict(s) for s in f["symbols"][:8]],
                }
                for f in files_and_symbols[:15]
            ]
            context["relevant_symbols"] = [
                s.name
                for f in files_and_symbols[:15]
                for s in (f.get("symbols") or [])
            ][:30]

        # Graph
        if graph_context:
            context["graph_context"] = graph_context

        # Relationships
        if relationships:
            context["relevant_relationships"] = relationships[:20]

        # Source code snippets
        if source_snippets:
            context["source_snippets"] = source_snippets[:5]

        # Conversation memory
        if self._memory:
            conv = self._memory.build_context_summary()
            if conv:
                context["conversation_context"] = conv

        # Summary
        context["summary"] = (
            f"Found {len(files_and_symbols)} relevant files, "
            f"{len(context.get('relevant_symbols', []))} relevant symbols, "
            f"{len(relationships)} relationships"
        )

        return context

    # ------------------------------------------------------------------
    # Internal — search
    # ------------------------------------------------------------------

    def _search_keywords(
        self,
        question: str,
        target: Optional[str],
        project: Project,
    ) -> List[Dict[str, Any]]:
        """Score files by how well their symbols/docstrings match the query."""
        keywords = _extract_keywords(question, target)
        if not keywords:
            return []

        scored: List[Dict[str, Any]] = []
        for f in project.indexed_files:
            analysis = f.analysis
            if analysis is None:
                continue

            score = 0
            matched_symbols: list[Symbol] = []

            # Score against module docstring
            if analysis.module_docstring:
                lowered = analysis.module_docstring.lower()
                score += sum(2 for kw in keywords if kw in lowered)

            # Score against each symbol
            for sym in analysis.symbols:
                sym_text = " ".join([
                    sym.name,
                    sym.qualified_name,
                    sym.docstring or "",
                    sym.parent or "",
                ]).lower()

                sym_score = sum(1 for kw in keywords if kw in sym_text)
                if sym_score > 0:
                    score += sym_score * 3  # symbol matches worth more
                    matched_symbols.append(sym)

            # Score imports (a file importing a target is very relevant)
            for imp in analysis.imports:
                if target and target.lower() in imp.lower():
                    score += 5

            if score > 0:
                scored.append({
                    "file": f.path,
                    "score": score,
                    "symbols": matched_symbols,
                    "imports": analysis.imports,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Internal — graph
    # ------------------------------------------------------------------

    def _build_graph_context(
        self,
        scored_files: List[Dict[str, Any]],
        project: Project,
    ) -> Optional[Dict[str, Any]]:
        """Pull a sub-graph of relevant nodes and edges."""
        if not project.graph or not project.graph.nodes:
            return None

        # Collect file paths from scored results
        relevant_paths: set[str] = set()
        for sf in scored_files:
            p = sf["file"]
            relevant_paths.add(str(p))

        # Find nodes belonging to relevant files
        relevant_node_ids: set[str] = set()
        for node in project.graph.nodes:
            if node.id in relevant_paths or any(
                node.id.startswith(p) for p in relevant_paths
            ):
                relevant_node_ids.add(node.id)

        # Find edges connecting relevant nodes
        relevant_edges = [
            e for e in project.graph.edges
            if e.source in relevant_node_ids or e.target in relevant_node_ids
        ]

        # Pull in neighbour node IDs
        for e in relevant_edges:
            relevant_node_ids.add(e.source)
            relevant_node_ids.add(e.target)

        relevant_nodes = [
            n for n in project.graph.nodes if n.id in relevant_node_ids
        ]

        return {
            "node_count": len(relevant_nodes),
            "edge_count": len(relevant_edges),
            "nodes": [
                {"id": n.id, "type": n.type.value, "name": n.name}
                for n in relevant_nodes[:30]
            ],
            "edges": [
                {"source": e.source, "target": e.target, "relation": e.relation.value}
                for e in relevant_edges[:50]
            ],
        }

    # ------------------------------------------------------------------
    # Internal — relationships & snippets
    # ------------------------------------------------------------------

    def _find_relationships(
        self,
        scored_files: List[Dict[str, Any]],
        project: Project,
    ) -> List[Dict[str, str]]:
        """Find dependency relationships between relevant files."""
        if not project.relationships:
            return []

        relevant_paths = {str(sf["file"]) for sf in scored_files}
        result = []
        for rel in project.relationships:
            source_match = rel.source in relevant_paths
            target_match = rel.target in relevant_paths
            if source_match or target_match:
                result.append({
                    "source": rel.source,
                    "target": rel.target,
                    "kind": rel.kind,
                })
        return result

    def _fetch_snippets(
        self,
        scored_files: List[Dict[str, Any]],
        project: Project,
    ) -> List[Dict[str, Any]]:
        """Read the first N lines of the top-scoring files as context."""
        snippets = []
        for sf in scored_files[:5]:
            path: Path = sf["file"]
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                preview = "\n".join(lines[:40])  # first 40 lines
                snippets.append({
                    "path": path.as_posix(),
                    "preview": preview,
                    "total_lines": len(lines),
                })
            except Exception:
                continue
        return snippets


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_keywords(question: str, target: Optional[str] = None) -> list[str]:
    """Extract meaningful keywords from the question, optionally boosted by target."""
    words = question.lower().split()
    # Filter out very short words and common stop-words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "this", "that", "these", "those", "it", "its", "what", "how",
        "why", "where", "when", "who", "which", "and", "or", "but",
        "not", "no", "nor", "of", "in", "on", "at", "to", "for",
        "with", "by", "from", "as", "into", "through", "during",
        "about", "between", "explain", "tell", "show", "find",
    }
    keywords = {w.strip("(),?.!'\"") for w in words if len(w) > 2 and w not in stop_words}

    if target:
        keywords.add(target.lower())
        # Also add parts of camelCase/PascalCase targets
        parts = _split_identifier(target)
        keywords.update(parts)

    return list(keywords)


def _split_identifier(name: str) -> list[str]:
    """Split a camelCase or PascalCase identifier into parts.

    >>> _split_identifier("DatabaseManager")
    ["database", "manager"]
    >>> _split_identifier("parseURL")
    ["parse", "url"]
    """
    import re
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name)
    return [p.lower() for p in parts]


def _symbol_to_dict(sym: Symbol) -> dict:
    """Convert a Symbol (dataclass) to a plain dict."""
    return {
        "name": sym.name,
        "qualified_name": sym.qualified_name,
        "kind": sym.kind,
        "file": sym.file,
        "line": sym.line,
        "parent": sym.parent,
        "docstring": (sym.docstring or "")[:200],
        "parameters": [
            {
                "name": p.name if hasattr(p, "name") else p.get("name", "?"),
                "annotation": p.annotation if hasattr(p, "annotation") else p.get("annotation"),
            }
            for p in (sym.parameters or [])
        ],
        "return_type": sym.return_type,
    }
