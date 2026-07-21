"""Intent detection — classifies what the user is asking so EDITH can
query the right slice of knowledge (symbols, graph, metrics, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Intent(str, Enum):
    EXPLAIN_REPOSITORY = "explain_repository"
    EXPLAIN_FILE = "explain_file"
    EXPLAIN_CLASS = "explain_class"
    EXPLAIN_FUNCTION = "explain_function"
    REVIEW_CODE = "review_code"
    FIND_USAGE = "find_usage"
    FIND_IMPLEMENTATION = "find_implementation"
    ARCHITECTURE = "architecture"
    GENERAL_QUESTION = "general_question"


# Simple keyword/pattern rules — fast, no LLM call needed.
# Order matters: more specific patterns must come before less specific ones.
_PATTERNS: list[tuple[list[str], Intent]] = [
    # Most specific first
    (["explain this class", "what does this class", "class overview", "class diagram"], Intent.EXPLAIN_CLASS),
    (["explain this file", "what does this file", "file overview", "in this file"], Intent.EXPLAIN_FILE),
    (["explain this function", "what does this function", "how does this function"], Intent.EXPLAIN_FUNCTION),
    (["explain this repo", "explain the repository", "what does this project"], Intent.EXPLAIN_REPOSITORY),
    # Find-usage: check for trailing keywords like "implemented" / "defined"
    (["find definition", "implementation of", "find implementation", "defined", "implemented"], Intent.FIND_IMPLEMENTATION),
    (["where is", "where used", "who calls", "find usages", "find usage", "used in", "references"], Intent.FIND_USAGE),
    # Broader patterns — "overview" alone suggests repository overview
    (["overview"], Intent.EXPLAIN_REPOSITORY),
    (["architecture", "how does this work", "design", "structure", "component diagram"], Intent.ARCHITECTURE),
    (["review", "code quality", "code review", "refactor"], Intent.REVIEW_CODE),
]


def detect_intent(question: str) -> Intent:
    """Classify the user's question into an Intent enum value."""
    lowered = question.lower().strip()

    for keywords, intent in _PATTERNS:
        if any(kw in lowered for kw in keywords):
            return intent

    return Intent.GENERAL_QUESTION


# Words that aren't useful targets
_FILLER_WORDS = {"this", "that", "these", "those", "the", "a", "an", "it", "itself", "they", "them"}


def _is_filler(word: str) -> bool:
    return word.lower() in _FILLER_WORDS


def extract_target(question: str) -> Optional[str]:
    """Try to extract a specific symbol or file name from the question.

    Examples
    --------
    >>> extract_target("explain DatabaseManager")
    "DatabaseManager"
    >>> extract_target("where is connect() used?")
    "connect"
    >>> extract_target("review utils.py")
    "utils.py"
    """
    original = question.strip()
    lowered = original.lower()

    # Remove common prefixes
    for prefix in [
        "explain ",
        "what does ",
        "how does ",
        "where is ",
        "who calls ",
        "find usages of ",
        "review ",
    ]:
        if lowered.startswith(prefix):
            # Take remaining text from the *original* (preserving case)
            rest = original[len(prefix):].strip().rstrip("?.,!;:")
            # Strip trailing parens from function references
            if rest.endswith("()"):
                rest = rest[:-2]
            # Take only the first identifier/word
            first_word = rest.split()[0] if rest.split() else rest
            first_word = first_word.strip("(),?.!:'\"")
            if first_word and not _is_filler(first_word):
                return first_word
            return None

    # Fallback: try to find a capitalized identifier (skip greetings/question words)
    _COMMON_CAPITALIZED = {"Hello", "Hi", "Hey", "What", "How", "Why", "Where", "Who", "When", "Which", "Can", "Could", "Would", "Should", "Will", "Is", "Are", "Do", "Does", "Did"}
    for word in question.split():
        word = word.strip("(),?.!:'\"")
        if word in _COMMON_CAPITALIZED:
            continue
        if word and len(word) > 1 and not _is_filler(word):
            if word[0].isupper() and not word.startswith("_"):
                return word

    # Fallback: snake_case or camelCase identifier
    for word in question.split():
        word = word.strip("(),?.!:'\"")
        if word and len(word) > 2 and ("_" in word or any(c.isupper() for c in word[1:])):
            if not _is_filler(word):
                return word

    return None


class IntentDetector:
    """Wraps intent detection logic for easy injection into the pipeline."""

    def detect(self, question: str) -> tuple[Intent, Optional[str]]:
        intent = detect_intent(question)
        target = extract_target(question)
        return intent, target
