"""Speaker diarization orchestration and immutable persistence."""

from __future__ import annotations

from dataclasses import dataclass

from tranpro.diarization.alignment import align_speakers, normalize_speaker_turns
from tranpro.diarization.models import DiarizationError, DiarizationProvider
from tranpro.library.models import Segment
from tranpro.library.repository import LibraryRepository


@dataclass(frozen=True, slots=True)
class DiarizationOutcome:
    recording_id: int
    transcript_id: int
    diarization_id: int
    provider: str
    model: str
    turns: int
    speakers: int
    segments: tuple[Segment, ...]
    reused: bool


class DiarizationService:
    """Run a provider once and project its timeline onto a transcript."""

    def __init__(
        self,
        *,
        provider: DiarizationProvider,
        repository: LibraryRepository,
        dominance_threshold: float = 0.6,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.dominance_threshold = dominance_threshold

    def run(
        self,
        recording_id: int,
        *,
        transcript_id: int | None = None,
        rediarize: bool = False,
    ) -> DiarizationOutcome:
        recording = self.repository.get_recording(recording_id, include_deleted=False)
        transcript = (
            self.repository.get_preferred_transcript(recording_id)
            if transcript_id is None
            else self.repository.get_transcript(transcript_id)
        )
        if transcript.recording_id != recording_id:
            raise DiarizationError(
                f"Transcript {transcript.id} does not belong to recording "
                f"{recording_id}"
            )
        source = recording.current_path
        if source is None or not source.is_file():
            raise DiarizationError(
                f"Recording {recording_id} has no available source audio"
            )

        descriptor = self.provider.descriptor
        reusable = None
        if not rediarize:
            reusable = self.repository.find_reusable_diarization(
                recording_id,
                provider=descriptor.name,
                model=descriptor.model,
                settings=descriptor.settings,
            )

        transcript_segments = self.repository.get_segments(transcript.id)
        if reusable is not None:
            assignments = self.repository.get_speaker_assignments(
                reusable.id, transcript.id
            )
            if len(assignments) != len(transcript_segments):
                turns = self.repository.get_speaker_turns(reusable.id)
                assignments = list(
                    align_speakers(
                        transcript_segments,
                        turns,
                        dominance_threshold=self.dominance_threshold,
                    )
                )
                self.repository.add_diarization_assignments(
                    reusable.id, transcript.id, assignments
                )
            segments = tuple(
                self.repository.get_diarized_segments(reusable.id, transcript.id)
            )
            reused_turns = self.repository.get_speaker_turns(reusable.id)
            return DiarizationOutcome(
                recording_id=recording_id,
                transcript_id=transcript.id,
                diarization_id=reusable.id,
                provider=reusable.provider,
                model=reusable.model,
                turns=len(reused_turns),
                speakers=len({turn.speaker for turn in reused_turns}),
                segments=segments,
                reused=True,
            )

        run = self.repository.begin_diarization(
            recording_id,
            provider=descriptor.name,
            model=descriptor.model,
            settings=descriptor.settings,
        )
        try:
            output = self.provider.diarize(source)
            normalized_turns = normalize_speaker_turns(output.turns)
            aligned_assignments = align_speakers(
                transcript_segments,
                normalized_turns,
                dominance_threshold=self.dominance_threshold,
            )
            completed = self.repository.complete_diarization(
                run.id,
                transcript_id=transcript.id,
                turns=normalized_turns,
                assignments=aligned_assignments,
            )
        except Exception as error:
            self.repository.fail_diarization(run.id, str(error))
            if isinstance(error, DiarizationError):
                raise
            raise DiarizationError(f"Diarization failed: {error}") from error

        segments = tuple(
            self.repository.get_diarized_segments(completed.id, transcript.id)
        )
        return DiarizationOutcome(
            recording_id=recording_id,
            transcript_id=transcript.id,
            diarization_id=completed.id,
            provider=completed.provider,
            model=completed.model,
            turns=len(normalized_turns),
            speakers=len({turn.speaker for turn in normalized_turns}),
            segments=segments,
            reused=False,
        )
