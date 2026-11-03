from pathlib import Path

import pytest

from tranpro.library.database import Database
from tranpro.library.models import (
    Segment,
    SpeakerAssignment,
    SpeakerTurn,
    SummarySection,
)
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


def test_reregistering_forgotten_content_restores_and_updates_path(
    repository: LibraryRepository, recording_path: Path, tmp_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)
    repository.forget(recording.id)
    moved = tmp_path / "moved.m4a"
    recording_path.rename(moved)

    restored, created = repository.register_recording(moved)

    assert created is False
    assert restored.id == recording.id
    assert restored.deleted_at is None
    assert restored.current_path == moved


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


def test_diarization_runs_are_immutable_preferred_artifacts(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)
    transcript = repository.add_transcript(
        recording.id,
        provider="test",
        model="asr",
        segments=[Segment(0, 0, 1_000, "Hello")],
    )
    first = repository.begin_diarization(
        recording.id,
        provider="test",
        model="speakers-v1",
        settings={"threshold": 0.6},
    )
    turn = SpeakerTurn(0, 0, 1_000, "Speaker 1", "channel-0", 0.9)
    assignment = SpeakerAssignment(0, "s000001", "Speaker 1", 1_000, 1.0, "assigned")
    completed = repository.complete_diarization(
        first.id,
        transcript_id=transcript.id,
        turns=[turn],
        assignments=[assignment],
    )
    second = repository.begin_diarization(
        recording.id,
        provider="test",
        model="speakers-v2",
    )
    repository.complete_diarization(
        second.id,
        transcript_id=transcript.id,
        turns=[turn],
        assignments=[assignment],
    )

    runs = repository.list_diarizations(recording.id)

    assert completed.status == "succeeded"
    assert [run.is_preferred for run in runs] == [True, False]
    assert repository.get_preferred_diarization(recording.id).id == second.id
    assert repository.get_speaker_turns(first.id) == [turn]
    assert repository.get_speaker_assignments(first.id, transcript.id) == [assignment]
    assert repository.get_diarized_segments(first.id, transcript.id)[0].speaker == (
        "Speaker 1"
    )
    reusable = repository.find_reusable_diarization(
        recording.id,
        provider="test",
        model="speakers-v1",
        settings={"threshold": 0.6},
    )
    assert reusable is not None
    assert reusable.id == first.id


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


def test_empty_transcript_is_a_valid_successful_run(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)

    transcript = repository.add_transcript(
        recording.id,
        provider="test",
        model="silence",
        segments=[],
    )

    assert transcript.status == "succeeded"
    assert repository.get_segments(transcript.id) == []


def test_missing_recording_has_domain_error(repository: LibraryRepository) -> None:
    with pytest.raises(RecordNotFoundError, match="Recording 404"):
        repository.get_recording(404)


def test_prompts_are_versioned_and_builtin_is_available(
    repository: LibraryRepository,
) -> None:
    builtin = repository.get_prompt("detailed-notes")
    first = repository.save_prompt("brief", "Summarize briefly.")
    second = repository.save_prompt("brief", "Use exactly five bullets.")

    assert builtin.is_builtin is True
    assert (first.version, second.version) == (1, 2)
    assert repository.get_prompt("brief").instructions == "Use exactly five bullets."
    assert [prompt.name for prompt in repository.list_prompts()] == [
        "brief",
        "detailed-notes",
    ]
    assert len(repository.list_prompts(all_versions=True)) == 3


def test_summary_lifecycle_preserves_plan_steps_and_validates_citations(
    repository: LibraryRepository, recording_path: Path
) -> None:
    recording, _ = repository.register_recording(recording_path)
    transcript = repository.add_transcript(
        recording.id,
        provider="test",
        model="test",
        segments=[Segment(0, 0, 1_000, "A grounded claim")],
    )
    run = repository.begin_summary(
        transcript.id,
        prompt=repository.get_prompt("detailed-notes"),
        system_contract="Return structured notes.",
        provider="test",
        model="test",
        context_plan={"mode": "whole"},
    )
    step = repository.add_summary_step(
        run.id,
        kind="source",
        input_segment_refs=("s000001",),
        output_text="Intermediate notes",
        usage={"input_tokens": 12},
    )

    with pytest.raises(ValueError, match="s999999"):
        repository.complete_summary(
            run.id,
            [SummarySection("Bad citation", "Body", ("s999999",))],
        )

    completed = repository.complete_summary(
        run.id,
        [SummarySection("Grounded", "Body", ("s000001",))],
    )

    assert step.index == 0
    assert completed.status == "succeeded"
    assert repository.get_summary_steps(run.id) == [step]
    assert repository.get_summary_sections(run.id)[0].segment_refs == ("s000001",)
