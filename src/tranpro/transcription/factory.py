"""Construct transcription adapters from user profiles and CLI overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tranpro.transcription.models import TranscriptionError, TranscriptionProvider
from tranpro.transcription.parakeet import DEFAULT_PARAKEET_MODEL, ParakeetMLXProvider
from tranpro.transcription.whisper_cpp import WhisperCppProvider


def build_provider(
    profile: dict[str, Any],
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    whisper_cli_override: Path | None = None,
    language_override: str | None = None,
    live: bool = False,
) -> TranscriptionProvider:
    provider_name = provider_override or _string(
        profile, "transcription_provider", required=True
    )
    model = model_override or _string(profile, "transcription_model")

    if provider_name == "parakeet-mlx":
        return ParakeetMLXProvider(
            model=model or DEFAULT_PARAKEET_MODEL,
            chunk_duration=_number(profile, "chunk_duration", 120.0),
            overlap_duration=_number(profile, "overlap_duration", 15.0),
            live=live,
        )
    if provider_name == "whisper-cpp":
        if live:
            raise TranscriptionError(
                "Live transcription is currently supported only by parakeet-mlx"
            )
        if not model:
            raise TranscriptionError(
                "whisper-cpp requires a model path in the profile or --model"
            )
        configured_cli = _string(profile, "whisper_cli")
        executable = whisper_cli_override or (
            None if configured_cli is None else Path(configured_cli)
        )
        language = language_override or _string(profile, "language") or "auto"
        return WhisperCppProvider(
            model=Path(model), executable=executable, language=language
        )
    if provider_name == "openai":
        raise TranscriptionError(
            "The OpenAI transcription provider is planned for the hosted-provider PR"
        )
    raise TranscriptionError(f"Unknown transcription provider: {provider_name}")


def _string(values: dict[str, Any], key: str, *, required: bool = False) -> str | None:
    value = values.get(key)
    if value is None:
        if required:
            raise TranscriptionError(f"Profile is missing {key}")
        return None
    if not isinstance(value, str) or not value:
        raise TranscriptionError(f"Profile value {key} must be a non-empty string")
    return value


def _number(values: dict[str, Any], key: str, default: float) -> float:
    value = values.get(key, default)
    if not isinstance(value, int | float):
        raise TranscriptionError(f"Profile value {key} must be a number")
    return float(value)
