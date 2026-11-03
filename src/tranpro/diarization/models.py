"""Normalized diarization provider and workflow types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tranpro.library.models import SpeakerTurn


class DiarizationError(RuntimeError):
    """Raised when speakers cannot be diarized or aligned."""


@dataclass(frozen=True, slots=True)
class DiarizationDescriptor:
    name: str
    model: str
    settings: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DiarizationOutput:
    turns: tuple[SpeakerTurn, ...]


class DiarizationProvider(Protocol):
    @property
    def descriptor(self) -> DiarizationDescriptor: ...

    def diarize(self, source: Path) -> DiarizationOutput: ...
