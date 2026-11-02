"""One-shot transcription orchestration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from send2trash import send2trash

from tranpro.library.fingerprint import fingerprint_file
from tranpro.library.repository import LibraryRepository
from tranpro.transcription.models import (
    TranscriptionError,
    TranscriptionEventSink,
    TranscriptionOutcome,
    TranscriptionProvider,
    TranscriptionRequest,
    TranscriptReplayStarted,
    TranscriptSegmentFinalized,
)
from tranpro.transcription.probe import probe_duration_ms
from tranpro.transcription.render import content_hash, render_markdown, write_markdown


class TranscriptionService:
    """Coordinate deduplication, providers, persistence, output, and Trash."""

    def __init__(
        self,
        *,
        provider: TranscriptionProvider,
        repository: LibraryRepository,
        duration_probe: Callable[[Path], int | None] = probe_duration_ms,
        trash: Callable[[str], None] = send2trash,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.duration_probe = duration_probe
        self._trash = trash

    def run(
        self,
        request: TranscriptionRequest,
        *,
        emit: TranscriptionEventSink | None = None,
    ) -> TranscriptionOutcome:
        source = request.source.expanduser().resolve()
        if not source.is_file():
            raise TranscriptionError(f"Source audio not found: {source}")
        if request.output_to_stdout and request.output is not None:
            raise TranscriptionError("stdout output cannot also have a file path")

        descriptor = self.provider.descriptor
        try:
            fingerprint = fingerprint_file(source) if request.save else None
        except OSError as error:
            raise TranscriptionError(
                f"Could not fingerprint source: {error}"
            ) from error
        recording = (
            self.repository.find_recording_by_fingerprint(fingerprint)
            if fingerprint is not None
            else None
        )
        reusable = None
        if recording is not None and not request.retranscribe:
            reusable = self.repository.find_reusable_transcript(
                recording.id,
                provider=descriptor.name,
                model=descriptor.model,
                settings=descriptor.settings,
            )

        if reusable is not None:
            assert recording is not None
            segments = tuple(self.repository.get_segments(reusable.id))
            if emit is not None:
                emit(TranscriptReplayStarted(reusable.id))
                for segment in segments:
                    emit(TranscriptSegmentFinalized(segment))
            duration_ms = recording.duration_ms
            language = reusable.language
            recording, _ = self.repository.register_recording(
                source,
                fingerprint=fingerprint,
                duration_ms=duration_ms,
                language=language,
            )
            transcript_id = reusable.id
            reused = True
        else:
            result = self.provider.transcribe(source, emit=emit)
            segments = result.segments
            duration_ms = self.duration_probe(source) or result.duration_ms
            language = result.language
            transcript_id = None
            reused = False
            if request.save:
                assert fingerprint is not None
                recording, _ = self.repository.register_recording(
                    source,
                    fingerprint=fingerprint,
                    duration_ms=duration_ms,
                    language=language,
                )
                transcript = self.repository.add_transcript(
                    recording.id,
                    provider=descriptor.name,
                    model=descriptor.model,
                    settings=descriptor.settings,
                    language=language,
                    segments=segments,
                )
                transcript_id = transcript.id

        recording_id = None if recording is None else recording.id
        markdown = render_markdown(
            source=source,
            segments=segments,
            provider=descriptor.name,
            model=descriptor.model,
            recording_id=recording_id,
            transcript_id=transcript_id,
        )
        output_path = None
        if not request.output_to_stdout:
            output_path = write_markdown(
                markdown,
                source=source,
                requested_path=request.output,
                force=request.force,
            )
            if recording_id is not None and transcript_id is not None:
                self.repository.record_rendered_output(
                    recording_id=recording_id,
                    transcript_id=transcript_id,
                    summary_id=None,
                    kind="transcript",
                    format="markdown",
                    path=output_path,
                    content_hash=content_hash(markdown),
                    replace=request.force,
                )

        return TranscriptionOutcome(
            source=source,
            markdown=markdown,
            output_path=output_path,
            recording_id=recording_id,
            transcript_id=transcript_id,
            provider=descriptor.name,
            model=descriptor.model,
            reused=reused,
            trash_source=request.trash_source,
        )

    def finalize_trash(self, outcome: TranscriptionOutcome) -> None:
        """Move the source to OS Trash only after the caller emits all output."""

        if not outcome.trash_source:
            return
        try:
            self._trash(str(outcome.source))
        except Exception as error:
            raise TranscriptionError(
                f"Transcript succeeded, but source could not be moved to Trash: {error}"
            ) from error
        if outcome.recording_id is not None:
            self.repository.mark_source_trashed(
                outcome.recording_id, original_path=outcome.source
            )
