from typing import Dict, List, Any
from app.models.project import Project
from app.core.config import logger


class ContextEngine:
    """Builds focused context for an LLM prompt from repository knowledge.

    This is a minimal, extensible implementation that selects a small set
    of relevant symbols and file summaries based on a user's question.
    """

    def __init__(self):
        pass

    def build_context(self, question: str, project: Project) -> Dict[str, Any]:
        logger.debug("ContextEngine: building context for question: %s", question)

        keywords = [w.lower() for w in question.split() if len(w) > 2]

        relevant: List[Dict[str, Any]] = []

        for f in project.indexed_files:
            analysis = f.analysis
            if analysis is None:
                continue

            # Check module docstring and symbol names for keyword matches
            score = 0
            text_fields = []
            if analysis.module_docstring:
                text_fields.append(analysis.module_docstring)
            for s in getattr(analysis, "symbols", []):
                text_fields.append(getattr(s, "name", ""))
                text_fields.append(getattr(s, "qualified_name", ""))

            combined = " ".join([t for t in text_fields if t])
            lowered = combined.lower()

            for k in keywords:
                if k in lowered:
                    score += 1

            if score > 0:
                relevant.append({
                    "file": f.path.as_posix(),
                    "score": score,
                    "symbols": [
                        {"name": getattr(s, "qualified_name", getattr(s, "name", None)), "kind": getattr(s, "kind", None)}
                        for s in getattr(analysis, "symbols", [])[:5]
                    ],
                })

        # Sort and keep top results to limit token usage
        relevant = sorted(relevant, key=lambda r: r["score"], reverse=True)[:10]

        context = {
            "question": question,
            "relevant_files": relevant,
            "summary": f"Found {len(relevant)} relevant files",
        }

        return context
