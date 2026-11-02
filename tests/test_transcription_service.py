from pathlib import Path

import pytest

from tranpro.library.database import Database
from tranpro.library.models import Segment
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths
from tranpro.transcription.models import (
    ProviderDescriptor,
    TranscriptionError,
    TranscriptionEvent,
    TranscriptionEventSink,
    TranscriptionOutput,
    TranscriptionProgress,
    TranscriptionRequest,
    TranscriptReplayStarted,
    TranscriptSegmentFinalized,
)
from tranpro.transcription.service import TranscriptionService


class FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor("fake", "v1", {"quality": "good"})

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput:
        self.calls += 1
        if self.fail:
            raise TranscriptionError("provider failure")
        segment = Segment(0, 0, 1000, "A transcript.")
        if emit is not None:
            emit(TranscriptionProgress(completed_ms=1000, total_ms=1000))
            emit(TranscriptSegmentFinalized(segment))
        return TranscriptionOutput(
            (segment,),
            language="en",
            duration_ms=1000,
        )


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "podcast.m4a"
    path.write_bytes(b"audio")
    return path


def service(
    paths: AppPaths,
    provider: FakeProvider,
    *,
    trash: list[str] | None = None,
) -> TranscriptionService:
    return TranscriptionService(
        provider=provider,
        repository=LibraryRepository(Database(paths)),
        duration_probe=lambda path: 1200,
        trash=(lambda path: trash.append(path))
        if trash is not None
        else lambda path: None,
    )


def test_success_persists_and_equivalent_second_run_reuses(
    paths: AppPaths, source: Path
) -> None:
    provider = FakeProvider()
    transcription = service(paths, provider)

    first = transcription.run(TranscriptionRequest(source))
    second = transcription.run(TranscriptionRequest(source))

    assert provider.calls == 1
    assert first.reused is False
    assert second.reused is True
    assert second.transcript_id == first.transcript_id
    assert first.output_path == source.with_name("podcast.transcript.md")
    assert len(LibraryRepository(Database(paths)).list_recordings()) == 1


def test_events_flow_from_provider_and_replay_from_reused_run(
    paths: AppPaths, source: Path
) -> None:
    provider = FakeProvider()
    transcription = service(paths, provider)
    first_events: list[TranscriptionEvent] = []
    replay_events: list[TranscriptionEvent] = []

    first = transcription.run(TranscriptionRequest(source), emit=first_events.append)
    transcription.run(TranscriptionRequest(source), emit=replay_events.append)

    assert first_events == [
        TranscriptionProgress(completed_ms=1000, total_ms=1000),
        TranscriptSegmentFinalized(Segment(0, 0, 1000, "A transcript.")),
    ]
    assert replay_events == [
        TranscriptReplayStarted(first.transcript_id or 0),
        TranscriptSegmentFinalized(Segment(0, 0, 1000, "A transcript.")),
    ]


def test_retranscribe_creates_new_version_and_non_overwriting_markdown(
    paths: AppPaths, source: Path
) -> None:
    provider = FakeProvider()
    transcription = service(paths, provider)
    first = transcription.run(TranscriptionRequest(source))

    second = transcription.run(TranscriptionRequest(source, retranscribe=True))

    assert provider.calls == 2
    assert second.transcript_id != first.transcript_id
    assert second.output_path == source.with_name("podcast.transcript.2.md")
    runs = LibraryRepository(Database(paths)).list_transcripts(first.recording_id or 0)
    assert len(runs) == 2
    assert runs[0].is_preferred is True


def test_no_save_avoids_database_but_still_writes_markdown(
    paths: AppPaths, source: Path
) -> None:
    provider = FakeProvider()
    transcription = service(paths, provider)

    outcome = transcription.run(TranscriptionRequest(source, save=False))

    assert outcome.recording_id is None
    assert outcome.transcript_id is None
    assert outcome.output_path is not None and outcome.output_path.is_file()
    assert not paths.database_file.exists()


def test_provider_failure_creates_no_record_or_output(
    paths: AppPaths, source: Path
) -> None:
    transcription = service(paths, FakeProvider(fail=True))

    with pytest.raises(TranscriptionError, match="provider failure"):
        transcription.run(TranscriptionRequest(source))

    assert LibraryRepository(Database(paths)).list_recordings() == []
    assert not source.with_name("podcast.transcript.md").exists()


def test_trash_is_explicitly_finalized_after_output(
    paths: AppPaths, source: Path
) -> None:
    trashed: list[str] = []
    transcription = service(paths, FakeProvider(), trash=trashed)
    outcome = transcription.run(TranscriptionRequest(source, trash_source=True))

    assert trashed == []
    assert outcome.output_path is not None and outcome.output_path.is_file()
    transcription.finalize_trash(outcome)

    assert trashed == [str(source)]
    recording = LibraryRepository(Database(paths)).get_recording(
        outcome.recording_id or 0
    )
    assert recording.current_path is None


def test_stdout_mode_returns_markdown_without_file(
    paths: AppPaths, source: Path
) -> None:
    outcome = service(paths, FakeProvider()).run(
        TranscriptionRequest(source, output_to_stdout=True, save=False)
    )

    assert "# Transcript: podcast" in outcome.markdown
    assert outcome.output_path is None
    assert not source.with_name("podcast.transcript.md").exists()


def test_force_replaces_explicit_projection_and_updates_its_record(
    paths: AppPaths, source: Path, tmp_path: Path
) -> None:
    provider = FakeProvider()
    transcription = service(paths, provider)
    output = tmp_path / "chosen.md"
    first = transcription.run(TranscriptionRequest(source, output=output))

    second = transcription.run(
        TranscriptionRequest(
            source,
            output=output,
            retranscribe=True,
            force=True,
        )
    )

    assert second.transcript_id != first.transcript_id
    rendered = LibraryRepository(Database(paths)).find_rendered_transcript(
        second.transcript_id or 0
    )
    assert rendered is not None
    assert rendered.path == output
    assert f"transcript_id: {second.transcript_id}" in output.read_text(
        encoding="utf-8"
    )
