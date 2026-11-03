"""Google authorization and document publication commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from tranpro.library.database import Database, DatabaseError
from tranpro.library.repository import LibraryError, LibraryRepository
from tranpro.paths import AppPaths
from tranpro.publication.auth import (
    GoogleAuthError,
    authorize,
    disconnect,
    install_client_credentials,
)
from tranpro.publication.google_docs import GoogleDocsPublisher, PublicationError
from tranpro.publication.service import PublicationService

google_app = typer.Typer(
    help="Configure Google Docs publication.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@google_app.callback()
def google_root(context: typer.Context) -> None:
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


@google_app.command("setup")
def google_setup(
    credentials: Annotated[
        Path,
        typer.Option(
            "--credentials", help="Downloaded OAuth Desktop client JSON file."
        ),
    ],
) -> None:
    """Install bring-your-own Google OAuth desktop credentials."""

    try:
        path = install_client_credentials(credentials)
    except GoogleAuthError as error:
        _fail(str(error))
    typer.echo(f"Stored OAuth client: {path}")
    typer.echo("Next: tp google authorize")


@google_app.command("authorize")
def google_authorize() -> None:
    """Open browser consent and store the refresh token in Keychain."""

    try:
        authorize()
    except GoogleAuthError as error:
        _fail(str(error))
    typer.echo("Google Docs authorization saved in the system keychain.")


@google_app.command("disconnect")
def google_disconnect() -> None:
    """Remove tranpro's Google refresh token from the system keychain."""

    disconnect()
    typer.echo("Removed Google authorization from the system keychain.")


def publish_google_doc(
    recording_id: Annotated[
        int, typer.Argument(min=1, help="Library recording ID to publish.")
    ],
    with_summary: Annotated[
        bool,
        typer.Option("--with-summary", help="Include the latest grounded summary."),
    ] = False,
    with_timestamps: Annotated[
        bool,
        typer.Option(
            "--with-timestamps",
            help="Include transcript timestamps and summary evidence markers.",
        ),
    ] = False,
    without_speakers: Annotated[
        bool,
        typer.Option(
            "--without-speakers",
            help="Ignore an existing diarization and publish the plain transcript.",
        ),
    ] = False,
    update: Annotated[
        bool,
        typer.Option("--update", help="Replace the latest published Doc explicitly."),
    ] = False,
    title: Annotated[
        str | None, typer.Option("--title", help="Google Doc title override.")
    ] = None,
    folder_id: Annotated[
        str | None,
        typer.Option("--folder", help="Google Drive destination folder ID."),
    ] = None,
    open_document: Annotated[
        bool,
        typer.Option("--open", help="Open the published Doc in your browser."),
    ] = False,
) -> None:
    """Publish a transcript snapshot to a polished Google Doc."""

    paths = AppPaths.for_user()
    try:
        repository = LibraryRepository(Database(paths))
        publisher = GoogleDocsPublisher()
        outcome = PublicationService(
            publisher=publisher, repository=repository
        ).publish(
            recording_id,
            with_summary=with_summary,
            with_timestamps=with_timestamps,
            with_speakers=not without_speakers,
            update=update,
            title=title,
            folder_id=folder_id,
        )
    except (
        DatabaseError,
        GoogleAuthError,
        LibraryError,
        PublicationError,
        OSError,
        ValueError,
    ) as error:
        _fail(str(error))
    action = "Reused" if outcome.reused else "Updated" if outcome.updated else "Created"
    typer.echo(f"{action} publication {outcome.publication_id}")
    typer.echo(outcome.url)
    if open_document and typer.launch(outcome.url) != 0:
        typer.echo("Could not open the browser. Open the URL above manually.", err=True)


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)
