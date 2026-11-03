"""Command-line entry point for tranpro."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from typer.core import TyperGroup

from tranpro import __version__
from tranpro.config import DEFAULT_CONFIG, Config, ConfigError, initialize_config
from tranpro.diarization.cli import diarize_recording
from tranpro.library.cli import (
    forget_recording,
    library_app,
    list_recordings,
    open_recording,
    restore_recording,
    search_library,
    show_recording,
)
from tranpro.library.database import Database, DatabaseError
from tranpro.library.repository import LibraryError, LibraryRepository
from tranpro.paths import AppPaths
from tranpro.publication.cli import google_app, publish_google_doc
from tranpro.summarization.cli import prompt_app
from tranpro.summarization.factory import build_summary_provider
from tranpro.summarization.ollama import SummarizationError
from tranpro.summarization.planner import ContextPlanningError
from tranpro.summarization.service import SummaryOutcome, SummaryService
from tranpro.transcription.factory import build_provider
from tranpro.transcription.models import (
    TranscriptionError,
    TranscriptionEvent,
    TranscriptionProgress,
    TranscriptionRequest,
    TranscriptReplayStarted,
    TranscriptSegmentFinalized,
)
from tranpro.transcription.render import format_timestamp
from tranpro.transcription.service import TranscriptionService

_AUDIO_SUFFIXES = {
    ".aac",
    ".aiff",
    ".flac",
    ".m4a",
    ".m4b",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}


class DefaultCommandGroup(TyperGroup):
    """Route path-like first arguments to the transcribe command."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if args and self._looks_like_source(args[0]):
            args.insert(0, "transcribe")
        return super().parse_args(ctx, args)

    def _looks_like_source(self, value: str) -> bool:
        if value.startswith("-") or value in self.commands:
            return False
        path = Path(value).expanduser()
        return (
            value.isdigit() or path.exists() or path.suffix.lower() in _AUDIO_SUFFIXES
        )


class TerminalProgress:
    """Render provider progress without contaminating stdout pipelines."""

    def __init__(self, *, enabled: bool, console: Console | None = None) -> None:
        self.enabled = enabled
        self._progress = Progress(
            SpinnerColumn("dots"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console or Console(stderr=True),
            transient=False,
        )
        self._task_id: TaskID | None = None
        self._total: float | None = None

    def __enter__(self) -> TerminalProgress:
        if self.enabled:
            self._progress.start()
            self._task_id = self._progress.add_task("Transcribing", total=None)
        return self

    def __exit__(self, *args: object) -> None:
        if self.enabled:
            self._progress.stop()

    def emit(self, event: TranscriptionEvent) -> None:
        if not self.enabled or self._task_id is None:
            return
        if isinstance(event, TranscriptionProgress):
            total = max(1, event.total_ms)
            completed = min(total, max(0, event.completed_ms))
            self._total = total
            self._progress.update(self._task_id, total=total, completed=completed)
        elif isinstance(event, TranscriptReplayStarted):
            self._progress.update(
                self._task_id,
                description=f"Reusing transcript {event.transcript_id}",
                total=1,
                completed=1,
            )
            self._total = 1

    def complete(self, *, reused: bool) -> None:
        if not self.enabled or self._task_id is None:
            return
        total = self._total or 1
        self._progress.update(
            self._task_id,
            description="Reused" if reused else "Transcribed",
            total=total,
            completed=total,
        )


def _stderr_is_terminal() -> bool:
    return sys.stderr.isatty()


app = typer.Typer(
    name="tp",
    help="Local-first transcription and transcript management.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=DefaultCommandGroup,
)
config_app = typer.Typer(
    help="Inspect and edit tranpro configuration.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(config_app, name="config")
app.add_typer(library_app, name="library")
app.add_typer(prompt_app, name="prompt")
app.add_typer(google_app, name="google")
app.command("publish")(publish_google_doc)
app.command("diarize")(diarize_recording)
app.command("list")(list_recordings)
app.command("show")(show_recording)
app.command("search")(search_library)
app.command("forget")(forget_recording)
app.command("restore")(restore_recording)
app.command("open")(open_recording)


@app.command("transcribe")
def transcribe(
    source: Annotated[
        Path, typer.Argument(help="Audio/video path or library recording ID.")
    ],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Markdown path, or - for stdout."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Named provider profile from config.toml."),
    ] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override the profile provider.")
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Override the provider model or model path."),
    ] = None,
    whisper_cli: Annotated[
        Path | None,
        typer.Option(
            "--whisper-cli", help="Path to whisper-cli when using whisper-cpp."
        ),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option("--language", help="Language override supported by the provider."),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option("--no-save", help="Do not add this run to the SQLite library."),
    ] = False,
    retranscribe: Annotated[
        bool,
        typer.Option(
            "--retranscribe", help="Run the model even if an equivalent run exists."
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an explicitly selected output path."),
    ] = False,
    live: Annotated[
        bool,
        typer.Option(
            "--live", help="Print finalized timestamped segments during transcription."
        ),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress", help="Disable the interactive transcription progress bar."
        ),
    ] = False,
    trash_source: Annotated[
        bool,
        typer.Option(
            "--trash-source",
            "-d",
            help="Move source to OS Trash after every requested output succeeds.",
        ),
    ] = False,
    summarize_after: Annotated[
        bool,
        typer.Option(
            "--summarize", help="Create a summary after the saved transcript succeeds."
        ),
    ] = False,
) -> None:
    """Transcribe one recording; this is also the default tp action."""

    paths = AppPaths.for_user()
    try:
        if live and output == "-":
            raise TranscriptionError("--live cannot be combined with --output -")
        if summarize_after and output == "-":
            raise TranscriptionError("--summarize cannot be combined with --output -")
        if summarize_after and no_save:
            raise TranscriptionError("--summarize requires a saved transcript")
        config = Config.load(paths)
        repository = LibraryRepository(Database(paths))
        source = _resolve_transcription_source(source, repository)
        profile_name = profile or config.default_transcription_profile
        profile_values = config.profile(profile_name)
        selected_provider = build_provider(
            profile_values,
            provider_override=provider,
            model_override=model,
            whisper_cli_override=whisper_cli,
            language_override=language,
            live=live,
        )
        service = TranscriptionService(
            provider=selected_provider,
            repository=repository,
        )
        output_path = None
        if output is not None and output != "-":
            output_path = Path(output)
        request = TranscriptionRequest(
            source=source,
            output=output_path,
            output_to_stdout=output == "-",
            save=not no_save,
            retranscribe=retranscribe,
            force=force,
            trash_source=trash_source,
        )
        progress_enabled = not live and not no_progress and _stderr_is_terminal()
        with TerminalProgress(enabled=progress_enabled) as progress:
            event_sink = (
                _render_live_event
                if live
                else (progress.emit if progress_enabled else None)
            )
            outcome = service.run(request, emit=event_sink)
            progress.complete(reused=outcome.reused)
        if request.output_to_stdout:
            typer.echo(outcome.markdown, nl=False)
        elif outcome.output_path is not None:
            action = "Reused" if outcome.reused else "Created"
            typer.echo(f"{action} transcript {outcome.transcript_id or 'unsaved'}")
            typer.echo(f"Markdown: {outcome.output_path}")
        if summarize_after:
            assert outcome.transcript_id is not None
            summary_outcome = _summarize_transcript(
                outcome.transcript_id,
                config=config,
                repository=repository,
            )
            typer.echo(f"Created summary {summary_outcome.summary_id}")
            typer.echo(f"Markdown: {summary_outcome.output_path}")
        service.finalize_trash(outcome)
        if trash_source:
            typer.echo(f"Moved source to Trash: {outcome.source}", err=True)
    except (
        ConfigError,
        DatabaseError,
        LibraryError,
        TranscriptionError,
        SummarizationError,
        ContextPlanningError,
        OSError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


@app.command("summarize")
def summarize_recording(
    recording_id: Annotated[
        int, typer.Argument(min=1, help="Library recording ID to summarize.")
    ],
    transcript_id: Annotated[
        int | None,
        typer.Option("--transcript", min=1, help="Use an exact transcript run."),
    ] = None,
    prompt: Annotated[
        str, typer.Option("--prompt", help="Saved prompt name.")
    ] = "detailed-notes",
    prompt_version: Annotated[
        int | None,
        typer.Option("--prompt-version", min=1, help="Exact saved prompt version."),
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Named summary profile.")
    ] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override summary provider.")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="Override summary model.")
    ] = None,
    context_tokens: Annotated[
        int | None,
        typer.Option(
            "--context-tokens", min=2048, help="Effective runtime context window."
        ),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Summary Markdown path.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an explicitly selected output.")
    ] = False,
    without_speakers: Annotated[
        bool,
        typer.Option(
            "--without-speakers",
            help="Ignore an existing diarization when creating the summary.",
        ),
    ] = False,
) -> None:
    """Explicitly summarize a saved transcript with a local or hosted profile."""

    paths = AppPaths.for_user()
    try:
        config = Config.load(paths)
        repository = LibraryRepository(Database(paths))
        selected_transcript = (
            repository.get_preferred_transcript(recording_id)
            if transcript_id is None
            else repository.get_transcript(transcript_id)
        )
        if selected_transcript.recording_id != recording_id:
            raise SummarizationError(
                f"Transcript {selected_transcript.id} does not belong to "
                f"recording {recording_id}"
            )
        outcome = _summarize_transcript(
            selected_transcript.id,
            config=config,
            repository=repository,
            profile=profile,
            provider=provider,
            model=model,
            context_tokens=context_tokens,
            prompt=prompt,
            prompt_version=prompt_version,
            output=output,
            force=force,
            use_speakers=not without_speakers,
        )
        typer.echo(f"Created summary {outcome.summary_id}")
        typer.echo(f"Context: {outcome.context_mode}")
        typer.echo(f"Markdown: {outcome.output_path}")
    except (
        ConfigError,
        DatabaseError,
        LibraryError,
        SummarizationError,
        ContextPlanningError,
        OSError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


def _summarize_transcript(
    transcript_id: int,
    *,
    config: Config,
    repository: LibraryRepository,
    profile: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    context_tokens: int | None = None,
    prompt: str = "detailed-notes",
    prompt_version: int | None = None,
    output: Path | None = None,
    force: bool = False,
    use_speakers: bool = True,
) -> SummaryOutcome:
    profile_name = profile or config.default_summary_profile
    selected_provider = build_summary_provider(
        config.profile(profile_name),
        provider_override=provider,
        model_override=model,
        context_override=context_tokens,
    )
    service = SummaryService(provider=selected_provider, repository=repository)
    with Console(stderr=True).status("[bold]Summarizing[/bold]"):
        return service.run(
            transcript_id,
            prompt_name=prompt,
            prompt_version=prompt_version,
            output=output,
            force=force,
            use_speakers=use_speakers,
        )


def _resolve_transcription_source(source: Path, repository: LibraryRepository) -> Path:
    """Resolve a numeric recording ID while preserving real numeric paths."""

    expanded = source.expanduser()
    if expanded.exists() or not str(source).isdigit():
        return expanded
    recording = repository.get_recording(int(str(source)))
    if recording.current_path is None:
        raise TranscriptionError(
            f"Recording {recording.id} has no current source file; "
            "restore it before retranscribing"
        )
    return recording.current_path


def _render_live_event(event: TranscriptionEvent) -> None:
    if isinstance(event, TranscriptReplayStarted):
        typer.echo(f"Replaying saved transcript {event.transcript_id}", err=True)
    elif isinstance(event, TranscriptSegmentFinalized):
        segment = event.segment
        typer.echo(f"[{format_timestamp(segment.start_ms)}] {segment.text}")
    elif isinstance(event, TranscriptionProgress):
        return


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tranpro {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    """Local-first transcription and transcript management."""


@config_app.callback()
def config_root(context: typer.Context) -> None:
    """Inspect and edit tranpro configuration."""

    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


@app.command("paths")
def show_paths() -> None:
    """Show where tranpro keeps private application state."""

    paths = AppPaths.for_user()
    rows = (
        ("Data", paths.data_dir),
        ("Config", paths.config_file),
        ("Database", paths.database_file),
        ("Backups", paths.backup_dir),
        ("Cache", paths.cache_dir),
    )
    for label, path in rows:
        typer.echo(f"{label:<9} {path}")


@config_app.command("show")
def show_config() -> None:
    """Print the active config, or the defaults when no file exists."""

    paths = AppPaths.for_user()
    try:
        Config.load(paths)
    except ConfigError as error:
        raise typer.BadParameter(str(error)) from error

    if paths.config_file.exists():
        typer.echo(paths.config_file.read_text(encoding="utf-8"), nl=False)
    else:
        typer.echo("# Built-in defaults; run `tp config init` to save them.\n")
        typer.echo(DEFAULT_CONFIG, nl=False)


@config_app.command("init")
def init_config() -> None:
    """Write the default config without replacing an existing file."""

    path, created = initialize_config()
    if created:
        typer.echo(f"Created {path}")
    else:
        typer.echo(f"Already exists: {path}")


@config_app.command("edit")
def edit_config() -> None:
    """Open the user config in $VISUAL or $EDITOR."""

    path, _ = initialize_config()
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise typer.BadParameter("Set $VISUAL or $EDITOR before using config edit")
    try:
        subprocess.run([*shlex.split(editor), str(path)], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise typer.BadParameter(f"Could not open editor: {error}") from error


def main() -> None:
    app()


if __name__ == "__main__":
    main()
