from pathlib import Path

import pytest
from typer.testing import CliRunner

from tranpro import cli
from tranpro.library.models import Segment
from tranpro.paths import AppPaths
from tranpro.transcription.models import (
    ProviderDescriptor,
    TranscriptionEventSink,
    TranscriptionOutput,
)

runner = CliRunner()


class FakeProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor("fake", "test-model", {})

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput:
        return TranscriptionOutput((Segment(0, 0, 1000, "CLI transcript."),))


@pytest.fixture
def app_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppPaths:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli.AppPaths, "for_user", classmethod(lambda cls: paths))
    monkeypatch.setattr(cli, "build_provider", lambda *args, **kwargs: FakeProvider())
    return paths


def test_path_is_default_transcription_command(
    app_paths: AppPaths, tmp_path: Path
) -> None:
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"audio")

    result = runner.invoke(cli.app, [str(source)])

    assert result.exit_code == 0
    assert "Created transcript 1" in result.stdout
    assert source.with_name("recording.transcript.md").is_file()
    assert app_paths.database_file.is_file()


def test_explicit_transcribe_command_and_stdout_do_not_save(
    app_paths: AppPaths, tmp_path: Path
) -> None:
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")

    result = runner.invoke(
        cli.app, ["transcribe", str(source), "--no-save", "--output", "-"]
    )

    assert result.exit_code == 0
    assert "# Transcript: recording" in result.stdout
    assert "CLI transcript." in result.stdout
    assert not app_paths.database_file.exists()
    assert not source.with_name("recording.transcript.md").exists()


def test_unknown_audio_path_has_concise_error(app_paths: AppPaths) -> None:
    result = runner.invoke(cli.app, ["missing.mp3"])

    assert result.exit_code == 1
    assert "Error: Source audio not found" in result.stderr


def test_existing_commands_still_win_over_default_file_routing(
    app_paths: AppPaths,
) -> None:
    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert "No recordings" in result.stdout
