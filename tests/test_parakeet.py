from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tranpro.transcription.parakeet import ParakeetMLXProvider


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
