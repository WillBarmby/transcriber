from pathlib import Path

import pytest
from typer.testing import CliRunner

from tranpro import cli
from tranpro.paths import AppPaths
from tranpro.summarization import cli as summary_cli

runner = CliRunner()


@pytest.fixture
def app_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppPaths:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(
        summary_cli.AppPaths, "for_user", classmethod(lambda cls: paths)
    )
    return paths


def test_builtin_prompt_can_be_listed_and_shown(app_paths: AppPaths) -> None:
    listed = runner.invoke(cli.app, ["prompt", "list"])
    shown = runner.invoke(cli.app, ["prompt", "show", "detailed-notes"])

    assert listed.exit_code == 0
    assert "detailed-notes@1  built-in" in listed.stdout
    assert shown.exit_code == 0
    assert "key terms" in shown.stdout
    assert "sources cited" in shown.stdout


def test_save_creates_versions_without_overwriting(app_paths: AppPaths) -> None:
    first = runner.invoke(
        cli.app,
        ["prompt", "save", "my-notes", "-i", "Write short notes."],
    )
    second = runner.invoke(
        cli.app,
        ["prompt", "save", "my-notes", "-i", "Write longer notes."],
    )
    listed = runner.invoke(cli.app, ["prompt", "list", "--all"])

    assert first.stdout == "Saved my-notes@1\n"
    assert second.stdout == "Saved my-notes@2\n"
    assert "my-notes@2  user" in listed.stdout
    assert "my-notes@1  user" in listed.stdout


def test_save_accepts_a_prompt_file(app_paths: AppPaths, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Focus on disagreements.\n", encoding="utf-8")

    saved = runner.invoke(
        cli.app,
        ["prompt", "save", "debate", "--file", str(prompt_file)],
    )
    shown = runner.invoke(cli.app, ["prompt", "show", "debate"])

    assert saved.exit_code == 0
    assert shown.stdout.endswith("Focus on disagreements.\n")
