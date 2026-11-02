"""Parakeet MLX provider for Apple Silicon."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tranpro.library.models import Segment
from tranpro.transcription.models import (
    ProviderDescriptor,
    TranscriptionError,
    TranscriptionEventSink,
    TranscriptionOutput,
    TranscriptionProgress,
    TranscriptSegmentFinalized,
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


def _default_audio_loader(path: Path, sample_rate: int) -> Any:
    try:
        audio_module = importlib.import_module("parakeet_mlx.audio")
    except ImportError as error:
        raise TranscriptionError(
            "Parakeet MLX is not installed. Install it with "
            "`pip install 'tranpro[local]'`."
        ) from error
    return audio_module.load_audio(path, sample_rate)


@dataclass(frozen=True, slots=True)
class _ParakeetRuntime:
    get_logmel: Callable[[Any, Any], Any]
    tokens_to_sentences: Callable[[list[Any]], list[Any]]
    sentences_to_result: Callable[[list[Any]], Any]
    merge_contiguous: Callable[..., list[Any]]
    merge_subsequence: Callable[..., list[Any]]


def _default_runtime_loader() -> _ParakeetRuntime:
    audio_module = importlib.import_module("parakeet_mlx.audio")
    alignment_module = importlib.import_module("parakeet_mlx.alignment")
    return _ParakeetRuntime(
        get_logmel=audio_module.get_logmel,
        tokens_to_sentences=alignment_module.tokens_to_sentences,
        sentences_to_result=alignment_module.sentences_to_result,
        merge_contiguous=alignment_module.merge_longest_contiguous,
        merge_subsequence=alignment_module.merge_longest_common_subsequence,
    )


class ParakeetMLXProvider:
    """Normalize Parakeet's aligned sentences into tranpro segments."""

    def __init__(
        self,
        model: str = DEFAULT_PARAKEET_MODEL,
        *,
        chunk_duration: float = 120.0,
        overlap_duration: float = 15.0,
        live: bool = False,
        loader: Callable[[str], Any] = _default_loader,
        audio_loader: Callable[[Path, int], Any] = _default_audio_loader,
        runtime_loader: Callable[[], _ParakeetRuntime] = _default_runtime_loader,
    ) -> None:
        if chunk_duration < 0:
            raise ValueError("chunk_duration cannot be negative")
        if overlap_duration < 0:
            raise ValueError("overlap_duration cannot be negative")
        if chunk_duration and overlap_duration >= chunk_duration:
            raise ValueError("overlap_duration must be smaller than chunk_duration")
        if live and chunk_duration <= 0:
            raise ValueError("live transcription requires chunk_duration > 0")
        self.model_name = model
        self.chunk_duration = chunk_duration
        self.overlap_duration = overlap_duration
        self.live = live
        self._loader = loader
        self._audio_loader = audio_loader
        self._runtime_loader = runtime_loader
        self._model: Any | None = None

    @property
    def descriptor(self) -> ProviderDescriptor:
        if self.live:
            settings: dict[str, float | str] = {
                "mode": "live",
                "chunk_duration": self.chunk_duration,
                "overlap_duration": self.overlap_duration,
            }
        else:
            settings = {
                "chunk_duration": self.chunk_duration,
                "overlap_duration": self.overlap_duration,
            }
        return ProviderDescriptor(
            name="parakeet-mlx",
            model=self.model_name,
            settings=settings,
        )

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput:
        try:
            if self._model is None:
                self._model = self._loader(self.model_name)
            if self.live:
                return self._transcribe_streaming(source, emit=emit)
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

        segments = self._normalize_sentences(sentences)
        duration_ms = max((segment.end_ms for segment in segments), default=None)
        return TranscriptionOutput(tuple(segments), duration_ms=duration_ms)

    def _transcribe_streaming(
        self, source: Path, *, emit: TranscriptionEventSink | None
    ) -> TranscriptionOutput:
        assert self._model is not None
        sample_rate = int(self._model.preprocessor_config.sample_rate)
        audio = self._audio_loader(source, sample_rate)
        total_samples = len(audio)
        chunk_samples = max(1, round(self.chunk_duration * sample_rate))
        overlap_samples = round(self.overlap_duration * sample_rate)
        step_samples = chunk_samples - overlap_samples
        runtime = self._runtime_loader()
        all_tokens: list[Any] = []
        emitted_segments = 0

        for start in range(0, total_samples, step_samples):
            end = min(start + chunk_samples, total_samples)
            chunk_audio = audio[start:end]
            if len(chunk_audio) < int(self._model.preprocessor_config.hop_length):
                break
            mel = runtime.get_logmel(chunk_audio, self._model.preprocessor_config)
            chunk_result = self._model.generate(mel)[0]
            offset_seconds = start / sample_rate
            for token in chunk_result.tokens:
                token.start += offset_seconds
                token.end = token.start + token.duration

            if not all_tokens:
                all_tokens = list(chunk_result.tokens)
            else:
                try:
                    all_tokens = runtime.merge_contiguous(
                        all_tokens,
                        chunk_result.tokens,
                        overlap_duration=self.overlap_duration,
                    )
                except RuntimeError:
                    all_tokens = runtime.merge_subsequence(
                        all_tokens,
                        chunk_result.tokens,
                        overlap_duration=self.overlap_duration,
                    )

            sentences = runtime.tokens_to_sentences(all_tokens)
            segments = self._normalize_sentences(sentences)
            safe_before_ms = (
                round((end / sample_rate - self.overlap_duration) * 1000)
                if end < total_samples
                else None
            )
            stable_segments = (
                segments
                if safe_before_ms is None
                else [
                    segment for segment in segments if segment.end_ms <= safe_before_ms
                ]
            )
            if emit is not None:
                for segment in stable_segments[emitted_segments:]:
                    emit(TranscriptSegmentFinalized(segment))
                emit(
                    TranscriptionProgress(
                        completed_ms=round(end / sample_rate * 1000),
                        total_ms=round(total_samples / sample_rate * 1000),
                    )
                )
            emitted_segments = len(stable_segments)
            if end == total_samples:
                break

        result = runtime.sentences_to_result(runtime.tokens_to_sentences(all_tokens))

        segments = self._normalize_sentences(result.sentences)
        if emit is not None:
            for segment in segments[emitted_segments:]:
                emit(TranscriptSegmentFinalized(segment))
        duration_ms = max((segment.end_ms for segment in segments), default=None)
        return TranscriptionOutput(tuple(segments), duration_ms=duration_ms)

    @staticmethod
    def _normalize_sentences(sentences: Any) -> list[Segment]:
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

        return segments
