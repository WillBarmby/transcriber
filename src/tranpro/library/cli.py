"""Terminal presentation for the transcript library."""

from __future__ import annotations

from pathlib import Path
from typing import Never

import typer

from tranpro.library.database import Database, DatabaseError
from tranpro.library.models import Recording
from tranpro.library.repository import (
    LibraryError,
    LibraryRepository,
    RecordNotFoundError,
)
from tranpro.paths import AppPaths

library_app = typer.Typer(
    help="Manage the local transcript library.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@library_app.callback()
def library_root(context: typer.Context) -> None:
    """Manage the local transcript library."""

    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


def _repository() -> LibraryRepository:
    return LibraryRepository(Database(AppPaths.for_user()))


@library_app.command("init")
def initialize_library() -> None:
    """Create or safely migrate the transcript database."""

    database = Database(AppPaths.for_user())
    try:
        version = database.initialize()
    except DatabaseError as error:
        _fail(str(error))
    typer.echo(f"Library schema {version} ready: {database.paths.database_file}")


@library_app.command("status")
def library_status() -> None:
    """Show the database location, schema, and artifact counts."""

    repository = _repository()
    try:
        version = repository.database.initialize()
        stats = repository.stats()
    except (DatabaseError, LibraryError) as error:
        _fail(str(error))
    typer.echo(f"Database     {repository.database.paths.database_file}")
    typer.echo(f"Schema       {version}")
    typer.echo(f"Recordings   {stats.recordings}")
    typer.echo(f"Deleted      {stats.deleted_recordings}")
    typer.echo(f"Transcripts  {stats.transcripts}")
    typer.echo(f"Summaries    {stats.summaries}")


@library_app.command("reveal")
def reveal_library() -> None:
    """Reveal tranpro's application-data directory."""

    paths = AppPaths.for_user()
    paths.create_private_directories()
    typer.launch(str(paths.data_dir))


def list_recordings(
    include_deleted: bool = typer.Option(
        False, "--all", help="Include forgotten recordings."
    ),
    limit: int = typer.Option(100, min=1, help="Maximum recordings to show."),
) -> None:
    """List recordings in the local library."""

    try:
        recordings = _repository().list_recordings(
            include_deleted=include_deleted, limit=limit
        )
    except (DatabaseError, LibraryError) as error:
        _fail(str(error))
    if not recordings:
        typer.echo("No recordings in the library yet.")
        return

    typer.echo(f"{'ID':>4}  {'State':<7}  {'Duration':>8}  Recording")
    for recording in recordings:
        state = "deleted" if recording.deleted_at else "active"
        name = _display_path(recording).name
        typer.echo(
            f"{recording.id:>4}  {state:<7}  "
            f"{_format_duration(recording.duration_ms):>8}  {name}"
        )


def show_recording(recording_id: int) -> None:
    """Show recording metadata and all artifact versions."""

    repository = _repository()
    try:
        recording = repository.get_recording(recording_id)
        transcripts = repository.list_transcripts(recording_id)
        summaries = repository.list_summaries(recording_id)
    except (DatabaseError, LibraryError, RecordNotFoundError) as error:
        _fail(str(error))

    path = _display_path(recording)
    typer.echo(f"Recording {recording.id}: {path.name}")
    typer.echo(f"State        {'forgotten' if recording.deleted_at else 'active'}")
    typer.echo(f"Source       {path}")
    typer.echo(f"Source exists {'yes' if path.exists() else 'no'}")
    typer.echo(f"Fingerprint  {recording.fingerprint}")
    typer.echo(f"Size         {recording.file_size_bytes} bytes")
    typer.echo(f"Duration     {_format_duration(recording.duration_ms)}")
    typer.echo(f"Language     {recording.language or 'unknown'}")
    typer.echo(f"Created      {recording.created_at}")

    typer.echo("\nTranscripts")
    if not transcripts:
        typer.echo("  none")
    for transcript in transcripts:
        preferred = " preferred" if transcript.is_preferred else ""
        typer.echo(
            f"  #{transcript.id} {transcript.provider}/{transcript.model} "
            f"{transcript.status}{preferred}"
        )

    typer.echo("\nSummaries")
    if not summaries:
        typer.echo("  none")
    for summary in summaries:
        typer.echo(
            f"  #{summary.id} transcript #{summary.transcript_id} "
            f"{summary.provider}/{summary.model} {summary.status} "
            f"prompt={summary.prompt_name}@{summary.prompt_version}"
        )


def search_library(
    query: str,
    kind: str | None = typer.Option(
        None, "--kind", help="Limit to transcript or summary results."
    ),
    include_deleted: bool = typer.Option(
        False, "--all", help="Include forgotten recordings."
    ),
    limit: int = typer.Option(20, min=1, help="Maximum matches to show."),
) -> None:
    """Search transcript segments and summary sections."""

    try:
        hits = _repository().search(
            query,
            kind=kind,
            include_deleted=include_deleted,
            limit=limit,
        )
    except (DatabaseError, LibraryError, ValueError) as error:
        _fail(str(error))
    if not hits:
        typer.echo(f"No matches for: {query}")
        return

    for hit in hits:
        timestamp = (
            f" {_format_timestamp(hit.start_ms)}" if hit.start_ms is not None else ""
        )
        typer.echo(
            f"[{hit.recording_id}] {hit.recording_path.name} · "
            f"{hit.kind} #{hit.artifact_id}{timestamp} · {hit.location}"
        )
        if hit.title:
            typer.echo(f"    {hit.title}")
        typer.echo(f"    {hit.snippet}")


def forget_recording(recording_id: int) -> None:
    """Hide a recording without deleting source files or artifacts."""

    try:
        changed = _repository().forget(recording_id)
    except (DatabaseError, LibraryError, RecordNotFoundError) as error:
        _fail(str(error))
    if changed:
        typer.echo(f"Forgot recording {recording_id}; restore it with `tp restore`.")
    else:
        typer.echo(f"Recording {recording_id} is already forgotten.")


def restore_recording(recording_id: int) -> None:
    """Restore a forgotten recording to normal listings and search."""

    try:
        changed = _repository().restore(recording_id)
    except (DatabaseError, LibraryError, RecordNotFoundError) as error:
        _fail(str(error))
    if changed:
        typer.echo(f"Restored recording {recording_id}.")
    else:
        typer.echo(f"Recording {recording_id} is already active.")


def open_recording(recording_id: int) -> None:
    """Open a recording's current source file with the operating system."""

    try:
        recording = _repository().get_recording(recording_id)
    except (DatabaseError, LibraryError, RecordNotFoundError) as error:
        _fail(str(error))
    candidates = [recording.current_path, recording.original_path]
    path = next(
        (candidate for candidate in candidates if candidate and candidate.exists()),
        None,
    )
    if path is None:
        _fail(f"No source file for recording {recording_id} exists on disk")
    typer.launch(str(path))


def _display_path(recording: Recording) -> Path:
    return recording.current_path or recording.original_path


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "unknown"
    total_seconds = duration_ms // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _format_timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _fail(message: str) -> Never:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)
