import pytest

from tranpro.library.models import Segment
from tranpro.summarization.models import ContextWindow
from tranpro.summarization.planner import (
    ContextPlanningError,
    plan_context,
    render_segments,
)


def words(text: str) -> int:
    return len(text.split())


def test_whole_transcript_is_preferred_when_it_fits() -> None:
    plan = plan_context(
        system_contract="Be accurate.",
        instructions="Write notes.",
        segments=[
            Segment(0, 0, 1_000, "First idea"),
            Segment(1, 1_000, 2_000, "Second idea"),
        ],
        window=ContextWindow(100, reserved_output_tokens=10, safety_margin_tokens=5),
        count_tokens=words,
    )

    assert plan.mode == "whole"
    assert plan.sections[0].segment_refs == ("s000001", "s000002")
    assert plan.sections[0].estimated_input_tokens <= plan.context_window.input_limit


def test_rendered_summary_input_includes_available_speaker_labels() -> None:
    rendered = render_segments(
        [
            Segment(0, 0, 1_000, "Welcome.", "Speaker 1"),
            Segment(1, 1_000, 2_000, "Thanks."),
        ]
    )

    assert rendered == "[s000001] Speaker 1: Welcome.\n[s000002] Thanks."


def test_long_transcript_splits_only_at_segment_boundaries() -> None:
    plan = plan_context(
        system_contract="Accurate.",
        instructions="Detailed notes.",
        segments=[
            Segment(0, 0, 1_000, "one two three four"),
            Segment(1, 1_000, 2_000, "five six seven eight"),
            Segment(2, 2_000, 3_000, "nine ten eleven twelve"),
        ],
        window=ContextWindow(15, reserved_output_tokens=2, safety_margin_tokens=1),
        count_tokens=words,
    )

    assert plan.mode == "hierarchical"
    assert [section.segment_refs for section in plan.sections] == [
        ("s000001",),
        ("s000002",),
        ("s000003",),
    ]
    assert plan.to_dict()["mode"] == "hierarchical"


def test_single_oversized_segment_reports_its_stable_reference() -> None:
    with pytest.raises(ContextPlanningError, match="s000001"):
        plan_context(
            system_contract="Accurate.",
            instructions="Notes.",
            segments=[Segment(0, 0, 1_000, " ".join(["word"] * 30))],
            window=ContextWindow(20, reserved_output_tokens=2, safety_margin_tokens=1),
            count_tokens=words,
        )
