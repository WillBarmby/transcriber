"""Provider-independent speaker diarization workflow."""

from tranpro.diarization.alignment import align_speakers, normalize_speaker_turns
from tranpro.diarization.models import (
    DiarizationDescriptor,
    DiarizationError,
    DiarizationOutput,
    DiarizationProvider,
)
from tranpro.diarization.service import DiarizationOutcome, DiarizationService

__all__ = [
    "DiarizationDescriptor",
    "DiarizationError",
    "DiarizationOutcome",
    "DiarizationOutput",
    "DiarizationProvider",
    "DiarizationService",
    "align_speakers",
    "normalize_speaker_turns",
]
