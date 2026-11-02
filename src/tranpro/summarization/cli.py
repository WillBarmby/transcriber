"""Commands for inspecting and versioning reusable summary prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from tranpro.library.database import Database, DatabaseError
from tranpro.library.repository import LibraryError, LibraryRepository
from tranpro.paths import AppPaths

prompt_app = typer.Typer(
    help="Manage reusable, versioned summary prompts.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@prompt_app.callback()
def prompt_root(context: typer.Context) -> None:
    """Manage reusable, versioned summary prompts."""

    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


def _repository() -> LibraryRepository:
    return LibraryRepository(Database(AppPaths.for_user()))


@prompt_app.command("list")
def list_prompts(
    all_versions: Annotated[
        bool, typer.Option("--all", help="Show complete version history.")
    ] = False,
) -> None:
    """List saved prompts."""

    try:
        prompts = _repository().list_prompts(all_versions=all_versions)
    except (DatabaseError, LibraryError) as error:
        _fail(str(error))
    for prompt in prompts:
        origin = "built-in" if prompt.is_builtin else "user"
        typer.echo(f"{prompt.name}@{prompt.version}  {origin}")


@prompt_app.command("show")
def show_prompt(
    name: Annotated[str, typer.Argument(help="Prompt name.")],
    version: Annotated[
        int | None, typer.Option("--version", min=1, help="Exact version to show.")
    ] = None,
) -> None:
    """Print one prompt, using its latest version by default."""

    try:
        prompt = _repository().get_prompt(name, version)
    except (DatabaseError, LibraryError) as error:
        _fail(str(error))
    typer.echo(f"# {prompt.name}@{prompt.version}")
    typer.echo(prompt.instructions)


@prompt_app.command("save")
def save_prompt(
    name: Annotated[str, typer.Argument(help="Stable lowercase prompt name.")],
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Read instructions from a UTF-8 file."),
    ] = None,
    instructions: Annotated[
        str | None,
        typer.Option("--instructions", "-i", help="Prompt instructions inline."),
    ] = None,
) -> None:
    """Save a new prompt version without replacing its history."""

    if (file is None) == (instructions is None):
        raise typer.BadParameter("provide exactly one of --file or --instructions")
    try:
        content = (
            file.expanduser().read_text(encoding="utf-8")
            if file is not None
            else instructions
        )
        assert content is not None
        prompt = _repository().save_prompt(name, content)
    except (DatabaseError, LibraryError, OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"Saved {prompt.name}@{prompt.version}")


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)
