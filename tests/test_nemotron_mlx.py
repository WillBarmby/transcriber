from pathlib import Path
from types import SimpleNamespace

import pytest

from tranpro.diarization.models import DiarizationError
from tranpro.diarization.nemotron_mlx import NemotronMLXProvider


class FakeModel:
    def __init__(self) -> None:
        self.preset: str | None = None
        self.arguments: dict[str, object] = {}

    def set_streaming_config(self, preset: str) -> None:
        self.preset = preset

    def generate(self, source: str, **arguments: object) -> object:
        self.arguments = {"source": source, **arguments}
        return SimpleNamespace(
            segments=[
                SimpleNamespace(start=0.25, end=1.75, speaker=3),
                SimpleNamespace(start=1.75, end=2.5, speaker=1),
            ]
        )


def test_provider_loads_strict_model_and_normalizes_millisecond_turns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "meeting.m4a"
    source.write_bytes(b"audio")
    model = FakeModel()
    loaded: list[str] = []

    def load(model_name: str) -> FakeModel:
        loaded.append(model_name)
        return model

    provider = NemotronMLXProvider(
        model="local/nemotron",
        preset="offline",
        threshold=0.45,
        min_duration=0.2,
        merge_gap=0.15,
        loader=load,
    )

    output = provider.diarize(source)

    assert loaded == ["local/nemotron"]
    assert model.preset == "offline"
    assert model.arguments == {
        "source": str(source),
        "threshold": 0.45,
        "min_duration": 0.2,
        "merge_gap": 0.15,
        "verbose": False,
    }
    assert [
        (turn.start_ms, turn.end_ms, turn.source_speaker) for turn in output.turns
    ] == [(250, 1_750, "speaker_3"), (1_750, 2_500, "speaker_1")]


def test_provider_settings_are_complete_reuse_inputs() -> None:
    descriptor = NemotronMLXProvider(loader=lambda _: FakeModel()).descriptor

    assert descriptor.name == "nemotron-mlx"
    assert descriptor.settings == {
        "preset": "offline",
        "threshold": 0.5,
        "min_duration": 0.1,
        "merge_gap": 0.1,
        "strict": True,
    }


@pytest.mark.parametrize("threshold", [0, 1, float("nan")])
def test_provider_rejects_invalid_thresholds(threshold: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        NemotronMLXProvider(threshold=threshold)


def test_provider_wraps_runtime_errors() -> None:
    class BrokenModel(FakeModel):
        def generate(self, source: str, **arguments: object) -> object:
            raise RuntimeError("Metal allocation failed")

    with pytest.raises(DiarizationError, match="Metal allocation failed"):
        NemotronMLXProvider(loader=lambda _: BrokenModel()).diarize(Path("audio.wav"))
