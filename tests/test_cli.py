import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tranpro import cli
from tranpro.paths import AppPaths

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("tranpro ")


def test_short_help_alias() -> None:
    result = runner.invoke(cli.app, ["-h"])

    assert result.exit_code == 0
    assert "Local-first transcription" in result.stdout
    assert "config" in result.stdout


def test_config_without_command_shows_help() -> None:
    result = runner.invoke(cli.app, ["config"])

    assert result.exit_code == 0
    assert "Inspect and edit tranpro configuration" in result.stdout
    assert "show" in result.stdout
    assert "init" in result.stdout
    assert "edit" in result.stdout


def test_config_short_help_alias() -> None:
    result = runner.invoke(cli.app, ["config", "-h"])

    assert result.exit_code == 0
    assert "Inspect and edit tranpro configuration" in result.stdout


def test_google_and_publish_commands_are_discoverable() -> None:
    root = runner.invoke(cli.app, ["--help"])
    google = runner.invoke(cli.app, ["google"])
    publish = runner.invoke(cli.app, ["publish", "--help"], color=True)

    assert root.exit_code == 0
    assert "publish" in root.stdout
    assert google.exit_code == 0
    assert "setup" in google.stdout
    assert "authorize" in google.stdout
    assert publish.exit_code == 0
    plain_help = re.sub(r"\x1b\[[0-9;]*m", "", publish.stdout)
    assert "--with-summary" in plain_help
    assert "--update" in plain_help


def test_paths_are_displayed_without_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli.AppPaths, "for_user", classmethod(lambda cls: paths))

    result = runner.invoke(cli.app, ["paths"])

    assert result.exit_code == 0
    assert str(paths.database_file) in result.stdout
    assert str(paths.cache_dir) in result.stdout
    assert not paths.data_dir.exists()


def test_config_show_labels_unsaved_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli.AppPaths, "for_user", classmethod(lambda cls: paths))

    result = runner.invoke(cli.app, ["config", "show"])

    assert result.exit_code == 0
    assert "Built-in defaults" in result.stdout
    assert 'transcription_provider = "parakeet-mlx"' in result.stdout
    assert not paths.config_file.exists()


def test_config_init_does_not_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli.AppPaths, "for_user", classmethod(lambda cls: paths))

    first = runner.invoke(cli.app, ["config", "init"])
    paths.config_file.write_text("version = 1\n# mine\n", encoding="utf-8")
    second = runner.invoke(cli.app, ["config", "init"])

    assert first.exit_code == 0
    assert "Created" in first.stdout
    assert second.exit_code == 0
    assert "Already exists" in second.stdout
    assert paths.config_file.read_text(encoding="utf-8") == "version = 1\n# mine\n"
