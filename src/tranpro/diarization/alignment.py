"""Deterministic projection of speaker timelines onto transcript segments."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from tranpro.library.models import Segment, SpeakerAssignment, SpeakerTurn

MIXED_SPEAKER = "Mixed"


def normalize_speaker_turns(turns: Iterable[SpeakerTurn]) -> tuple[SpeakerTurn, ...]:
    """Assign stable generic labels in first-arrival order."""

    ordered = sorted(turns, key=lambda turn: (turn.start_ms, turn.end_ms, turn.index))
    labels: dict[str, str] = {}
    normalized: list[SpeakerTurn] = []
    for index, turn in enumerate(ordered):
        _validate_turn(turn)
        label = labels.setdefault(
            turn.source_speaker,
            f"Speaker {len(labels) + 1}",
        )
        normalized.append(
            SpeakerTurn(
                index=index,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                speaker=label,
                source_speaker=turn.source_speaker,
                confidence=turn.confidence,
            )
        )
    return tuple(normalized)


def align_speakers(
    segments: Iterable[Segment],
    turns: Iterable[SpeakerTurn],
    *,
    dominance_threshold: float = 0.6,
) -> tuple[SpeakerAssignment, ...]:
    """Choose the maximum-overlap speaker for each sentence-level segment.

    A segment is marked mixed when its leading speaker does not account for the
    requested share of all speaker overlap. This intentionally avoids inventing
    word boundaries that the transcript provider did not supply.
    """

    if not 0.5 < dominance_threshold <= 1:
        raise ValueError("dominance threshold must be greater than 0.5 and at most 1")
    materialized_turns = tuple(turns)
    for turn in materialized_turns:
        _validate_turn(turn)

    assignments: list[SpeakerAssignment] = []
    for expected_index, segment in enumerate(segments):
        if segment.index != expected_index:
            raise ValueError("segment indexes must be contiguous and start at zero")
        overlaps: dict[str, int] = defaultdict(int)
        for turn in materialized_turns:
            overlap = min(segment.end_ms, turn.end_ms) - max(
                segment.start_ms, turn.start_ms
            )
            if overlap > 0:
                overlaps[turn.speaker] += overlap

        if not overlaps:
            assignments.append(
                SpeakerAssignment(
                    segment_index=segment.index,
                    stable_ref=segment.stable_ref,
                    speaker=None,
                    overlap_ms=0,
                    confidence=0.0,
                    status="unassigned",
                )
            )
            continue

        speaker, winning_overlap = min(
            overlaps.items(), key=lambda item: (-item[1], item[0])
        )
        total_overlap = sum(overlaps.values())
        confidence = winning_overlap / total_overlap
        mixed = confidence < dominance_threshold
        assignments.append(
            SpeakerAssignment(
                segment_index=segment.index,
                stable_ref=segment.stable_ref,
                speaker=MIXED_SPEAKER if mixed else speaker,
                overlap_ms=winning_overlap,
                confidence=confidence,
                status="mixed" if mixed else "assigned",
            )
        )
    return tuple(assignments)


def _validate_turn(turn: SpeakerTurn) -> None:
    if turn.start_ms < 0 or turn.end_ms < turn.start_ms:
        raise ValueError(f"invalid timestamps for speaker turn {turn.index}")
    if not turn.source_speaker.strip():
        raise ValueError(f"speaker turn {turn.index} has no source speaker")
    if turn.confidence is not None and not 0 <= turn.confidence <= 1:
        raise ValueError(f"invalid confidence for speaker turn {turn.index}")
