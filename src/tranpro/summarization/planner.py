"""Deterministic context-window feasibility planning."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from tranpro.library.models import Segment
from tranpro.summarization.models import ContextPlan, ContextWindow, PlannedSection


class ContextPlanningError(ValueError):
    """Raised when even one transcript segment cannot fit in the model context."""


def render_segments(segments: Sequence[Segment]) -> str:
    """Render stable references with text for token counting and model input."""

    return "\n".join(
        f"[{segment.stable_ref}] "
        f"{f'{segment.speaker}: ' if segment.speaker else ''}{segment.text}"
        for segment in segments
    )


def plan_context(
    *,
    system_contract: str,
    instructions: str,
    segments: Sequence[Segment],
    window: ContextWindow,
    count_tokens: Callable[[str], int],
) -> ContextPlan:
    """Prefer one pass, otherwise split at transcript segment boundaries."""

    overhead_text = f"{system_contract}\n\n{instructions}\n\nTranscript:\n"
    overhead_tokens = count_tokens(overhead_text)
    if overhead_tokens >= window.input_limit:
        raise ContextPlanningError(
            "summary instructions consume the provider's entire input budget"
        )

    transcript_tokens = count_tokens(render_segments(segments))
    whole_tokens = count_tokens(overhead_text + render_segments(segments))
    all_refs = tuple(segment.stable_ref for segment in segments)
    if whole_tokens <= window.input_limit:
        return ContextPlan(
            mode="whole",
            context_window=window,
            overhead_tokens=overhead_tokens,
            transcript_tokens=transcript_tokens,
            sections=(PlannedSection(0, all_refs, whole_tokens),),
        )

    planned: list[PlannedSection] = []
    current: list[Segment] = []
    current_tokens = overhead_tokens
    for segment in segments:
        candidate = [*current, segment]
        candidate_tokens = count_tokens(overhead_text + render_segments(candidate))
        if candidate_tokens <= window.input_limit:
            current = candidate
            current_tokens = candidate_tokens
            continue
        if not current:
            raise ContextPlanningError(
                f"transcript segment {segment.stable_ref} cannot fit in the provider "
                "context window; split the segment before summarizing"
            )
        planned.append(
            PlannedSection(
                len(planned),
                tuple(item.stable_ref for item in current),
                current_tokens,
            )
        )
        current = [segment]
        current_tokens = count_tokens(overhead_text + render_segments(current))
        if current_tokens > window.input_limit:
            raise ContextPlanningError(
                f"transcript segment {segment.stable_ref} cannot fit in the provider "
                "context window; split the segment before summarizing"
            )

    if current or not planned:
        planned.append(
            PlannedSection(
                len(planned),
                tuple(item.stable_ref for item in current),
                current_tokens,
            )
        )
    return ContextPlan(
        mode="hierarchical",
        context_window=window,
        overhead_tokens=overhead_tokens,
        transcript_tokens=transcript_tokens,
        sections=tuple(planned),
    )
