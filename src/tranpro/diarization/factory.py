"""Construct diarization providers from user profiles and CLI overrides."""

from __future__ import annotations

from typing import Any

from tranpro.diarization.models import DiarizationError, DiarizationProvider
from tranpro.diarization.nemotron_mlx import (
    DEFAULT_NEMOTRON_MODEL,
    NemotronMLXProvider,
)


def build_diarization_provider(
    profile: dict[str, Any],
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    preset_override: str | None = None,
    threshold_override: float | None = None,
    min_duration_override: float | None = None,
    merge_gap_override: float | None = None,
) -> DiarizationProvider:
    provider = provider_override or str(
        profile.get("diarization_provider", "nemotron-mlx")
    )
    if provider != "nemotron-mlx":
        raise DiarizationError(
            f"Unsupported diarization provider {provider!r}; choose nemotron-mlx"
        )
    return NemotronMLXProvider(
        model=model_override
        or str(profile.get("diarization_model", DEFAULT_NEMOTRON_MODEL)),
        preset=preset_override or str(profile.get("diarization_preset", "offline")),
        threshold=(
            threshold_override
            if threshold_override is not None
            else float(profile.get("diarization_threshold", 0.5))
        ),
        min_duration=(
            min_duration_override
            if min_duration_override is not None
            else float(profile.get("diarization_min_duration", 0.1))
        ),
        merge_gap=(
            merge_gap_override
            if merge_gap_override is not None
            else float(profile.get("diarization_merge_gap", 0.1))
        ),
    )
