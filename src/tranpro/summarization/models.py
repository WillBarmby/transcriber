"""Domain values shared by summary workflows and provider adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from tranpro.library.models import Segment, SummarySection


@dataclass(frozen=True, slots=True)
class ContextWindow:
    """The provider's usable context and space reserved for its response."""

    max_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int = 512

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if self.reserved_output_tokens < 1:
            raise ValueError("reserved_output_tokens must be positive")
        if self.safety_margin_tokens < 0:
            raise ValueError("safety_margin_tokens cannot be negative")
        if self.input_limit < 1:
            raise ValueError("context window leaves no room for input")

    @property
    def input_limit(self) -> int:
        return self.max_tokens - self.reserved_output_tokens - self.safety_margin_tokens


@dataclass(frozen=True, slots=True)
class PlannedSection:
    index: int
    segment_refs: tuple[str, ...]
    estimated_input_tokens: int


@dataclass(frozen=True, slots=True)
class ContextPlan:
    mode: Literal["whole", "hierarchical"]
    context_window: ContextWindow
    overhead_tokens: int
    transcript_tokens: int
    sections: tuple[PlannedSection, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable audit record."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class SummaryRequest:
    system_contract: str
    instructions: str
    segments: tuple[Segment, ...]


@dataclass(frozen=True, slots=True)
class SummaryResult:
    sections: tuple[SummarySection, ...]
    raw_text: str
    usage: dict[str, int | float]
