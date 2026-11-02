from pathlib import Path

import pytest

from tranpro.library.database import Database
from tranpro.library.models import Segment, SummarySection
from tranpro.library.repository import LibraryRepository, RecordNotFoundError
from tranpro.paths import AppPaths


@pytest.fixture
def repository(tmp_path: Path) -> LibraryRepository:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    return LibraryRepository(Database(paths))


@pytest.fixture
def recording_path(tmp_path: Path) -> Path:
    path = tmp_path / "economics-podcast.m4a"
    path.write_bytes(b"pretend audio content")
    return path


def test_register_recording_deduplicates_by_content(
    repository: LibraryRepository, recording_path: Path, tmp_path: Path
) -> None:
    first, first_created = repository.register_recording(recording_path)
    duplicate_path = tmp_path / "copy.m4a"
    duplicate_path.write_bytes(recording_path.read_bytes())

    second, second_created = repository.register_recording(duplicate_path)

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert len(repository.list_recordings()) == 1


def test_transcripts_are_versioned_and_exact_settings_are_reusable(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)
    first = repository.add_transcript(
        recording.id,
        provider="parakeet-mlx",
        model="parakeet-v3",
        settings={"language": "en", "temperature": 0},
        segments=[Segment(0, 0, 1_000, "First version")],
    )
    second = repository.add_transcript(
        recording.id,
        provider="openai",
        model="gpt-transcribe",
        segments=[Segment(0, 0, 1_000, "Second version")],
    )

    runs = repository.list_transcripts(recording.id)
    reusable = repository.find_reusable_transcript(
        recording.id,
        provider="parakeet-mlx",
        model="parakeet-v3",
        settings={"temperature": 0, "language": "en"},
    )

    assert [run.id for run in runs] == [second.id, first.id]
    assert [run.is_preferred for run in runs] == [True, False]
    assert reusable is not None
    assert reusable.id == first.id


def test_full_text_search_covers_transcripts_and_summaries(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)
    transcript = repository.add_transcript(
        recording.id,
        provider="parakeet-mlx",
        model="parakeet-v3",
        segments=[
            Segment(
                0,
                0,
                2_000,
                "Households face heterogeneous budget constraints.",
                "Ada",
            ),
            Segment(1, 2_000, 4_000, "A separate discussion of music."),
        ],
    )
    repository.add_summary(
        transcript.id,
        provider="ollama",
        model="gemma4:12b",
        sections=[
            SummarySection(
                "Key concepts",
                "Supply and demand interact under scarcity.",
                ("s000001",),
            )
        ],
    )

    transcript_hits = repository.search("budget constraints")
    summary_hits = repository.search("supply scarcity", kind="summary")

    assert len(transcript_hits) == 1
    assert transcript_hits[0].kind == "transcript"
    assert transcript_hits[0].location == "s000001"
    assert "[budget] [constraints]" in transcript_hits[0].snippet
    assert len(summary_hits) == 1
    assert summary_hits[0].kind == "summary"
    assert summary_hits[0].recording_id == recording.id


def test_forget_hides_recording_and_search_results_until_restore(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)
    repository.add_transcript(
        recording.id,
        provider="parakeet-mlx",
        model="parakeet-v3",
        segments=[Segment(0, 0, 1_000, "Macroeconomic expectations")],
    )

    assert repository.forget(recording.id) is True
    assert repository.forget(recording.id) is False
    assert repository.list_recordings() == []
    assert repository.search("macroeconomic") == []
    assert repository.get_recording(recording.id).deleted_at is not None

    assert repository.restore(recording.id) is True
    assert repository.restore(recording.id) is False
    assert repository.search("macroeconomic")[0].recording_id == recording.id


def test_failed_segment_validation_does_not_create_a_run(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)

    with pytest.raises(ValueError, match="contiguous"):
        repository.add_transcript(
            recording.id,
            provider="test",
            model="test",
            segments=[Segment(2, 0, 100, "Wrong index")],
        )

    assert repository.list_transcripts(recording.id) == []


def test_missing_recording_has_domain_error(repository: LibraryRepository) -> None:
    with pytest.raises(RecordNotFoundError, match="Recording 404"):
        repository.get_recording(404)
