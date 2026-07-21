"""EDITH AI Core — provider abstraction, context engine, prompt builder, and intent detection."""

from app.ai.provider import BaseProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.context_engine import ContextEngine
from app.ai.prompt_builder import PromptBuilder
from app.ai.intent_detector import IntentDetector, Intent
from app.ai.conversation_memory import ConversationMemory

__all__ = [
    "BaseProvider",
    "OpenAIProvider",
    "ContextEngine",
    "PromptBuilder",
    "IntentDetector",
    "Intent",
    "ConversationMemory",
]
