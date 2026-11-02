from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tranpro.transcription.models import (
    TranscriptionEvent,
    TranscriptionProgress,
    TranscriptSegmentFinalized,
)
from tranpro.transcription.parakeet import ParakeetMLXProvider, _ParakeetRuntime


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, float]] = []

    def transcribe(
        self, source: str, *, chunk_duration: float, overlap_duration: float
    ) -> Any:
        self.calls.append((source, chunk_duration, overlap_duration))
        return SimpleNamespace(
            sentences=[
                SimpleNamespace(text=" Hello world. ", start=1.234, end=2.345),
                SimpleNamespace(text="", start=3, end=4),
                SimpleNamespace(text="Next idea.", start=4, end=5),
            ]
        )


class FakeStreamingModel:
    def __init__(self) -> None:
        self.preprocessor_config = SimpleNamespace(sample_rate=2, hop_length=2)
        self.calls = 0

    def generate(self, mel: list[int]) -> list[Any]:
        texts = ["First sentence.", "Second sentence!", "Final trailing thought"]
        text = texts[self.calls]
        self.calls += 1
        token = SimpleNamespace(
            id=self.calls,
            text=text,
            start=0.0,
            end=1.0,
            duration=1.0,
        )
        return [SimpleNamespace(tokens=[token])]


def test_parakeet_normalizes_sentences_and_caches_model(tmp_path: Path) -> None:
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    model = FakeModel()
    loads: list[str] = []

    def load(model_name: str) -> FakeModel:
        loads.append(model_name)
        return model

    provider = ParakeetMLXProvider(
        "parakeet-test",
        chunk_duration=60,
        overlap_duration=10,
        loader=load,
    )

    first = provider.transcribe(source)
    provider.transcribe(source)

    assert loads == ["parakeet-test"]
    assert model.calls == [(str(source), 60, 10), (str(source), 60, 10)]
    assert [segment.text for segment in first.segments] == [
        "Hello world.",
        "Next idea.",
    ]
    assert first.segments[0].start_ms == 1234
    assert first.duration_ms == 5000


def test_parakeet_rejects_overlap_larger_than_chunk() -> None:
    with pytest.raises(ValueError, match="smaller"):
        ParakeetMLXProvider(chunk_duration=15, overlap_duration=15)


def test_parakeet_streams_only_stable_sentences_then_returns_final_result(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    model = FakeStreamingModel()
    events: list[TranscriptionEvent] = []

    def sentences(tokens: list[Any]) -> list[Any]:
        return [
            SimpleNamespace(text=token.text, start=token.start, end=token.end)
            for token in tokens
        ]

    runtime = _ParakeetRuntime(
        get_logmel=lambda audio, config: audio,
        tokens_to_sentences=sentences,
        sentences_to_result=lambda value: SimpleNamespace(sentences=value),
        merge_contiguous=lambda left, right, **kwargs: [*left, *right],
        merge_subsequence=lambda left, right, **kwargs: [*left, *right],
    )

    provider = ParakeetMLXProvider(
        "parakeet-test",
        live=True,
        chunk_duration=2,
        overlap_duration=0,
        loader=lambda model_name: model,
        audio_loader=lambda path, sample_rate: list(range(12)),
        runtime_loader=lambda: runtime,
    )

    result = provider.transcribe(source, emit=events.append)

    finalized = [
        event.segment.text
        for event in events
        if isinstance(event, TranscriptSegmentFinalized)
    ]
    progress = [event for event in events if isinstance(event, TranscriptionProgress)]
    assert finalized == [
        "First sentence.",
        "Second sentence!",
        "Final trailing thought",
    ]
    assert [segment.text for segment in result.segments] == finalized
    assert [event.completed_ms for event in progress] == [2000, 4000, 6000]
    assert provider.descriptor.settings == {
        "mode": "live",
        "chunk_duration": 2,
        "overlap_duration": 0,
    }


def test_parakeet_live_rejects_nonpositive_chunk_duration() -> None:
    with pytest.raises(ValueError, match="chunk_duration > 0"):
        ParakeetMLXProvider(live=True, chunk_duration=0)
