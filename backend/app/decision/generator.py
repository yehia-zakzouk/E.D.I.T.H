"""Candidate Generator — transforms an ``EngineeringProblem`` into a set of
fundamentally different ``CandidateSolution`` objects.

Architecture
------------
    BaseGenerator              (abstract — the interface)
       │
       ├── OpenAIGenerator    (calls GPT with diverse prompt)
       ├── MockGenerator      (canned responses for testing)
       └── TemplateGenerator  (future: deterministic templates)

Every generator returns **exactly 3 candidates**, each optimized for a
different trade-off:

    A — Performance   (fastest, most efficient)
    B — Maintainability (cleanest, most modular)
    C — Simplicity    (fewest lines, easiest to understand)

The prompt is carefully engineered to force *fundamental* differences,
not cosmetic changes.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Optional

from app.core.config import config, logger
from app.decision.problem import EngineeringProblem, ProblemGoal
from app.decision.candidate import CandidateSolution


# ------------------------------------------------------------------
# Prompt template — the crucial piece
# ------------------------------------------------------------------

GENERATION_PROMPT = """You are EDITH's solution generator. Given an engineering problem and repository context, generate THREE fundamentally different implementation approaches.

## Engineering Problem

**Goal:** {goal}
**Scope:** {scope}
**Affected Layers:** {layers}
**Complexity:** {complexity}  **Risk:** {risk}

**Request:** {question}

**Constraints:**
{constraints}

**User Preferences:**
{preferences}

**Relevant Files:**
{files}

**Relevant Symbols:**
{symbols}

**Project Context:**
- Languages: {languages}
- Frameworks: {frameworks}
- Build System: {build_system}

## Critical Instructions

You MUST generate THREE solutions. Each solution must be FUNDAMENTALLY different — not just variable names changed.

- **Solution A — Performance-First:** Optimize for speed, throughput, and low latency. Accept higher complexity and less readability if it means better performance.
- **Solution B — Maintainability-First:** Optimize for clean architecture, modularity, and ease of future changes. Accept slightly lower performance if it means cleaner code.
- **Solution C — Simplicity-First:** Optimize for minimal code, fewest concepts, and easiest understanding. Accept less flexibility if it means the simplest possible implementation.

## Output Format

Respond with valid JSON only — no markdown, no explanation outside the JSON.

```json
[
  {{
    "title": "Solution A title",
    "description": "2-3 sentence explanation of this approach",
    "code": "the full implementation code as a string",
    "reasoning": "Why this approach was chosen and what trade-offs it makes",
    "files_modified": ["path/to/file1.py", "path/to/file2.py"],
    "estimated_runtime": "e.g. 2-3 hours",
    "estimated_memory": "e.g. +1.2 MB or negligible"
  }},
  {{
    "title": "Solution B title",
    ...
  }},
  {{
    "title": "Solution C title",
    ...
  }}
]
```

## Quality Requirements

1. Each solution MUST contain working code — not pseudocode, not "TODO"
2. Each solution MUST have a different architectural approach, not just different variable names
3. Each solution MUST include all necessary imports
4. Code must be compatible with the project's language and framework
5. If a solution touches a file that doesn't exist yet, include "create" in the file path
"""


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

class GenerationError(Exception):
    """Raised when candidate generation fails or validation fails."""
    pass


def validate_candidates(
    candidates: list[CandidateSolution],
    min_count: int = 3,
) -> list[CandidateSolution]:
    """Validate a list of candidates.

    Checks:
        - At least ``min_count`` candidates (default 3)
        - Each candidate has code and reasoning
        - No duplicate titles (cosmetic duplicates)
        - Each candidate has a unique approach

    Returns the validated list.
    Raises ``GenerationError`` on failure.
    """
    if len(candidates) < min_count:
        raise GenerationError(
            f"Expected at least {min_count} candidates, got {len(candidates)}"
        )

    errors: list[str] = []

    for i, c in enumerate(candidates):
        if not c.code or not c.code.strip():
            errors.append(f"Candidate {i+1} ('{c.title}') is missing code")
        if not c.reasoning or not c.reasoning.strip():
            errors.append(f"Candidate {i+1} ('{c.title}') is missing reasoning")
        if not c.title or not c.title.strip():
            errors.append(f"Candidate {i+1} has no title")

    # Check for near-duplicate titles (cosmetic duplicates)
    seen_titles: set[str] = set()
    for c in candidates:
        normalized = c.title.lower().strip().rstrip(".")
        if normalized in seen_titles:
            errors.append(f"Duplicate title: '{c.title}'")
        seen_titles.add(normalized)

    if errors:
        raise GenerationError("Validation failed:\n" + "\n".join(errors))

    return candidates


# ------------------------------------------------------------------
# Base class (interface)
# ------------------------------------------------------------------

class BaseGenerator(ABC):
    """Abstract generator interface.

    Every generator implementation must implement ``generate()`` which
    returns a list of ``CandidateSolution`` objects.
    """

    @abstractmethod
    def generate(
        self,
        problem: EngineeringProblem,
    ) -> list[CandidateSolution]:
        """Generate candidate solutions for an engineering problem.

        Args:
            problem: The structured engineering problem to solve.

        Returns:
            A list of validated CandidateSolution objects (typically 3).
        """
        ...

    def _build_prompt(self, problem: EngineeringProblem) -> str:
        """Build the generation prompt from a problem (shared across providers)."""
        return GENERATION_PROMPT.format(
            goal=problem.goal.value,
            scope=problem.scope.value,
            layers=", ".join(l.value for l in problem.affected_layers),
            complexity=problem.complexity,
            risk=problem.risk,
            question=problem.question,
            constraints="\n".join(f"- {c}" for c in problem.constraints) or "None",
            preferences="\n".join(f"- {p}" for p in problem.preferences) or "None",
            files="\n".join(f"- {f}" for f in problem.relevant_files[:8]) or "None specified",
            symbols="\n".join(f"- {s}" for s in problem.relevant_symbols[:10]) or "None specified",
            languages=", ".join(problem.project_languages) or "Unknown",
            frameworks=", ".join(problem.project_frameworks) or "None detected",
            build_system=problem.build_system or "Unknown",
        )

    @staticmethod
    def _extract_outermost_array(text: str) -> str:
        """Find the outermost ``[...]`` JSON array in *text*.

        Walks the string character-by-character tracking bracket depth
        so that ``]`` inside strings (e.g. ``items[0]``) doesn't cause
        premature truncation.

        Returns the matched JSON text, or the original text if no
        balanced array is found.
        """
        depth = 0
        start = -1
        in_string = False
        escape = False

        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == "[":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0 and start >= 0:
                    return text[start:i + 1]

        # No balanced array found — return the original for json.loads to reject
        return text

    @staticmethod
    def _parse_candidates(
        response: str,
        parent_problem_id: int,
    ) -> list[CandidateSolution]:
        """Parse the LLM's JSON response into CandidateSolution objects.

        Tries to extract JSON from various response formats:
            - Pure JSON array
            - JSON embedded in ```json ... ``` code blocks
            - JSON embedded in ``` ... ``` code blocks
        """
        json_str = response.strip()

        # Remove markdown code fence if present.
        fence_match = re.search(
            r"```(?:json)?\s*([\s\S]*?)\s*```",
            response,
        )
        if fence_match:
            json_str = fence_match.group(1).strip()

        # Extract the outermost balanced JSON array, handling `]` in code strings.
        json_str = BaseGenerator._extract_outermost_array(json_str)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse generator JSON response: %s", e)
            logger.debug("Raw response (first 500 chars): %s", response[:500])
            raise GenerationError(f"Failed to parse LLM response as JSON: {e}")

        if not isinstance(data, list):
            data = [data]

        candidates: list[CandidateSolution] = []
        for i, item in enumerate(data):
            candidate = CandidateSolution(
                parent_problem_id=parent_problem_id,
                title=item.get("title", f"Solution {chr(65 + i)}").strip(),
                description=item.get("description", "").strip(),
                code=item.get("code", "").strip(),
                reasoning=item.get("reasoning", "").strip(),
                files_modified=item.get("files_modified", []),
                estimated_runtime=item.get("estimated_runtime", ""),
                estimated_memory=item.get("estimated_memory", ""),
                estimated_tokens=len(item.get("code", "")) // 4,
                metadata={"source": "llm"},
            )
            candidates.append(candidate)

        return validate_candidates(candidates)


# ------------------------------------------------------------------
# OpenAI Generator
# ------------------------------------------------------------------

class OpenAIGenerator(BaseGenerator):
    """Uses OpenAI to generate three diverse solutions."""

    def __init__(self):
        self._provider = self._create_provider()

    def generate(
        self,
        problem: EngineeringProblem,
    ) -> list[CandidateSolution]:
        prompt = self._build_prompt(problem)

        logger.info(
            "OpenAIGenerator: generating for problem #%d (%s)",
            problem.problem_id,
            problem.summary(),
        )

        if self._provider is None:
            logger.warning("No AI provider available — falling back to MockGenerator")
            return MockGenerator().generate(problem)

        response = self._provider.ask(
            prompt,
            temperature=0.7,  # enough creativity for diversity
            max_tokens=4096,
        )

        candidates = self._parse_candidates(response, problem.problem_id)
        logger.info(
            "OpenAIGenerator: generated %d candidates for problem #%d",
            len(candidates),
            problem.problem_id,
        )

        return candidates

    @staticmethod
    def _create_provider():
        """Create an AI provider for generation."""
        try:
            from app.main import create_provider as _create
            return _create()
        except Exception:
            try:
                from app.ai.openai_provider import OpenAIProvider
                api_key = config.ai.api_key
                return OpenAIProvider() if api_key else None
            except Exception:
                return None


# ------------------------------------------------------------------
# Mock Generator (for testing without API)
# ------------------------------------------------------------------

class MockGenerator(BaseGenerator):
    """Returns canned solutions for development and testing."""

    def generate(
        self,
        problem: EngineeringProblem,
    ) -> list[CandidateSolution]:
        logger.info("MockGenerator: generating for problem #%d", problem.problem_id)

        candidates = [
            CandidateSolution(
                parent_problem_id=problem.problem_id,
                title="Decorator-based middleware (Performance)",
                description=(
                    "Use a lightweight decorator that wraps the target function "
                    "with minimal overhead. Inline caching reduces lookups."
                ),
                code="# Performance-optimized decorator approach\n"
                     "import functools\n"
                     "from typing import Callable\n\n\n"
                     "def fast_auth(func: Callable) -> Callable:\n"
                     '    """Zero-overhead auth check via decorator."""\n'
                     "    @functools.wraps(func)\n"
                     "    def wrapper(*args, **kwargs):\n"
                     "        user = get_current_user()  # cached lookup\n"
                     "        if user is None:\n"
                     "            raise PermissionError('Unauthorized')\n"
                     "        return func(*args, **kwargs)\n"
                     "    return wrapper\n",
                reasoning=(
                    "Decorators add zero overhead per-call after decoration. "
                    "This is the fastest approach because the auth check runs "
                    "in a single function call with no indirection. Trade-off: "
                    "less flexible than middleware, harder to compose."
                ),
                files_modified=["app/auth/decorators.py", "app/api/routes.py"],
                estimated_runtime="1-2 hours",
                estimated_memory="negligible",
                estimated_tokens=180,
                metadata={"source": "mock"},
            ),
            CandidateSolution(
                parent_problem_id=problem.problem_id,
                title="Middleware pipeline (Maintainability)",
                description=(
                    "Implement auth as a middleware class in the request pipeline. "
                    "Supports composable checks (rate-limit + auth + audit)."
                ),
                code="# Maintainable middleware pipeline\n"
                     "from abc import ABC, abstractmethod\n"
                     "from dataclasses import dataclass, field\n"
                     "from typing import Optional\n\n\n"
                     "class AuthMiddleware(ABC):\n"
                     '    """Composable auth middleware."""\n'
                     "    @abstractmethod\n"
                     "    def authenticate(self, request) -> Optional[dict]:\n"
                     "        ...\n\n\n"
                     "class JWTAuthMiddleware(AuthMiddleware):\n"
                     '    """Validates JWT tokens from Authorization header."""\n'
                     "    def authenticate(self, request) -> Optional[dict]:\n"
                     "        token = request.headers.get('Authorization', '').removeprefix('Bearer ')\n"
                     "        if not token:\n"
                     "            return None\n"
                     "        return decode_jwt(token)\n\n\n"
                     "@dataclass\n"
                     "class MiddlewarePipeline:\n"
                     '    """Chain of middleware handlers."""\n'
                     "    handlers: list[AuthMiddleware] = field(default_factory=list)\n\n"
                     "    def process(self, request):\n"
                     "        for handler in self.handlers:\n"
                     "            user = handler.authenticate(request)\n"
                     "            if user:\n"
                     "                request.user = user\n"
                     "                return True\n"
                     "        raise PermissionError('Unauthorized')\n",
                reasoning=(
                    "Middleware is the most maintainable pattern: each concern "
                    "is isolated in its own class, easily testable, and the "
                    "pipeline can be reordered via config. Trade-off: slightly "
                    "more indirection than decorators."
                ),
                files_modified=["app/auth/middleware.py", "app/core/pipeline.py", "app/config/settings.py"],
                estimated_runtime="3-4 hours",
                estimated_memory="+0.5 MB (class overhead)",
                estimated_tokens=420,
                metadata={"source": "mock"},
            ),
            CandidateSolution(
                parent_problem_id=problem.problem_id,
                title="Dependency injection (Simplicity)",
                description=(
                    "Pass auth state directly as a dependency. No decorators, "
                    "no middleware — just a function parameter."
                ),
                code="# Simplest possible approach: dependency injection\n"
                     "from dataclasses import dataclass\n"
                     "from typing import Optional\n\n\n"
                     "@dataclass\n"
                     "class AuthContext:\n"
                     '    """Carries authentication state."""\n'
                     "    user_id: Optional[str] = None\n"
                     "    roles: list[str] = None\n\n\n"
                     "def get_auth_context(request) -> AuthContext:\n"
                     '    """Extract auth context from request."""\n'
                     "    token = request.headers.get('Authorization', '')\n"
                     "    if not token.startswith('Bearer '):\n"
                     "        return AuthContext()\n"
                     "    payload = decode_jwt(token.removeprefix('Bearer '))\n"
                     "    return AuthContext(\n"
                     "        user_id=payload.get('sub'),\n"
                     "        roles=payload.get('roles', []),\n"
                     "    )\n\n\n"
                     "# Usage: def create_post(auth: AuthContext, ...):\n"
                     "#         if not auth.user_id:\n"
                     "#             raise PermissionError\n",
                reasoning=(
                    "The simplest approach: auth is just data passed around. "
                    "No patterns to learn, no decorators, no middleware classes. "
                    "Trade-off: requires manual propagation through every function "
                    "that needs auth context."
                ),
                files_modified=["app/auth/context.py"],
                estimated_runtime="30 min",
                estimated_memory="negligible",
                estimated_tokens=250,
                metadata={"source": "mock"},
            ),
        ]

        return validate_candidates(candidates)


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

_GENERATORS: dict[str, type[BaseGenerator]] = {
    "openai": OpenAIGenerator,
    "mock": MockGenerator,
}


def get_generator(name: str = "") -> BaseGenerator:
    """Factory: returns a generator by name (or the default)."""
    if not name:
        name = "openai" if config.ai.api_key else "mock"
    cls = _GENERATORS.get(name)
    if cls is None:
        raise ValueError(f"Unknown generator '{name}'. Available: {list(_GENERATORS.keys())}")
    return cls()
