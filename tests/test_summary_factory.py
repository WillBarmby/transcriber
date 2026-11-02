import pytest

from tranpro.summarization.factory import build_summary_provider
from tranpro.summarization.ollama import OllamaProvider
from tranpro.summarization.openai import OpenAISummaryProvider


def test_builds_local_provider_with_profile_settings() -> None:
    provider = build_summary_provider(
        {
            "summary_provider": "ollama",
            "summary_model": "gemma4:12b",
            "summary_context_tokens": 32_768,
            "summary_output_tokens": 2_048,
        }
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.model == "gemma4:12b"
    assert provider.context_window.max_tokens == 32_768


def test_builds_openai_provider_without_a_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider = build_summary_provider(
        {
            "summary_provider": "openai",
            "summary_model": "gpt-6.1-terra",
            "summary_context_tokens": 272_000,
            "summary_output_tokens": 8_192,
            "reasoning_effort": "none",
        }
    )

    assert isinstance(provider, OpenAISummaryProvider)
    assert provider.model == "gpt-6.1-terra"
    assert provider.reasoning_effort == "none"
