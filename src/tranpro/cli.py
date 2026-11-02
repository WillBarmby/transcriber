"""Command-line entry point for tranpro."""

from __future__ import annotations

import os
import shlex
import subprocess

import typer

from tranpro import __version__
from tranpro.config import DEFAULT_CONFIG, Config, ConfigError, initialize_config
from tranpro.paths import AppPaths

app = typer.Typer(
    name="tp",
    help="Local-first transcription and transcript management.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
config_app = typer.Typer(
    help="Inspect and edit tranpro configuration.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(config_app, name="config")


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
