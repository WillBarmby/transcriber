"""Transform canonical transcript artifacts into styled document blocks."""

from __future__ import annotations

from pathlib import Path

from tranpro.library.models import Segment, SummarySection
from tranpro.publication.models import DocumentBlock, DocumentContent
from tranpro.transcription.render import format_timestamp


def render_document(
    *,
    source: Path,
    segments: tuple[Segment, ...],
    summary_sections: tuple[SummarySection, ...] = (),
) -> DocumentContent:
    title = source.stem
    blocks = [
        DocumentBlock(title, "TITLE"),
        DocumentBlock("Created by tranpro", "SUBTITLE"),
    ]
    if summary_sections:
        blocks.append(DocumentBlock("Summary", "HEADING_1"))
        for section in summary_sections:
            blocks.append(DocumentBlock(section.heading, "HEADING_2"))
            blocks.append(DocumentBlock(section.body))
            evidence = ", ".join(
                _evidence(ref, segments) for ref in section.segment_refs
            )
            if evidence:
                blocks.append(DocumentBlock(f"Transcript evidence: {evidence}"))
    blocks.append(DocumentBlock("Transcript", "HEADING_1"))
    if not segments:
        blocks.append(DocumentBlock("No speech detected."))
    for segment in segments:
        prefix = f"[{format_timestamp(segment.start_ms)}]"
        if segment.speaker:
            prefix += f" {segment.speaker}:"
        blocks.append(DocumentBlock(f"{prefix} {segment.text}"))
    return DocumentContent(title=title, blocks=tuple(blocks))


def google_batch_requests(
    content: DocumentContent, *, delete_end_index: int | None = None
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    if delete_end_index is not None and delete_end_index > 1:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {"startIndex": 1, "endIndex": delete_end_index}
                }
            }
        )
    requests.append(
        {"insertText": {"location": {"index": 1}, "text": content.plain_text}}
    )
    start = 1
    for block in content.blocks:
        text = f"{block.text.rstrip()}\n"
        end = start + _google_index_length(text)
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "paragraphStyle": {"namedStyleType": block.named_style},
                    "fields": "namedStyleType",
                }
            }
        )
        start = end
    return requests


def _google_index_length(text: str) -> int:
    """Return the UTF-16 code-unit length used by Google Docs indices."""

    return len(text.encode("utf-16-le")) // 2


def _evidence(ref: str, segments: tuple[Segment, ...]) -> str:
    by_ref = {segment.stable_ref: segment for segment in segments}
    segment = by_ref[ref]
    return f"{format_timestamp(segment.start_ms)} ({ref})"
