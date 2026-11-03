import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tranpro import cli
from tranpro.library.database import Database
from tranpro.library.models import Segment, SummarySection
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths
from tranpro.summarization.models import (
    ContextWindow,
    SummaryRequest,
    SummaryResult,
)

runner = CliRunner()


class FakeSummaryProvider:
    name = "fake"
    model = "fake-summary"
    context_window = ContextWindow(2_000, 200, 50)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        refs = tuple(segment.stable_ref for segment in request.segments)
        section = SummarySection("Overview", "Summary body.", refs)
        raw = json.dumps(
            {
                "sections": [
                    {
                        "heading": section.heading,
                        "body": section.body,
                        "segment_refs": list(refs),
                    }
                ]
            }
        )
        return SummaryResult((section,), raw, {})


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[AppPaths, Path]:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli.AppPaths, "for_user", classmethod(lambda cls: paths))
    monkeypatch.setattr(
        cli, "build_summary_provider", lambda *args, **kwargs: FakeSummaryProvider()
    )
    source = tmp_path / "interview.mp3"
    source.write_bytes(b"audio")
    repository = LibraryRepository(Database(paths))
    recording, _ = repository.register_recording(source)
    repository.add_transcript(
        recording.id,
        provider="test",
        model="test",
        segments=[Segment(0, 5_000, 6_000, "A new concept is introduced.")],
    )
    return paths, source


def test_summarize_command_uses_preferred_transcript_and_writes_markdown(
    seeded: tuple[AppPaths, Path],
) -> None:
    _, source = seeded

    result = runner.invoke(cli.app, ["summarize", "1"])

    assert result.exit_code == 0
    assert "Created summary 1" in result.stdout
    assert "Context: whole" in result.stdout
    output = source.with_name("interview.summary.md")
    assert output.is_file()
    assert "00:05 (s000001)" in output.read_text(encoding="utf-8")


def test_summarize_rejects_transcript_from_another_recording(
    seeded: tuple[AppPaths, Path], tmp_path: Path
) -> None:
    paths, _ = seeded
    repository = LibraryRepository(Database(paths))
    other_source = tmp_path / "other.mp3"
    other_source.write_bytes(b"other")
    other, _ = repository.register_recording(other_source)
    other_transcript = repository.add_transcript(
        other.id,
        provider="test",
        model="test",
        segments=[Segment(0, 0, 1_000, "Other")],
    )

    result = runner.invoke(
        cli.app, ["summarize", "1", "--transcript", str(other_transcript.id)]
    )

    assert result.exit_code == 1
    assert "does not belong to recording 1" in result.stderr
