"""LLM Provider Factory.

Instantiates configured LLM clients (Groq, Mock, OpenAI) based on application Settings.
"""

from app.config import Settings
from app.exceptions import ConfigurationError
from app.llm.client import LLMClient
from app.llm.providers.groq import GroqLLMClient
from app.llm.providers.mock import MockLLMClient
from app.logging import get_logger

logger = get_logger(__name__)


def get_llm_client(settings: Settings) -> LLMClient:
    """Factory creating an instance of LLMClient matching settings.llm_provider.

    Args:
        settings: Application settings instance.

    Returns:
        LLMClient protocol implementation.
    """
    provider = settings.llm_provider.lower()

    if provider == "groq":
        logger.debug("Instantiating Groq LLM client (model: %s)", settings.llm_model)
        return GroqLLMClient(settings=settings)

    elif provider == "mock":
        logger.debug("Instantiating Mock LLM client for testing/offline use.")
        return MockLLMClient()

    elif provider in {"openai", "gemini", "ollama"}:
        # Groq-compatible / OpenAI-compatible endpoint fallback
        logger.info("Using Groq/OpenAI compatible client for provider: %s", provider)
        return GroqLLMClient(settings=settings)

    else:
        raise ConfigurationError(
            f"Unsupported LLM provider: '{provider}'. Supported options: groq, mock, openai, gemini, ollama",
            details={"provider": provider},
        )
