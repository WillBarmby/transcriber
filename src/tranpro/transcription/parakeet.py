"""Parakeet MLX provider for Apple Silicon."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tranpro.library.models import Segment
from tranpro.transcription.models import (
    ProviderDescriptor,
    TranscriptionError,
    TranscriptionEventSink,
    TranscriptionOutput,
)

DEFAULT_PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"


def _default_loader(model_name: str) -> Any:
    try:
        module = importlib.import_module("parakeet_mlx")
    except ImportError as error:
        raise TranscriptionError(
            "Parakeet MLX is not installed. Install it with "
            "`pip install 'tranpro[local]'`."
        ) from error
    return module.from_pretrained(model_name)


class ParakeetMLXProvider:
    """Normalize Parakeet's aligned sentences into tranpro segments."""

    def __init__(
        self,
        model: str = DEFAULT_PARAKEET_MODEL,
        *,
        chunk_duration: float = 120.0,
        overlap_duration: float = 15.0,
        loader: Callable[[str], Any] = _default_loader,
    ) -> None:
        if chunk_duration < 0:
            raise ValueError("chunk_duration cannot be negative")
        if overlap_duration < 0:
            raise ValueError("overlap_duration cannot be negative")
        if chunk_duration and overlap_duration >= chunk_duration:
            raise ValueError("overlap_duration must be smaller than chunk_duration")
        self.model_name = model
        self.chunk_duration = chunk_duration
        self.overlap_duration = overlap_duration
        self._loader = loader
        self._model: Any | None = None

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="parakeet-mlx",
            model=self.model_name,
            settings={
                "chunk_duration": self.chunk_duration,
                "overlap_duration": self.overlap_duration,
            },
        )

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput:
        try:
            if self._model is None:
                self._model = self._loader(self.model_name)
            result = self._model.transcribe(
                str(source),
                chunk_duration=self.chunk_duration,
                overlap_duration=self.overlap_duration,
            )
            sentences = result.sentences
        except TranscriptionError:
            raise
        except Exception as error:
            raise TranscriptionError(f"Parakeet MLX failed: {error}") from error

        segments: list[Segment] = []
        for sentence in sentences:
            text = str(sentence.text).strip()
            if not text:
                continue
            start_ms = max(0, round(float(sentence.start) * 1000))
            end_ms = max(start_ms, round(float(sentence.end) * 1000))
            segments.append(
                Segment(
                    index=len(segments),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                )
            )

        duration_ms = max((segment.end_ms for segment in segments), default=None)
        return TranscriptionOutput(tuple(segments), duration_ms=duration_ms)
