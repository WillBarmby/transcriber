"""Construct summary adapters from named configuration profiles."""

from __future__ import annotations

from typing import Any

from tranpro.summarization.ollama import (
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_OLLAMA_MODEL,
    OllamaProvider,
    SummarizationError,
)
from tranpro.summarization.provider import SummaryProvider


def build_summary_provider(
    profile: dict[str, Any],
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    context_override: int | None = None,
) -> SummaryProvider:
    provider_name = provider_override or _string(
        profile, "summary_provider", required=True
    )
    model = model_override or _string(profile, "summary_model")
    if provider_name == "ollama":
        return OllamaProvider(
            model=model or DEFAULT_OLLAMA_MODEL,
            base_url=_string(profile, "ollama_url") or "http://127.0.0.1:11434",
            context_tokens=context_override
            or _integer(profile, "summary_context_tokens", DEFAULT_CONTEXT_TOKENS),
            output_tokens=_integer(profile, "summary_output_tokens", 4_096),
        )
    if provider_name == "openai":
        raise SummarizationError(
            "The OpenAI summary provider is planned for the hosted-provider PR"
        )
    raise SummarizationError(f"Unknown summary provider: {provider_name}")


def _string(values: dict[str, Any], key: str, *, required: bool = False) -> str | None:
    value = values.get(key)
    if value is None:
        if required:
            raise SummarizationError(f"Profile is missing {key}")
        return None
    if not isinstance(value, str) or not value:
        raise SummarizationError(f"Profile value {key} must be a non-empty string")
    return value


def _integer(values: dict[str, Any], key: str, default: int) -> int:
    value = values.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise SummarizationError(f"Profile value {key} must be a positive integer")
    return value
