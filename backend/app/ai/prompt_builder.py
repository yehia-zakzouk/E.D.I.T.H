"""Prompt Builder — assembles a structured, token-efficient prompt from
the context produced by the Context Engine.

The resulting prompt has sections:

    [System]
    [Repository Summary]
    [Relevant Files & Symbols]
    [Source Snippets]
    [Graph Context]
    [Relationships]
    [Conversation History]
    [Question]

This keeps the LLM focused on high-quality context instead of raw files.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.project import Project
from app.core.config import logger


# Default system prompt that frames EDITH's role
SYSTEM_PROMPT = """You are EDITH, an expert code analysis assistant. You help developers understand, review, and navigate codebases.

You have been given structured context from the repository's analysis — including symbols, file summaries, dependency relationships, and a knowledge graph.

Guidelines:
- Be concise and precise. Focus on the most relevant details.
- Reference specific symbols, files, and line numbers when relevant.
- If the question is about a bug or code review, be constructively critical.
- If you don't have enough context, say so rather than guessing.
- Use markdown for clarity (code blocks, bullet lists, headings).

The repository has been pre-analyzed. Below is the relevant context.
"""


class PromptBuilder:
    """Builds a structured prompt from context + project knowledge.

    Usage::

        prompt = PromptBuilder().build(
            question="explain DatabaseManager",
            context=context_engine_output,
            project=analyzed_project,
        )
        answer = provider.ask(prompt)
    """

    def __init__(self, system_prompt: Optional[str] = None):
        self._system_prompt = system_prompt or SYSTEM_PROMPT

    def build(
        self,
        question: str,
        context: Dict[str, Any],
        project: Optional[Project] = None,
    ) -> str:
        """Assemble the full prompt string."""
        sections: list[str] = []

        # --- Repository Summary ---
        if project is not None:
            repo_summary = self._render_repo_summary(project)
            if repo_summary:
                sections.append(repo_summary)

        # --- Conversation Context (if any) ---
        conv = context.get("conversation_context")
        if conv:
            sections.append(f"## Conversation History\n\n{conv}\n")

        # --- Relevant Files & Symbols ---
        files_section = self._render_files_section(context)
        if files_section:
            sections.append(files_section)

        # --- Source Snippets ---
        snippets_section = self._render_snippets_section(context)
        if snippets_section:
            sections.append(snippets_section)

        # --- Graph Context ---
        graph_section = self._render_graph_section(context)
        if graph_section:
            sections.append(graph_section)

        # --- Relationships / Dependencies ---
        rel_section = self._render_relationships_section(context)
        if rel_section:
            sections.append(rel_section)

        # --- The Question ---
        sections.append(f"## Question\n\n{question}")

        prompt = "\n\n---\n\n".join(sections)
        logger.debug("PromptBuilder: built prompt (%d chars)", len(prompt))
        return prompt

    def build_system_message(self) -> str:
        """Return just the system prompt for use in chat-style APIs."""
        return self._system_prompt

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _render_repo_summary(self, project: Project) -> str:
        lines = ["## Repository Summary", ""]
        if project.languages:
            lines.append(f"- **Languages:** {', '.join(project.languages)}")
        if project.frameworks:
            lines.append(f"- **Frameworks:** {', '.join(project.frameworks)}")
        if project.build_system:
            lines.append(f"- **Build System:** {project.build_system}")
        if project.database:
            lines.append(f"- **Database:** {project.database}")
        lines.append(f"- **Indexed Files:** {len(project.indexed_files)}")
        if project.graph:
            lines.append(
                f"- **Graph:** {len(project.graph.nodes)} nodes, "
                f"{len(project.graph.edges)} edges"
            )
        return "\n".join(lines)

    def _render_files_section(self, context: Dict[str, Any]) -> str:
        files = context.get("relevant_files")
        if not files:
            return ""

        lines = ["## Relevant Files & Symbols", ""]
        for f in files[:10]:
            symbols_list = []
            for sym in f.get("symbols", [])[:5]:
                sym_desc = f"`{sym.get('name', '?')}` ({sym.get('kind', '?')})"
                if sym.get("parent"):
                    sym_desc += f" in `{sym['parent']}`"
                symbols_list.append(sym_desc)

            lines.append(f"### {f.get('path', '?')}  (score: {f.get('score', 0)})")
            if symbols_list:
                lines.append("Symbols: " + ", ".join(symbols_list))
            lines.append("")

        return "\n".join(lines)

    def _render_snippets_section(self, context: Dict[str, Any]) -> str:
        snippets = context.get("source_snippets")
        if not snippets:
            return ""

        lines = ["## Source Code", ""]
        for s in snippets[:3]:
            lines.append(f"**{s.get('path', '?')}** ({s.get('total_lines', '?')} lines)")
            lines.append("```python")
            lines.append(s.get("preview", ""))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _render_graph_section(self, context: Dict[str, Any]) -> str:
        graph = context.get("graph_context")
        if not graph:
            return ""

        lines = ["## Knowledge Graph (relevant sub-graph)", ""]
        lines.append(f"- **Nodes:** {graph.get('node_count', 0)}")
        lines.append(f"- **Edges:** {graph.get('edge_count', 0)}")
        lines.append("")

        nodes = graph.get("nodes", [])[:15]
        if nodes:
            lines.append("### Nodes")
            for n in nodes:
                lines.append(f"- `{n['id']}`  ({n['type']})")
            lines.append("")

        edges = graph.get("edges", [])[:20]
        if edges:
            lines.append("### Edges")
            for e in edges:
                lines.append(
                    f"- `{e['source']}` --[{e['relation']}]--> `{e['target']}`"
                )
            lines.append("")

        return "\n".join(lines)

    def _render_relationships_section(self, context: Dict[str, Any]) -> str:
        rels = context.get("relevant_relationships")
        if not rels:
            return ""

        lines = ["## File Relationships / Dependencies", ""]
        for r in rels[:15]:
            lines.append(f"- `{r['source']}` --[{r.get('kind', 'depends')}]--> `{r['target']}`")
        lines.append("")

        return "\n".join(lines)
