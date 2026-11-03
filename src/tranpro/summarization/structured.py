"""Shared structured-summary schema, prompting, and validation."""

from __future__ import annotations

import json
from typing import Any, cast

from tranpro.library.models import SummarySection
from tranpro.summarization.models import SummaryRequest
from tranpro.summarization.planner import render_segments

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                    "segment_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": ["heading", "body", "segment_refs"],
                "additionalProperties": False,
            },
            "minItems": 1,
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}


def render_summary_request(request: SummaryRequest) -> str:
    if request.source_notes:
        source = "\n\n".join(
            f"Partial notes {index + 1}:\n{notes}"
            for index, notes in enumerate(request.source_notes)
        )
        source_label = "Partial notes to synthesize"
    else:
        source = render_segments(request.segments)
        source_label = "Transcript"
    return (
        f"{request.instructions}\n\n"
        "Return valid JSON matching the supplied schema. Preserve only segment "
        "references that appear in the input.\n\n"
        f"{source_label}:\n{source}"
    )


def parse_summary_text(raw_text: str) -> tuple[SummarySection, ...]:
    parsed = cast(dict[str, Any], json.loads(raw_text))
    raw_sections = cast(list[dict[str, Any]], parsed["sections"])
    sections = tuple(
        SummarySection(
            heading=str(section["heading"]).strip(),
            body=str(section["body"]).strip(),
            segment_refs=tuple(
                str(ref) for ref in cast(list[Any], section["segment_refs"])
            ),
        )
        for section in raw_sections
    )
    if not sections or any(not item.heading or not item.body for item in sections):
        raise ValueError("provider returned an empty summary section")
    if any(not item.segment_refs for item in sections):
        raise ValueError("provider returned an ungrounded summary section")
    return sections
