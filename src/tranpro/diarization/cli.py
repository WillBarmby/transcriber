"""Command-line speaker diarization workflow."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console

from tranpro.config import Config, ConfigError
from tranpro.diarization.factory import build_diarization_provider
from tranpro.diarization.models import DiarizationError
from tranpro.diarization.service import DiarizationService
from tranpro.library.database import Database, DatabaseError
from tranpro.library.repository import LibraryError, LibraryRepository
from tranpro.paths import AppPaths


def diarize_recording(
    recording_id: Annotated[
        int, typer.Argument(min=1, help="Library recording ID to diarize.")
    ],
    transcript_id: Annotated[
        int | None,
        typer.Option("--transcript", min=1, help="Align an exact transcript run."),
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Named diarization profile.")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="Override the diarization model.")
    ] = None,
    preset: Annotated[
        str | None,
        typer.Option(
            "--preset",
            help="Nemotron latency preset: offline, low, very-low, or ultra-low.",
        ),
    ] = None,
    threshold: Annotated[
        float | None,
        typer.Option(
            "--threshold", min=0.01, max=0.99, help="Speaker activity cutoff."
        ),
    ] = None,
    min_duration: Annotated[
        float | None,
        typer.Option(
            "--min-duration", min=0, help="Discard shorter speaker turns (seconds)."
        ),
    ] = None,
    merge_gap: Annotated[
        float | None,
        typer.Option(
            "--merge-gap",
            min=0,
            help="Merge same-speaker gaps up to this many seconds.",
        ),
    ] = None,
    rediarize: Annotated[
        bool,
        typer.Option(
            "--rediarize", help="Run the model even if an equivalent run exists."
        ),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Disable the terminal activity spinner."),
    ] = False,
) -> None:
    """Identify who spoke when and align speakers to a saved transcript."""

    paths = AppPaths.for_user()
    try:
        config = Config.load(paths)
        profile_name = profile or config.default_diarization_profile
        provider = build_diarization_provider(
            config.profile(profile_name),
            model_override=model,
            preset_override=None if preset is None else preset.replace("-", "_"),
            threshold_override=threshold,
            min_duration_override=min_duration,
            merge_gap_override=merge_gap,
        )
        repository = LibraryRepository(Database(paths))
        service = DiarizationService(provider=provider, repository=repository)
        show_progress = not no_progress and sys.stderr.isatty()
        if show_progress:
            with Console(stderr=True).status("[bold]Identifying speakers[/bold]"):
                outcome = service.run(
                    recording_id,
                    transcript_id=transcript_id,
                    rediarize=rediarize,
                )
        else:
            outcome = service.run(
                recording_id,
                transcript_id=transcript_id,
                rediarize=rediarize,
            )
        action = "Reused" if outcome.reused else "Created"
        speaker_label = "speaker" if outcome.speakers == 1 else "speakers"
        turn_label = "turn" if outcome.turns == 1 else "turns"
        typer.echo(f"{action} diarization {outcome.diarization_id}")
        typer.echo(
            f"Aligned transcript {outcome.transcript_id}: "
            f"{outcome.speakers} {speaker_label}, {outcome.turns} {turn_label}"
        )
    except (
        ConfigError,
        DatabaseError,
        LibraryError,
        DiarizationError,
        OSError,
        ValueError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
