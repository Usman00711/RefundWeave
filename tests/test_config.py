import pytest

from agent.config import ConfigurationError, load_model_settings


def test_model_settings_require_an_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        load_model_settings()


def test_model_settings_reject_placeholder_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "your_openrouter_api_key_here")

    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        load_model_settings()


def test_model_settings_support_provider_overrides(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "example/model")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://example.test/v1")

    settings = load_model_settings()

    assert settings.api_key == "test-key"
    assert settings.model == "example/model"
    assert settings.base_url == "https://example.test/v1"


def test_model_settings_reject_invalid_base_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "not-a-url")

    with pytest.raises(ConfigurationError, match=r"HTTP\(S\) URL"):
        load_model_settings()
