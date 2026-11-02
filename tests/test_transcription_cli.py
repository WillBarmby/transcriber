from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from tranpro import cli
from tranpro.library.models import Segment
from tranpro.paths import AppPaths
from tranpro.transcription.models import (
    ProviderDescriptor,
    TranscriptionEventSink,
    TranscriptionOutput,
    TranscriptionProgress,
    TranscriptSegmentFinalized,
)

runner = CliRunner()


class FakeProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor("fake", "test-model", {})

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput:
        segment = Segment(0, 0, 1000, "CLI transcript.")
        if emit is not None:
            emit(TranscriptSegmentFinalized(segment))
        return TranscriptionOutput((segment,))


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


def test_live_prints_finalized_segments_and_still_writes_output(
    app_paths: AppPaths, tmp_path: Path
) -> None:
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")

    result = runner.invoke(cli.app, [str(source), "--live"])

    assert result.exit_code == 0
    assert "[00:00] CLI transcript." in result.stdout
    assert "Created transcript 1" in result.stdout
    assert source.with_name("recording.transcript.md").is_file()


def test_live_rejects_duplicate_stdout_mode(
    app_paths: AppPaths, tmp_path: Path
) -> None:
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")

    result = runner.invoke(cli.app, [str(source), "--live", "--output", "-"])

    assert result.exit_code == 1
    assert "--live cannot be combined with --output -" in result.stderr


def test_progress_renderer_shows_completion() -> None:
    output = StringIO()
    renderer = cli.TerminalProgress(
        enabled=True,
        console=Console(file=output, force_terminal=True, width=100),
    )

    with renderer:
        renderer.emit(TranscriptionProgress(completed_ms=500, total_ms=1000))
        renderer.complete(reused=False)

    rendered = output.getvalue()
    assert "Transcribed" in rendered
    assert "100%" in rendered


def test_no_progress_option_is_available(app_paths: AppPaths, tmp_path: Path) -> None:
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")

    result = runner.invoke(cli.app, [str(source), "--no-progress"])

    assert result.exit_code == 0
    assert "Created transcript 1" in result.stdout
