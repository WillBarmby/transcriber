"""Normalized transcription provider and workflow types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeAlias

from tranpro.library.models import Segment


class TranscriptionError(RuntimeError):
    """Raised when audio cannot be transcribed or normalized."""


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    name: str
    model: str
    settings: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TranscriptionOutput:
    segments: tuple[Segment, ...]
    language: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionProgress:
    """Progress through the provider's source audio."""

    completed_ms: int
    total_ms: int


@dataclass(frozen=True, slots=True)
class TranscriptSegmentFinalized:
    """A segment whose displayed text will no longer be revised."""

    segment: Segment


@dataclass(frozen=True, slots=True)
class TranscriptReplayStarted:
    """Signals that events are replaying an existing stored transcript."""

    transcript_id: int


TranscriptionEvent: TypeAlias = (
    TranscriptionProgress | TranscriptSegmentFinalized | TranscriptReplayStarted
)
TranscriptionEventSink: TypeAlias = Callable[[TranscriptionEvent], None]


class TranscriptionProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput: ...


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    source: Path
    output: Path | None = None
    output_to_stdout: bool = False
    save: bool = True
    retranscribe: bool = False
    force: bool = False
    trash_source: bool = False


@dataclass(frozen=True, slots=True)
class TranscriptionOutcome:
    source: Path
    markdown: str
    output_path: Path | None
    recording_id: int | None
    transcript_id: int | None
    provider: str
    model: str
    reused: bool
    trash_source: bool
