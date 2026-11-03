"""Nemotron 3 speaker diarization through MLX Audio."""

from __future__ import annotations

import math
import platform
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tranpro.diarization.models import (
    DiarizationDescriptor,
    DiarizationError,
    DiarizationOutput,
)
from tranpro.library.models import SpeakerTurn

DEFAULT_NEMOTRON_MODEL = "mlx-community/Nemotron-3-Diarization"
_PRESETS = {"offline", "low", "very_low", "ultra_low"}


class NemotronMLXProvider:
    """Run bounded-context, eight-speaker diarization on Apple Silicon."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_NEMOTRON_MODEL,
        preset: str = "offline",
        threshold: float = 0.5,
        min_duration: float = 0.1,
        merge_gap: float = 0.1,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        if preset not in _PRESETS:
            choices = ", ".join(sorted(_PRESETS))
            raise ValueError(f"unknown diarization preset {preset!r}; choose {choices}")
        if not math.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError("diarization threshold must be between 0 and 1")
        if not math.isfinite(min_duration) or min_duration < 0:
            raise ValueError("minimum speaker duration cannot be negative")
        if not math.isfinite(merge_gap) or merge_gap < 0:
            raise ValueError("speaker merge gap cannot be negative")
        self.model = model
        self.preset = preset
        self.threshold = threshold
        self.min_duration = min_duration
        self.merge_gap = merge_gap
        self._loader = loader

    @property
    def descriptor(self) -> DiarizationDescriptor:
        return DiarizationDescriptor(
            "nemotron-mlx",
            self.model,
            {
                "preset": self.preset,
                "threshold": self.threshold,
                "min_duration": self.min_duration,
                "merge_gap": self.merge_gap,
                "strict": True,
            },
        )

    def diarize(self, source: Path) -> DiarizationOutput:
        model = self._load_model()
        try:
            model.set_streaming_config(self.preset)
            result = model.generate(
                str(source),
                threshold=self.threshold,
                min_duration=self.min_duration,
                merge_gap=self.merge_gap,
                verbose=False,
            )
            turns = tuple(
                SpeakerTurn(
                    index=index,
                    start_ms=round(float(segment.start) * 1_000),
                    end_ms=round(float(segment.end) * 1_000),
                    speaker=f"speaker_{segment.speaker}",
                    source_speaker=f"speaker_{segment.speaker}",
                )
                for index, segment in enumerate(result.segments)
                if float(segment.end) > float(segment.start)
            )
        except DiarizationError:
            raise
        except Exception as error:
            raise DiarizationError(f"Nemotron diarization failed: {error}") from error
        return DiarizationOutput(turns)

    def _load_model(self) -> Any:
        if self._loader is not None:
            return self._loader(self.model)
        if sys.platform != "darwin" or platform.machine() != "arm64":
            raise DiarizationError("nemotron-mlx requires an Apple Silicon Mac")
        try:
            from mlx_audio.vad import load
        except ImportError as error:
            raise DiarizationError(
                "MLX Audio is not installed. With pipx, run: "
                "pipx inject tranpro 'mlx-audio>=0.6.2,<0.7'"
            ) from error
        try:
            return load(self.model, strict=True)
        except Exception as error:
            raise DiarizationError(
                f"Could not load Nemotron model {self.model}: {error}"
            ) from error
