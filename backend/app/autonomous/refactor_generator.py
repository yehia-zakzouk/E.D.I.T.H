"""Refactor Generator (Sprint 9.2) — generates improved code for each
opportunity identified by the Opportunity Engine.

This is where EDITH goes from "what's wrong?" to "here's the fix."

Strategy
--------
1. For simple, deterministic refactorings (add docstring, rename, extract line
   break) — use AST transformations directly. Fast and reliable.
2. For complex refactorings (reduce complexity, extract method, fix architecture)
   — use the LLM to generate improved code, guided by the opportunity context.

The generator creates a ``RefactoredCode`` for every opportunity it can handle.
"""

from __future__ import annotations

import ast
import re
import textwrap
from typing import Optional

from app.core.config import config, logger
from app.autonomous.models import (
    Opportunity,
    OpportunityType,
    RefactoredCode,
)


class RefactorGenerator:
    """Generates improved code for each engineering opportunity.

    Usage::

        generator = RefactorGenerator()
        refactored = generator.refactor(opportunity, source_text)
        print(refactored.refactored_code)
    """

    def __init__(self, use_llm: bool = True):
        self._use_llm = use_llm
        self._provider = None

    def refactor(
        self,
        opportunity: Opportunity,
        full_source: str,
    ) -> Optional[RefactoredCode]:
        """Generate improved code for a single opportunity.

        Args:
            opportunity: The opportunity to fix.
            full_source: The full source code of the file containing the opportunity.

        Returns:
            A RefactoredCode with the improvement, or None if this opportunity
            cannot be automatically refactored.
        """
        lines = full_source.splitlines()

        # Extract the original code segment
        if opportunity.line > 0 and opportunity.context_lines:
            start_idx = max(0, opportunity.line - 4)  # 0-indexed
            end_idx = min(len(lines), opportunity.line + opportunity.end_line - opportunity.line + 3) if opportunity.end_line else min(len(lines), opportunity.line + 5)
            original_code = "\n".join(lines[start_idx:end_idx])
        else:
            original_code = full_source

        opp_type = opportunity.type

        # ── Deterministic refactorings (no LLM needed) ──────────────
        if opp_type == OpportunityType.MISSING_DOCSTRING:
            return self._add_docstring(opportunity, full_source, lines)

        if opp_type == OpportunityType.POOR_NAMING:
            return self._fix_naming(opportunity, full_source, lines)

        if opp_type == OpportunityType.LONG_LINE:
            return self._break_long_lines(opportunity, full_source, lines)

        # ── LLM-based refactorings ──────────────────────────────────
        if self._use_llm and opp_type in (
            OpportunityType.HIGH_COMPLEXITY,
            OpportunityType.LONG_FUNCTION,
            OpportunityType.TOO_MANY_PARAMS,
            OpportunityType.DEEP_NESTING,
            OpportunityType.LARGE_CLASS,
            OpportunityType.DUPLICATION,
        ):
            return self._llm_refactor(opportunity, original_code, full_source)

        # ── Cannot refactor automatically ──────────────────────────
        logger.debug("RefactorGenerator: no automatic refactoring for %s", opp_type.value)
        return None

    # ------------------------------------------------------------------
    # Deterministic refactorings
    # ------------------------------------------------------------------

    def _add_docstring(
        self,
        opportunity: Opportunity,
        full_source: str,
        lines: list[str],
    ) -> Optional[RefactoredCode]:
        """Add a docstring to the target function or class."""
        try:
            tree = ast.parse(full_source)
        except SyntaxError:
            return None

        line_no = opportunity.line
        if line_no == 0:
            return None

        # Find the function/class at this line
        target_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.lineno == line_no:
                    target_node = node
                    break

        if target_node is None:
            return None

        # Build docstring text
        if isinstance(target_node, ast.ClassDef):
            doc_text = f'    """{opportunity.symbol_name}\n\n    TODO: Add class description.\n    """\n'
        else:
            params = ""
            if isinstance(target_node, ast.FunctionDef):
                args = [a.arg for a in target_node.args.args if a.arg not in ("self", "cls")]
                if args:
                    params = "\n    Args:\n" + "\n".join(f"        {a}: Description." for a in args)
            doc_text = f'    """{opportunity.symbol_name}\n\n    TODO: Add function description.{params}\n    """\n'

        # Insert the docstring right after the function/class signature
        body = target_node.body
        if body:
            first_stmt_line = body[0].lineno
            insert_pos = first_stmt_line - 1  # 0-indexed
            new_lines = lines.copy()
            # Check if there's already a docstring
            if (isinstance(body[0], ast.Expr) and isinstance(body[0].value, (ast.Constant, ast.Str))):
                return None  # Already has a docstring

            new_lines.insert(insert_pos, doc_text)
            new_source = "\n".join(new_lines)
            return RefactoredCode(
                opportunity_key=opportunity.key,
                original_code=full_source,
                refactored_code=new_source,
                explanation=f"Added docstring to {opportunity.symbol_name}",
                preserves_behavior=True,
            )

        return None

    @staticmethod
    def _fix_naming(
        opportunity: Opportunity,
        full_source: str,
        lines: list[str],
    ) -> Optional[RefactoredCode]:
        """Fix naming convention violations (stub — LLM handles complex renames)."""
        # Simple renames can be done via find/replace, but most naming
        # fixes require propagating across the entire project.
        # For now, warn the user.
        return RefactoredCode(
            opportunity_key=opportunity.key,
            original_code=opportunity.description,
            refactored_code="",  # Manual rename needed
            explanation=f"Naming issue found: {opportunity.description}. "
                        f"Rename requires project-wide propagation — EDITH recommends "
                        f"using your IDE's rename refactoring.",
            preserves_behavior=True,
        )

    @staticmethod
    def _break_long_lines(
        opportunity: Opportunity,
        full_source: str,
        lines: list[str],
    ) -> Optional[RefactoredCode]:
        """Break long lines into multiple lines."""
        new_lines = []
        changes = 0
        for line in lines:
            if len(line) > 100:
                # Try to break at an operator or comma
                broken = _break_line(line, 100)
                if broken != line:
                    new_lines.append(broken)
                    changes += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if changes == 0:
            return None

        new_source = "\n".join(new_lines)
        return RefactoredCode(
            opportunity_key=opportunity.key,
            original_code=full_source,
            refactored_code=new_source,
            explanation=f"Broken {changes} long lines",
            preserves_behavior=True,
        )

    # ------------------------------------------------------------------
    # LLM-based refactoring
    # ------------------------------------------------------------------

    def _llm_refactor(
        self,
        opportunity: Opportunity,
        original_code: str,
        full_source: str,
    ) -> Optional[RefactoredCode]:
        """Use the LLM to generate refactored code."""
        provider = self._get_provider()
        if provider is None:
            logger.debug("RefactorGenerator: no LLM provider — skipping LLM refactoring")
            return None

        prompt = _build_refactor_prompt(opportunity, original_code)

        try:
            response = provider.ask(prompt, temperature=0.3, max_tokens=2048)
        except Exception as e:
            logger.warning("RefactorGenerator: LLM call failed: %s", e)
            return None

        # Extract code from response (strip markdown fences)
        code_match = re.search(
            r"```(?:python)?\s*([\s\S]*?)```",
            response,
        )
        if code_match:
            refactored_code = code_match.group(1).strip()
        else:
            refactored_code = response.strip()

        # Extract explanation (text before the code block)
        explanation_match = re.search(
            r"^([\s\S]*?)```",
            response,
        )
        explanation = ""
        if explanation_match:
            explanation = explanation_match.group(1).strip()
            # Clean up leading/trailing markers
            explanation = re.sub(r"^Here('s| is) the (refactored|improved) code[:\s]*", "", explanation)
            explanation = re.sub(r"^Sure[,\s]+", "", explanation)
            explanation = explanation.strip()

        return RefactoredCode(
            opportunity_key=opportunity.key,
            original_code=original_code,
            refactored_code=refactored_code,
            explanation=explanation or f"Refactored {opportunity.symbol_name} to reduce {opportunity.metric_name}",
            preserves_behavior=True,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_provider(self):
        if self._provider is not None:
            return self._provider
        try:
            from app.main import create_provider as _create
            self._provider = _create()
        except Exception:
            try:
                api_key = config.ai.api_key
                if api_key:
                    from app.ai.openai_provider import OpenAIProvider
                    self._provider = OpenAIProvider()
                else:
                    self._provider = None
            except Exception:
                self._provider = None
        return self._provider


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _break_line(line: str, max_length: int = 100) -> str:
    """Break a single long line at a sensible point."""
    stripped = line.rstrip("\n")
    if len(stripped) <= max_length:
        return line

    # Try breaking at binary operators
    for op in [" and ", " or ", " + ", " | ", " & ", " || ", " && "]:
        idx = stripped.rfind(op, 0, max_length)
        if idx > max_length * 0.4:  # break point is not too early
            indent = " " * (len(line) - len(line.lstrip()) + 4)
            return stripped[:idx] + op.strip() + "\n" + indent + stripped[idx + len(op):]

    # Try breaking at commas (for function calls)
    idx = stripped.rfind(",", 0, max_length)
    if idx > max_length * 0.4:
        indent = " " * (len(line) - len(line.lstrip()) + 4)
        return stripped[:idx + 1] + "\n" + indent + stripped[idx + 1:].lstrip()

    # Try breaking at parentheses
    idx = stripped.rfind("(", 0, max_length)
    if idx > max_length * 0.3:
        indent = " " * (len(line) - len(line.lstrip()) + 4)
        return stripped[:idx + 1] + "\n" + indent + stripped[idx + 1:].strip()

    return line


def _build_refactor_prompt(opportunity: Opportunity, code: str) -> str:
    """Build the LLM prompt for refactoring."""
    type_labels = {
        OpportunityType.HIGH_COMPLEXITY: "Reduce cyclomatic complexity",
        OpportunityType.LONG_FUNCTION: "Extract into smaller functions",
        OpportunityType.TOO_MANY_PARAMS: "Reduce parameter count",
        OpportunityType.DEEP_NESTING: "Reduce nesting depth",
        OpportunityType.LARGE_CLASS: "Split into smaller classes",
        OpportunityType.DUPLICATION: "Remove duplication",
    }
    instruction = type_labels.get(opportunity.type, "Improve")

    prompt = f"""You are EDITH's code refactoring engine. Given the following code, {instruction.lower()}.

## Current code

```python
{code}
```

## Issue

{opportunity.description}

## Recommendation from analysis

{opportunity.recommendation}

## Instructions

1. {instruction} in the code above.
2. Preserve all existing behavior — the refactored code must be functionally identical.
3. Include all necessary imports.
4. Keep the same public API / function signature unless the opportunity specifically relates to parameters.
5. Respond with a brief explanation on the first line(s), then the complete refactored code in a markdown code block.
6. Only show the changed function(s) or class(es), not the entire file, unless the whole file needs restructuring.

## Output format

Brief explanation of what changed and why.

```python
the complete refactored code
```
"""
    return prompt
