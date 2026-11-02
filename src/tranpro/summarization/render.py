"""Grounded Markdown rendering for summaries."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tranpro.library.models import Segment, SummarySection
from tranpro.summarization.ollama import SummarizationError
from tranpro.transcription.render import format_timestamp


def render_summary_markdown(
    *,
    source: Path,
    sections: tuple[SummarySection, ...],
    segments: tuple[Segment, ...],
    provider: str,
    model: str,
    prompt_name: str,
    prompt_version: int,
    recording_id: int,
    transcript_id: int,
    summary_id: int,
) -> str:
    metadata: dict[str, object] = {
        "source": str(source),
        "provider": provider,
        "model": model,
        "prompt": f"{prompt_name}@{prompt_version}",
        "recording_id": recording_id,
        "transcript_id": transcript_id,
        "summary_id": summary_id,
    }
    timestamps = {
        segment.stable_ref: format_timestamp(segment.start_ms) for segment in segments
    }
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(["---", "", f"# Summary: {source.stem}", ""])
    for section in sections:
        lines.extend([f"## {section.heading}", "", section.body, ""])
        if section.segment_refs:
            evidence = ", ".join(
                f"{timestamps[ref]} ({ref})" for ref in section.segment_refs
            )
            lines.extend([f"_Transcript evidence: {evidence}_", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_summary_markdown(
    content: str,
    *,
    source: Path,
    requested_path: Path | None,
    force: bool,
) -> Path:
    explicit = requested_path is not None
    destination = (
        (requested_path or source.with_name(f"{source.stem}.summary.md"))
        .expanduser()
        .resolve()
    )
    if destination == source.resolve():
        raise SummarizationError("Summary output cannot replace the source audio")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if existing == content:
            return destination
        if explicit and not force:
            raise SummarizationError(
                f"Output already exists: {destination}; pass --force to replace it"
            )
        if not explicit:
            destination = _available_version(destination)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise SummarizationError(f"Could not write summary: {error}") from error
    return destination


def _available_version(path: Path) -> Path:
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}.{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1
