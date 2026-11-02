"""Readable Markdown rendering with collision-safe file output."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from tranpro.library.models import Segment
from tranpro.transcription.models import TranscriptionError


def render_markdown(
    *,
    source: Path,
    segments: tuple[Segment, ...],
    provider: str,
    model: str,
    recording_id: int | None,
    transcript_id: int | None,
) -> str:
    metadata = {
        "source": str(source),
        "provider": provider,
        "model": model,
        "recording_id": recording_id,
        "transcript_id": transcript_id,
    }
    lines = ["---"]
    for key, value in metadata.items():
        rendered = "null" if value is None else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {rendered}")
    lines.extend(["---", "", f"# Transcript: {source.stem}", ""])
    if not segments:
        lines.append("_No speech detected._")
    for segment in segments:
        speaker = f" **{segment.speaker}:**" if segment.speaker else ""
        lines.append(f"[{format_timestamp(segment.start_ms)}]{speaker} {segment.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def content_hash(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def default_output_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}.transcript.md")


def write_markdown(
    content: str,
    *,
    source: Path,
    requested_path: Path | None,
    force: bool,
) -> Path:
    explicit = requested_path is not None
    destination = (requested_path or default_output_path(source)).expanduser().resolve()
    if destination == source.resolve():
        raise TranscriptionError("Transcript output cannot replace the source audio")
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        try:
            existing = destination.read_text(encoding="utf-8")
        except OSError as error:
            raise TranscriptionError(
                f"Could not read existing output: {error}"
            ) from error
        if existing == content:
            return destination
        if explicit and not force:
            raise TranscriptionError(
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
        raise TranscriptionError(f"Could not write transcript: {error}") from error
    return destination


def _available_version(path: Path) -> Path:
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}.{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def format_timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
