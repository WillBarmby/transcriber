"""Provider-independent transcript library records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Recording:
    id: int
    fingerprint: str
    original_path: Path
    current_path: Path | None
    file_size_bytes: int
    duration_ms: int | None
    language: str | None
    created_at: str
    deleted_at: str | None


@dataclass(frozen=True, slots=True)
class Segment:
    index: int
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None

    @property
    def stable_ref(self) -> str:
        return f"s{self.index + 1:06d}"


@dataclass(frozen=True, slots=True)
class TranscriptRun:
    id: int
    recording_id: int
    provider: str
    model: str
    status: str
    language: str | None
    is_preferred: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class SummarySection:
    heading: str
    body: str
    segment_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SummaryRun:
    id: int
    transcript_id: int
    prompt_name: str
    prompt_version: int
    provider: str
    model: str
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    kind: str
    recording_id: int
    artifact_id: int
    location: str
    title: str
    snippet: str
    rank: float
    recording_path: Path
    start_ms: int | None


@dataclass(frozen=True, slots=True)
class LibraryStats:
    recordings: int
    deleted_recordings: int
    transcripts: int
    summaries: int
