import json
import re
from pathlib import Path

import pytest

from tranpro.library.database import Database
from tranpro.library.models import (
    Segment,
    SpeakerAssignment,
    SpeakerTurn,
    SummarySection,
)
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths
from tranpro.summarization.models import (
    ContextWindow,
    SummaryRequest,
    SummaryResult,
)
from tranpro.summarization.ollama import SummarizationError
from tranpro.summarization.service import SummaryService


class FakeProvider:
    name = "fake"
    model = "fake-notes"

    def __init__(self, *, context_tokens: int = 1_000, fail: bool = False) -> None:
        self.context_window = ContextWindow(
            context_tokens,
            reserved_output_tokens=20,
            safety_margin_tokens=5,
        )
        self.fail = fail
        self.requests: list[SummaryRequest] = []

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        self.requests.append(request)
        if self.fail:
            raise SummarizationError("provider failed")
        if request.source_notes:
            refs = tuple(
                dict.fromkeys(
                    ref
                    for notes in request.source_notes
                    for ref in re.findall(r"s\d{6}", notes)
                )
            )
        else:
            refs = tuple(segment.stable_ref for segment in request.segments)
        sections = (SummarySection("Overview", "Grounded notes.", refs),)
        raw = json.dumps(
            {
                "sections": [
                    {
                        "heading": "Overview",
                        "body": "Grounded notes.",
                        "segment_refs": list(refs),
                    }
                ]
            }
        )
        return SummaryResult(sections, raw, {"input_tokens": 10})


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[LibraryRepository, Path, int]:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    repository = LibraryRepository(Database(paths))
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"audio")
    recording, _ = repository.register_recording(source)
    transcript = repository.add_transcript(
        recording.id,
        provider="test",
        model="test",
        segments=[
            Segment(0, 0, 1_000, "Scarcity requires choices."),
            Segment(1, 1_000, 2_000, "Prices coordinate those choices."),
        ],
    )
    return repository, source, transcript.id


def test_summary_service_persists_and_renders_grounded_result(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, source, transcript_id = seeded
    provider = FakeProvider()

    outcome = SummaryService(provider=provider, repository=repository).run(
        transcript_id
    )

    assert outcome.context_mode == "whole"
    assert outcome.output_path == source.with_name("lecture.summary.md")
    assert "00:00 (s000001)" in outcome.markdown
    assert "00:01 (s000002)" in outcome.markdown
    assert repository.get_summary(outcome.summary_id).status == "succeeded"
    assert len(repository.get_summary_steps(outcome.summary_id)) == 1


def test_summary_automatically_uses_and_records_preferred_diarization(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, _, transcript_id = seeded
    transcript = repository.get_transcript(transcript_id)
    diarization = repository.begin_diarization(
        transcript.recording_id, provider="test", model="speakers"
    )
    turns = [SpeakerTurn(0, 0, 2_000, "Speaker 1", "raw-0")]
    assignments = [
        SpeakerAssignment(0, "s000001", "Speaker 1", 1_000, 1.0, "assigned"),
        SpeakerAssignment(1, "s000002", "Speaker 1", 1_000, 1.0, "assigned"),
    ]
    repository.complete_diarization(
        diarization.id,
        transcript_id=transcript_id,
        turns=turns,
        assignments=assignments,
    )
    provider = FakeProvider()

    outcome = SummaryService(provider=provider, repository=repository).run(
        transcript_id
    )

    assert provider.requests[0].segments[0].speaker == "Speaker 1"
    assert outcome.diarization_id == diarization.id
    assert repository.get_summary(outcome.summary_id).diarization_id == diarization.id
    assert "diarization_id: 1" in outcome.markdown


def test_summary_can_explicitly_ignore_preferred_diarization(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, _, transcript_id = seeded
    transcript = repository.get_transcript(transcript_id)
    diarization = repository.begin_diarization(
        transcript.recording_id, provider="test", model="speakers"
    )
    repository.complete_diarization(
        diarization.id,
        transcript_id=transcript_id,
        turns=[SpeakerTurn(0, 0, 2_000, "Speaker 1", "raw-0")],
        assignments=[
            SpeakerAssignment(0, "s000001", "Speaker 1", 1_000, 1.0, "assigned"),
            SpeakerAssignment(1, "s000002", "Speaker 1", 1_000, 1.0, "assigned"),
        ],
    )
    provider = FakeProvider()

    outcome = SummaryService(provider=provider, repository=repository).run(
        transcript_id, use_speakers=False
    )

    assert provider.requests[0].segments[0].speaker is None
    assert outcome.diarization_id is None


def test_long_summary_uses_source_passes_then_synthesis(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, _, transcript_id = seeded
    original = repository.get_transcript(transcript_id)
    long_transcript = repository.add_transcript(
        original.recording_id,
        provider="test",
        model="long",
        segments=[
            Segment(
                index,
                index * 1_000,
                (index + 1) * 1_000,
                " ".join([f"topic{index}"] * 50),
            )
            for index in range(4)
        ],
    )
    provider = FakeProvider(context_tokens=220)

    outcome = SummaryService(provider=provider, repository=repository).run(
        long_transcript.id
    )

    steps = repository.get_summary_steps(outcome.summary_id)
    assert outcome.context_mode == "hierarchical"
    assert [step.kind for step in steps] == [
        "source",
        "source",
        "source",
        "source",
        "synthesis",
    ]
    assert steps[-1].input_step_indexes == (0, 1, 2, 3)
    assert len(provider.requests) == 5


def test_provider_failure_is_retained_as_a_failed_run(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, _, transcript_id = seeded

    with pytest.raises(SummarizationError, match="provider failed"):
        SummaryService(provider=FakeProvider(fail=True), repository=repository).run(
            transcript_id
        )

    summary = repository.list_summaries(1)[0]
    assert summary.status == "failed"
