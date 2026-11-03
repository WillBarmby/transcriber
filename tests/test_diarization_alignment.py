import pytest

from tranpro.diarization.alignment import align_speakers, normalize_speaker_turns
from tranpro.library.models import Segment, SpeakerTurn


def raw_turn(index: int, start_ms: int, end_ms: int, speaker: str) -> SpeakerTurn:
    return SpeakerTurn(index, start_ms, end_ms, speaker, speaker)


def test_speakers_are_normalized_by_first_arrival() -> None:
    turns = normalize_speaker_turns(
        [
            raw_turn(4, 2_000, 3_000, "channel-b"),
            raw_turn(2, 0, 1_000, "channel-a"),
            raw_turn(3, 1_000, 2_000, "channel-b"),
        ]
    )

    assert [(turn.index, turn.speaker, turn.source_speaker) for turn in turns] == [
        (0, "Speaker 1", "channel-a"),
        (1, "Speaker 2", "channel-b"),
        (2, "Speaker 2", "channel-b"),
    ]


def test_alignment_uses_overlap_and_marks_uncertain_sentences_mixed() -> None:
    segments = [
        Segment(0, 0, 1_000, "One speaker."),
        Segment(1, 1_000, 2_000, "A handoff."),
        Segment(2, 2_000, 3_000, "No detected speech."),
    ]
    turns = [
        SpeakerTurn(0, 0, 1_500, "Speaker 1", "a"),
        SpeakerTurn(1, 1_500, 2_000, "Speaker 2", "b"),
    ]

    assignments = align_speakers(segments, turns)

    assert assignments[0].speaker == "Speaker 1"
    assert assignments[0].status == "assigned"
    assert assignments[1].speaker == "Mixed"
    assert assignments[1].status == "mixed"
    assert assignments[1].confidence == pytest.approx(0.5)
    assert assignments[2].speaker is None
    assert assignments[2].status == "unassigned"


def test_alignment_counts_overlapping_speech_without_inventing_word_boundaries() -> (
    None
):
    assignment = align_speakers(
        [Segment(0, 0, 1_000, "Both people speak.")],
        [
            SpeakerTurn(0, 0, 1_000, "Speaker 1", "a"),
            SpeakerTurn(1, 200, 800, "Speaker 2", "b"),
        ],
    )[0]

    assert assignment.speaker == "Speaker 1"
    assert assignment.overlap_ms == 1_000
    assert assignment.confidence == pytest.approx(0.625)


def test_alignment_rejects_an_unsafe_dominance_threshold() -> None:
    with pytest.raises(ValueError, match="greater than 0.5"):
        align_speakers([], [], dominance_threshold=0.5)
