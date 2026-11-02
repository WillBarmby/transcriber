"""Command-line entry point for tranpro."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from tranpro import __version__
from tranpro.config import DEFAULT_CONFIG, Config, ConfigError, initialize_config
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
from tranpro.transcription.factory import build_provider
from tranpro.transcription.models import (
    TranscriptionError,
    TranscriptionRequest,
)
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
        return path.exists() or path.suffix.lower() in _AUDIO_SUFFIXES


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
app.command("list")(list_recordings)
app.command("show")(show_recording)
app.command("search")(search_library)
app.command("forget")(forget_recording)
app.command("restore")(restore_recording)
app.command("open")(open_recording)


@app.command("transcribe")
def transcribe(
    source: Annotated[Path, typer.Argument(help="Audio or video file to transcribe.")],
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
    trash_source: Annotated[
        bool,
        typer.Option(
            "--trash-source",
            "-d",
            help="Move source to OS Trash after every requested output succeeds.",
        ),
    ] = False,
) -> None:
    """Transcribe one recording; this is also the default tp action."""

    paths = AppPaths.for_user()
    try:
        config = Config.load(paths)
        profile_name = profile or config.default_transcription_profile
        profile_values = config.profile(profile_name)
        selected_provider = build_provider(
            profile_values,
            provider_override=provider,
            model_override=model,
            whisper_cli_override=whisper_cli,
            language_override=language,
        )
        service = TranscriptionService(
            provider=selected_provider,
            repository=LibraryRepository(Database(paths)),
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
        outcome = service.run(request)
        if request.output_to_stdout:
            typer.echo(outcome.markdown, nl=False)
        elif outcome.output_path is not None:
            action = "Reused" if outcome.reused else "Created"
            typer.echo(f"{action} transcript {outcome.transcript_id or 'unsaved'}")
            typer.echo(f"Markdown: {outcome.output_path}")
        service.finalize_trash(outcome)
        if trash_source:
            typer.echo(f"Moved source to Trash: {outcome.source}", err=True)
    except (
        ConfigError,
        DatabaseError,
        LibraryError,
        TranscriptionError,
        OSError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


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
