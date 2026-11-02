from pathlib import Path

import pytest
from typer.testing import CliRunner

from tranpro import cli
from tranpro.library import cli as library_cli
from tranpro.library.database import Database
from tranpro.library.models import Segment, SummarySection
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths

runner = CliRunner()


@pytest.fixture
def app_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppPaths:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(
        library_cli.AppPaths, "for_user", classmethod(lambda cls: paths)
    )
    return paths


def seed_library(app_paths: AppPaths, tmp_path: Path) -> int:
    source = tmp_path / "policy-discussion.m4a"
    source.write_bytes(b"audio")
    repository = LibraryRepository(Database(app_paths))
    recording, _ = repository.register_recording(
        source, duration_ms=3_723_000, language="en"
    )
    transcript = repository.add_transcript(
        recording.id,
        provider="parakeet-mlx",
        model="parakeet-v3",
        language="en",
        segments=[
            Segment(
                0,
                62_000,
                65_000,
                "Fiscal policy changes household demand.",
                "Host",
            )
        ],
    )
    repository.add_summary(
        transcript.id,
        provider="ollama",
        model="gemma4:12b",
        sections=[
            SummarySection(
                "Key concepts",
                "Budget constraints shape household choices.",
                ("s000001",),
            )
        ],
    )
    return recording.id


def test_library_without_command_shows_help() -> None:
    result = runner.invoke(cli.app, ["library"])

    assert result.exit_code == 0
    assert "Manage the local transcript library" in result.stdout
    assert "init" in result.stdout
    assert "status" in result.stdout
    assert "reveal" in result.stdout


def test_library_init_and_status_use_platform_paths(app_paths: AppPaths) -> None:
    initialized = runner.invoke(cli.app, ["library", "init"])
    status = runner.invoke(cli.app, ["library", "status"])

    assert initialized.exit_code == 0
    assert "Library schema 1 ready" in initialized.stdout
    assert str(app_paths.database_file) in initialized.stdout
    assert status.exit_code == 0
    assert "Recordings   0" in status.stdout
    assert "Transcripts  0" in status.stdout


def test_empty_list_is_explanatory(app_paths: AppPaths) -> None:
    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert result.stdout == "No recordings in the library yet.\n"
    assert app_paths.database_file.exists()


def test_list_show_and_search_render_artifact_context(
    app_paths: AppPaths, tmp_path: Path
) -> None:
    recording_id = seed_library(app_paths, tmp_path)

    listed = runner.invoke(cli.app, ["list"])
    shown = runner.invoke(cli.app, ["show", str(recording_id)])
    searched = runner.invoke(cli.app, ["search", "fiscal policy"])

    assert listed.exit_code == 0
    assert "1:02:03" in listed.stdout
    assert "policy-discussion.m4a" in listed.stdout
    assert shown.exit_code == 0
    assert "parakeet-mlx/parakeet-v3 succeeded preferred" in shown.stdout
    assert "ollama/gemma4:12b succeeded prompt=detailed-notes@1" in shown.stdout
    assert searched.exit_code == 0
    assert "transcript #1 01:02 · s000001" in searched.stdout
    assert "[Fiscal] [policy]" in searched.stdout


def test_forget_and_restore_are_recoverable(
    app_paths: AppPaths, tmp_path: Path
) -> None:
    recording_id = seed_library(app_paths, tmp_path)

    forgotten = runner.invoke(cli.app, ["forget", str(recording_id)])
    hidden = runner.invoke(cli.app, ["list"])
    all_recordings = runner.invoke(cli.app, ["list", "--all"])
    restored = runner.invoke(cli.app, ["restore", str(recording_id)])

    assert forgotten.exit_code == 0
    assert "restore it with `tp restore`" in forgotten.stdout
    assert "No recordings" in hidden.stdout
    assert "deleted" in all_recordings.stdout
    assert restored.exit_code == 0
    assert "Restored recording" in restored.stdout


def test_missing_recording_error_is_concise(app_paths: AppPaths) -> None:
    result = runner.invoke(cli.app, ["show", "404"])

    assert result.exit_code == 1
    assert result.stderr == "Error: Recording 404 was not found\n"


def test_reveal_creates_and_launches_data_directory(
    app_paths: AppPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    launched: list[str] = []
    monkeypatch.setattr(library_cli.typer, "launch", launched.append)

    result = runner.invoke(cli.app, ["library", "reveal"])

    assert result.exit_code == 0
    assert launched == [str(app_paths.data_dir)]
    assert app_paths.data_dir.is_dir()
