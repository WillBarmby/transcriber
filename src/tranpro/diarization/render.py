"""Markdown projection for speaker-labelled transcripts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tranpro.diarization.models import DiarizationError
from tranpro.library.models import Segment
from tranpro.transcription.render import format_timestamp


def render_diarized_markdown(
    *,
    source: Path,
    segments: tuple[Segment, ...],
    provider: str,
    model: str,
    recording_id: int,
    transcript_id: int,
    diarization_id: int,
) -> str:
    metadata: dict[str, object] = {
        "source": str(source),
        "provider": provider,
        "model": model,
        "recording_id": recording_id,
        "transcript_id": transcript_id,
        "diarization_id": diarization_id,
    }
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(["---", "", f"# Diarized Transcript: {source.stem}", ""])
    if not segments:
        lines.extend(["_No speech detected._", ""])
    for segment in segments:
        speaker = f" **{segment.speaker}:**" if segment.speaker else ""
        lines.append(f"[{format_timestamp(segment.start_ms)}]{speaker} {segment.text}")
    return "\n".join(lines).rstrip() + "\n"


def write_diarized_markdown(
    content: str,
    *,
    source: Path,
    requested_path: Path | None = None,
    force: bool = False,
) -> Path:
    explicit = requested_path is not None
    destination = (
        (requested_path or source.with_name(f"{source.stem}.diarized.md"))
        .expanduser()
        .resolve()
    )
    if destination == source.resolve():
        raise DiarizationError("Diarized output cannot replace the source audio")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if existing == content:
            return destination
        if explicit and not force:
            raise DiarizationError(
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
        raise DiarizationError(
            f"Could not write diarized transcript: {error}"
        ) from error
    return destination


def _available_version(path: Path) -> Path:
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}.{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1
