from pathlib import Path

import pytest

from tranpro.diarization.models import (
    DiarizationDescriptor,
    DiarizationError,
    DiarizationOutput,
)
from tranpro.diarization.service import DiarizationService
from tranpro.library.database import Database
from tranpro.library.models import Segment, SpeakerTurn
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths


class FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    @property
    def descriptor(self) -> DiarizationDescriptor:
        return DiarizationDescriptor("fake", "speakers-v1", {"max_speakers": 8})

    def diarize(self, source: Path) -> DiarizationOutput:
        self.calls += 1
        if self.fail:
            raise RuntimeError("model exploded")
        return DiarizationOutput(
            (
                SpeakerTurn(0, 0, 1_000, "raw-b", "raw-b"),
                SpeakerTurn(1, 1_000, 2_000, "raw-a", "raw-a"),
            )
        )


def seed(tmp_path: Path) -> tuple[LibraryRepository, int, int]:
    repository = LibraryRepository(
        Database(AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache"))
    )
    source = tmp_path / "interview.mp3"
    source.write_bytes(b"audio")
    recording, _ = repository.register_recording(source)
    transcript = repository.add_transcript(
        recording.id,
        provider="fake",
        model="asr",
        segments=[
            Segment(0, 0, 1_000, "First voice"),
            Segment(1, 1_000, 2_000, "Second voice"),
        ],
    )
    return repository, recording.id, transcript.id


def test_service_runs_normalizes_persists_and_reuses(tmp_path: Path) -> None:
    repository, recording_id, transcript_id = seed(tmp_path)
    provider = FakeProvider()
    service = DiarizationService(provider=provider, repository=repository)

    first = service.run(recording_id)
    second = service.run(recording_id)

    assert provider.calls == 1
    assert first.reused is False
    assert second.reused is True
    assert second.diarization_id == first.diarization_id
    assert [segment.speaker for segment in first.segments] == [
        "Speaker 1",
        "Speaker 2",
    ]
    assert repository.get_speaker_assignments(first.diarization_id, transcript_id)


def test_rediarize_creates_a_new_preferred_run(tmp_path: Path) -> None:
    repository, recording_id, _ = seed(tmp_path)
    provider = FakeProvider()
    service = DiarizationService(provider=provider, repository=repository)

    first = service.run(recording_id)
    second = service.run(recording_id, rediarize=True)

    assert provider.calls == 2
    assert second.diarization_id != first.diarization_id
    assert (
        repository.get_preferred_diarization(recording_id).id == second.diarization_id
    )


def test_failed_provider_leaves_an_auditable_failed_run(tmp_path: Path) -> None:
    repository, recording_id, _ = seed(tmp_path)

    with pytest.raises(DiarizationError, match="model exploded"):
        DiarizationService(provider=FakeProvider(fail=True), repository=repository).run(
            recording_id
        )

    runs = repository.list_diarizations(recording_id)
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].is_preferred is False
