from pathlib import Path

import pytest

from tranpro.library.models import Segment
from tranpro.transcription.models import TranscriptionError
from tranpro.transcription.render import render_markdown, write_markdown


def transcript(source: Path, *, transcript_id: int = 2) -> str:
    return render_markdown(
        source=source,
        segments=(Segment(0, 62_000, 65_000, "A useful idea.", "Host"),),
        provider="test",
        model="model",
        recording_id=1,
        transcript_id=transcript_id,
    )


def test_rendered_markdown_has_provenance_and_timestamp(tmp_path: Path) -> None:
    source = tmp_path / "podcast.m4a"

    markdown = transcript(source)

    assert 'provider: "test"' in markdown
    assert "transcript_id: 2" in markdown
    assert "[01:02] **Host:** A useful idea." in markdown


def test_default_output_versions_conflicting_content(tmp_path: Path) -> None:
    source = tmp_path / "podcast.m4a"
    source.write_bytes(b"audio")
    first = write_markdown(
        transcript(source), source=source, requested_path=None, force=False
    )
    repeated = write_markdown(
        transcript(source), source=source, requested_path=None, force=False
    )
    second = write_markdown(
        transcript(source, transcript_id=3),
        source=source,
        requested_path=None,
        force=False,
    )

    assert first.name == "podcast.transcript.md"
    assert repeated == first
    assert second.name == "podcast.transcript.2.md"


def test_explicit_output_requires_force_to_replace(tmp_path: Path) -> None:
    source = tmp_path / "podcast.m4a"
    source.write_bytes(b"audio")
    output = tmp_path / "notes.md"
    output.write_text("personal notes", encoding="utf-8")

    with pytest.raises(TranscriptionError, match="--force"):
        write_markdown(
            transcript(source), source=source, requested_path=output, force=False
        )

    replaced = write_markdown(
        transcript(source), source=source, requested_path=output, force=True
    )
    assert replaced == output
    assert "A useful idea" in output.read_text(encoding="utf-8")
