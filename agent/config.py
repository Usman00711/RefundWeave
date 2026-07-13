"""Runtime configuration for the customer support agent."""

import os
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    model: str
    base_url: str


def load_model_settings() -> ModelSettings:
    """Load and validate model configuration without exposing secret values."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "your_openrouter_api_key_here":
        raise ConfigurationError(
            "OPENROUTER_API_KEY is not configured. Copy .env.example to .env and add a valid key."
        )

    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free").strip()
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
    if not model:
        raise ConfigurationError("OPENROUTER_MODEL cannot be empty.")
    if not base_url.startswith(("https://", "http://")):
        raise ConfigurationError("OPENROUTER_BASE_URL must be an HTTP(S) URL.")

    return ModelSettings(api_key=api_key, model=model, base_url=base_url)
