from pathlib import Path

import pytest
from typer.testing import CliRunner

from tranpro import cli
from tranpro.diarization import cli as diarization_cli
from tranpro.diarization.models import DiarizationDescriptor, DiarizationOutput
from tranpro.library.database import Database
from tranpro.library.models import Segment, SpeakerTurn
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths

runner = CliRunner()


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def descriptor(self) -> DiarizationDescriptor:
        return DiarizationDescriptor("fake", "speakers", {})

    def diarize(self, source: Path) -> DiarizationOutput:
        self.calls += 1
        return DiarizationOutput((SpeakerTurn(0, 0, 1_000, "raw-0", "raw-0"),))


@pytest.fixture
def seeded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[AppPaths, FakeProvider]:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    source = tmp_path / "interview.mp3"
    source.write_bytes(b"audio")
    repository = LibraryRepository(Database(paths))
    recording, _ = repository.register_recording(source)
    repository.add_transcript(
        recording.id,
        provider="fake",
        model="asr",
        segments=[Segment(0, 0, 1_000, "Hello")],
    )
    provider = FakeProvider()
    monkeypatch.setattr(
        diarization_cli.AppPaths, "for_user", classmethod(lambda cls: paths)
    )
    monkeypatch.setattr(
        diarization_cli,
        "build_diarization_provider",
        lambda *args, **kwargs: provider,
    )
    return paths, provider


def test_diarize_command_creates_and_reuses_run(
    seeded: tuple[AppPaths, FakeProvider],
) -> None:
    _, provider = seeded

    first = runner.invoke(cli.app, ["diarize", "1", "--no-progress"])
    second = runner.invoke(cli.app, ["diarize", "1", "--no-progress"])

    assert first.exit_code == 0
    assert "Created diarization 1" in first.stdout
    assert "1 speaker, 1 turn" in first.stdout
    assert "Markdown:" in first.stdout
    assert second.exit_code == 0
    assert "Reused diarization 1" in second.stdout
    assert provider.calls == 1


def test_diarize_rediarize_creates_new_run(
    seeded: tuple[AppPaths, FakeProvider],
) -> None:
    _, provider = seeded
    runner.invoke(cli.app, ["diarize", "1", "--no-progress"])

    result = runner.invoke(cli.app, ["diarize", "1", "--rediarize", "--no-progress"])

    assert result.exit_code == 0
    assert "Created diarization 2" in result.stdout
    assert provider.calls == 2
