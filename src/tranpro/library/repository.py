"""Repository API for recordings and their versioned derived artifacts."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tranpro.library.database import Database
from tranpro.library.fingerprint import fingerprint_file
from tranpro.library.models import (
    DiarizationRun,
    LibraryStats,
    PromptTemplate,
    Publication,
    Recording,
    RenderedOutput,
    SearchHit,
    Segment,
    SpeakerAssignment,
    SpeakerTurn,
    SummaryRun,
    SummarySection,
    SummaryStep,
    TranscriptRun,
)


class LibraryError(RuntimeError):
    """Base exception for transcript library operations."""


class RecordNotFoundError(LibraryError):
    """Raised when a requested recording does not exist."""


_PROMPT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class LibraryRepository:
    """Expose storage operations in domain terms instead of SQL."""

    def __init__(self, database: Database | None = None) -> None:
        self.database = database or Database()

    def register_recording(
        self,
        path: Path,
        *,
        fingerprint: str | None = None,
        duration_ms: int | None = None,
        language: str | None = None,
    ) -> tuple[Recording, bool]:
        """Return the recording for a source, creating it only when unseen."""

        source = path.expanduser().resolve()
        stat = source.stat()
        source_fingerprint = fingerprint or fingerprint_file(source)
        timestamp = now_iso()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM recordings WHERE fingerprint = ?",
                (source_fingerprint,),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    """
                    UPDATE recordings
                    SET current_path = ?, file_size_bytes = ?, file_mtime_ns = ?,
                        duration_ms = coalesce(?, duration_ms),
                        language = coalesce(?, language), deleted_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        str(source),
                        stat.st_size,
                        stat.st_mtime_ns,
                        duration_ms,
                        language,
                        timestamp,
                        int(existing["id"]),
                    ),
                )
                updated = connection.execute(
                    "SELECT * FROM recordings WHERE id = ?", (int(existing["id"]),)
                ).fetchone()
                assert updated is not None
                return self._recording(updated), False

            cursor = connection.execute(
                """
                INSERT INTO recordings(
                    fingerprint, original_path, current_path, file_size_bytes,
                    file_mtime_ns, duration_ms, language, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_fingerprint,
                    str(source),
                    str(source),
                    stat.st_size,
                    stat.st_mtime_ns,
                    duration_ms,
                    language,
                    timestamp,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            row = connection.execute(
                "SELECT * FROM recordings WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            assert row is not None
            return self._recording(row), True

    def find_recording_by_fingerprint(self, fingerprint: str) -> Recording | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recordings WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            return None if row is None else self._recording(row)

    def get_recording(
        self, recording_id: int, *, include_deleted: bool = True
    ) -> Recording:
        with self.database.connect() as connection:
            sql = "SELECT * FROM recordings WHERE id = ?"
            parameters: tuple[Any, ...] = (recording_id,)
            if not include_deleted:
                sql += " AND deleted_at IS NULL"
            row = connection.execute(sql, parameters).fetchone()
            if row is None:
                raise RecordNotFoundError(f"Recording {recording_id} was not found")
            return self._recording(row)

    def list_recordings(
        self, *, include_deleted: bool = False, limit: int = 100
    ) -> list[Recording]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.database.connect() as connection:
            where = "" if include_deleted else "WHERE deleted_at IS NULL"
            rows = connection.execute(
                f"""
                SELECT * FROM recordings
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._recording(row) for row in rows]

    def add_transcript(
        self,
        recording_id: int,
        *,
        provider: str,
        model: str,
        segments: Iterable[Segment],
        settings: Mapping[str, Any] | None = None,
        language: str | None = None,
        prefer: bool = True,
    ) -> TranscriptRun:
        """Atomically add one successful, immutable transcript run."""

        materialized_segments = list(segments)
        self._validate_segments(materialized_segments)
        timestamp = now_iso()
        settings_json = self._canonical_json(settings or {})
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            if prefer:
                connection.execute(
                    """
                    UPDATE transcript_runs
                    SET is_preferred = 0
                    WHERE recording_id = ?
                    """,
                    (recording_id,),
                )
            cursor = connection.execute(
                """
                INSERT INTO transcript_runs(
                    recording_id, provider, model, settings_json, status,
                    language, is_preferred, started_at, completed_at, created_at
                ) VALUES (?, ?, ?, ?, 'succeeded', ?, ?, ?, ?, ?)
                """,
                (
                    recording_id,
                    provider,
                    model,
                    settings_json,
                    language,
                    int(prefer),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            transcript_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO transcript_segments(
                    transcript_id, segment_index, stable_ref, speaker,
                    start_ms, end_ms, text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        transcript_id,
                        segment.index,
                        segment.stable_ref,
                        segment.speaker,
                        segment.start_ms,
                        segment.end_ms,
                        segment.text,
                    )
                    for segment in materialized_segments
                ],
            )
            row = connection.execute(
                "SELECT * FROM transcript_runs WHERE id = ?", (transcript_id,)
            ).fetchone()
            assert row is not None
            return self._transcript(row)

    def find_reusable_transcript(
        self,
        recording_id: int,
        *,
        provider: str,
        model: str,
        settings: Mapping[str, Any] | None = None,
    ) -> TranscriptRun | None:
        settings_json = self._canonical_json(settings or {})
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM transcript_runs
                WHERE recording_id = ? AND provider = ? AND model = ?
                  AND settings_json = ? AND status = 'succeeded'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (recording_id, provider, model, settings_json),
            ).fetchone()
            return None if row is None else self._transcript(row)

    def list_transcripts(self, recording_id: int) -> list[TranscriptRun]:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            rows = connection.execute(
                """
                SELECT * FROM transcript_runs
                WHERE recording_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (recording_id,),
            ).fetchall()
            return [self._transcript(row) for row in rows]

    def get_transcript(self, transcript_id: int) -> TranscriptRun:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM transcript_runs WHERE id = ?", (transcript_id,)
            ).fetchone()
            if row is None:
                raise LibraryError(f"Transcript {transcript_id} was not found")
            return self._transcript(row)

    def get_preferred_transcript(self, recording_id: int) -> TranscriptRun:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            row = connection.execute(
                """
                SELECT * FROM transcript_runs
                WHERE recording_id = ? AND is_preferred = 1
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (recording_id,),
            ).fetchone()
            if row is None:
                raise LibraryError(
                    f"Recording {recording_id} has no preferred transcript"
                )
            return self._transcript(row)

    def get_segments(self, transcript_id: int) -> list[Segment]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM transcript_segments
                WHERE transcript_id = ?
                ORDER BY segment_index
                """,
                (transcript_id,),
            ).fetchall()
            if not rows:
                transcript = connection.execute(
                    "SELECT id FROM transcript_runs WHERE id = ?", (transcript_id,)
                ).fetchone()
                if transcript is None:
                    raise LibraryError(f"Transcript {transcript_id} was not found")
            return [
                Segment(
                    index=int(row["segment_index"]),
                    start_ms=int(row["start_ms"]),
                    end_ms=int(row["end_ms"]),
                    text=str(row["text"]),
                    speaker=None if row["speaker"] is None else str(row["speaker"]),
                )
                for row in rows
            ]

    def begin_diarization(
        self,
        recording_id: int,
        *,
        provider: str,
        model: str,
        settings: Mapping[str, Any] | None = None,
    ) -> DiarizationRun:
        """Create a running recording-level diarization artifact."""

        timestamp = now_iso()
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            cursor = connection.execute(
                """
                INSERT INTO diarization_runs(
                    recording_id, provider, model, settings_json, status,
                    started_at, created_at
                ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    recording_id,
                    provider,
                    model,
                    self._canonical_json(settings or {}),
                    timestamp,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            row = connection.execute(
                "SELECT * FROM diarization_runs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            assert row is not None
            return self._diarization(row)

    def complete_diarization(
        self,
        diarization_id: int,
        *,
        transcript_id: int,
        turns: Iterable[SpeakerTurn],
        assignments: Iterable[SpeakerAssignment],
    ) -> DiarizationRun:
        """Atomically seal a run with its timeline and first transcript projection."""

        materialized_turns = list(turns)
        materialized_assignments = list(assignments)
        self._validate_turns(materialized_turns)
        timestamp = now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM diarization_runs WHERE id = ?",
                (diarization_id,),
            ).fetchone()
            if row is None or row["status"] != "running":
                raise LibraryError(
                    f"Running diarization {diarization_id} was not found"
                )
            self._validate_diarization_assignments(
                connection,
                recording_id=int(row["recording_id"]),
                transcript_id=transcript_id,
                assignments=materialized_assignments,
            )
            connection.executemany(
                """
                INSERT INTO speaker_turns(
                    diarization_id, turn_index, source_speaker, speaker,
                    start_ms, end_ms, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        diarization_id,
                        turn.index,
                        turn.source_speaker,
                        turn.speaker,
                        turn.start_ms,
                        turn.end_ms,
                        turn.confidence,
                    )
                    for turn in materialized_turns
                ],
            )
            self._insert_diarization_assignments(
                connection,
                diarization_id=diarization_id,
                transcript_id=transcript_id,
                assignments=materialized_assignments,
            )
            connection.execute(
                """
                UPDATE diarization_runs SET is_preferred = 0
                WHERE recording_id = ?
                """,
                (int(row["recording_id"]),),
            )
            connection.execute(
                """
                UPDATE diarization_runs
                SET status = 'succeeded', is_preferred = 1, completed_at = ?
                WHERE id = ?
                """,
                (timestamp, diarization_id),
            )
            completed = connection.execute(
                "SELECT * FROM diarization_runs WHERE id = ?",
                (diarization_id,),
            ).fetchone()
            assert completed is not None
            return self._diarization(completed)

    def fail_diarization(self, diarization_id: int, error: str) -> DiarizationRun:
        timestamp = now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE diarization_runs
                SET status = 'failed', error = ?, completed_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (error, timestamp, diarization_id),
            )
            if cursor.rowcount == 0:
                raise LibraryError(
                    f"Running diarization {diarization_id} was not found"
                )
            row = connection.execute(
                "SELECT * FROM diarization_runs WHERE id = ?",
                (diarization_id,),
            ).fetchone()
            assert row is not None
            return self._diarization(row)

    def add_diarization_assignments(
        self,
        diarization_id: int,
        transcript_id: int,
        assignments: Iterable[SpeakerAssignment],
    ) -> None:
        """Attach an immutable projection for another transcript of the recording."""

        materialized = list(assignments)
        with self.database.connect() as connection:
            run = connection.execute(
                "SELECT * FROM diarization_runs WHERE id = ? AND status = 'succeeded'",
                (diarization_id,),
            ).fetchone()
            if run is None:
                raise LibraryError(
                    f"Successful diarization {diarization_id} was not found"
                )
            self._validate_diarization_assignments(
                connection,
                recording_id=int(run["recording_id"]),
                transcript_id=transcript_id,
                assignments=materialized,
            )
            existing = connection.execute(
                """
                SELECT count(*) AS count FROM diarization_assignments
                WHERE diarization_id = ? AND transcript_id = ?
                """,
                (diarization_id, transcript_id),
            ).fetchone()
            assert existing is not None
            if int(existing["count"]) > 0:
                raise LibraryError(
                    f"Diarization {diarization_id} already has assignments for "
                    f"transcript {transcript_id}"
                )
            self._insert_diarization_assignments(
                connection,
                diarization_id=diarization_id,
                transcript_id=transcript_id,
                assignments=materialized,
            )

    def find_reusable_diarization(
        self,
        recording_id: int,
        *,
        provider: str,
        model: str,
        settings: Mapping[str, Any] | None = None,
    ) -> DiarizationRun | None:
        settings_json = self._canonical_json(settings or {})
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM diarization_runs
                WHERE recording_id = ? AND provider = ? AND model = ?
                  AND settings_json = ? AND status = 'succeeded'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (recording_id, provider, model, settings_json),
            ).fetchone()
            return None if row is None else self._diarization(row)

    def get_preferred_diarization(self, recording_id: int) -> DiarizationRun:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            row = connection.execute(
                """
                SELECT * FROM diarization_runs
                WHERE recording_id = ? AND is_preferred = 1
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (recording_id,),
            ).fetchone()
            if row is None:
                raise LibraryError(
                    f"Recording {recording_id} has no preferred diarization"
                )
            return self._diarization(row)

    def list_diarizations(self, recording_id: int) -> list[DiarizationRun]:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            rows = connection.execute(
                """
                SELECT * FROM diarization_runs WHERE recording_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (recording_id,),
            ).fetchall()
            return [self._diarization(row) for row in rows]

    def get_speaker_turns(self, diarization_id: int) -> list[SpeakerTurn]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM speaker_turns WHERE diarization_id = ?
                ORDER BY turn_index
                """,
                (diarization_id,),
            ).fetchall()
            if not rows:
                run = connection.execute(
                    "SELECT id FROM diarization_runs WHERE id = ?",
                    (diarization_id,),
                ).fetchone()
                if run is None:
                    raise LibraryError(f"Diarization {diarization_id} was not found")
            return [
                SpeakerTurn(
                    index=int(row["turn_index"]),
                    start_ms=int(row["start_ms"]),
                    end_ms=int(row["end_ms"]),
                    speaker=str(row["speaker"]),
                    source_speaker=str(row["source_speaker"]),
                    confidence=(
                        None if row["confidence"] is None else float(row["confidence"])
                    ),
                )
                for row in rows
            ]

    def get_speaker_assignments(
        self, diarization_id: int, transcript_id: int
    ) -> list[SpeakerAssignment]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM diarization_assignments
                WHERE diarization_id = ? AND transcript_id = ?
                ORDER BY segment_index
                """,
                (diarization_id, transcript_id),
            ).fetchall()
            return [
                SpeakerAssignment(
                    segment_index=int(row["segment_index"]),
                    stable_ref=str(row["stable_ref"]),
                    speaker=None if row["speaker"] is None else str(row["speaker"]),
                    overlap_ms=int(row["overlap_ms"]),
                    confidence=float(row["confidence"]),
                    status=str(row["status"]),
                )
                for row in rows
            ]

    def get_diarized_segments(
        self, diarization_id: int, transcript_id: int
    ) -> list[Segment]:
        segments = self.get_segments(transcript_id)
        assignments = self.get_speaker_assignments(diarization_id, transcript_id)
        if len(assignments) != len(segments):
            raise LibraryError(
                f"Diarization {diarization_id} is not aligned to transcript "
                f"{transcript_id}"
            )
        return [
            Segment(
                index=segment.index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                speaker=assignment.speaker,
            )
            for segment, assignment in zip(segments, assignments, strict=True)
        ]

    def save_prompt(self, name: str, instructions: str) -> PromptTemplate:
        """Save a new immutable version of a user prompt."""

        normalized_name = name.strip().lower()
        normalized_instructions = instructions.strip()
        if not _PROMPT_NAME.fullmatch(normalized_name):
            raise ValueError(
                "prompt name must start with a letter and contain only "
                "lowercase letters, numbers, and hyphens"
            )
        if not normalized_instructions:
            raise ValueError("prompt instructions cannot be empty")
        timestamp = now_iso()
        with self.database.connect() as connection:
            latest = connection.execute(
                "SELECT max(version) AS version FROM prompts WHERE name = ?",
                (normalized_name,),
            ).fetchone()
            assert latest is not None
            version = int(latest["version"] or 0) + 1
            cursor = connection.execute(
                """
                INSERT INTO prompts(name, version, instructions, is_builtin, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (normalized_name, version, normalized_instructions, timestamp),
            )
            assert cursor.lastrowid is not None
            row = connection.execute(
                "SELECT * FROM prompts WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            assert row is not None
            return self._prompt(row)

    def get_prompt(self, name: str, version: int | None = None) -> PromptTemplate:
        """Return an exact prompt version, or the latest version by name."""

        with self.database.connect() as connection:
            if version is None:
                row = connection.execute(
                    """
                    SELECT * FROM prompts WHERE name = ?
                    ORDER BY version DESC LIMIT 1
                    """,
                    (name,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM prompts WHERE name = ? AND version = ?",
                    (name, version),
                ).fetchone()
            if row is None:
                suffix = "" if version is None else f"@{version}"
                raise LibraryError(f"Prompt {name}{suffix} was not found")
            return self._prompt(row)

    def list_prompts(self, *, all_versions: bool = False) -> list[PromptTemplate]:
        """List latest prompt versions unless full history is requested."""

        with self.database.connect() as connection:
            if all_versions:
                rows = connection.execute(
                    "SELECT * FROM prompts ORDER BY name, version DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT prompt.* FROM prompts AS prompt
                    JOIN (
                        SELECT name, max(version) AS version
                        FROM prompts GROUP BY name
                    ) AS latest
                      ON latest.name = prompt.name
                     AND latest.version = prompt.version
                    ORDER BY prompt.name
                    """
                ).fetchall()
            return [self._prompt(row) for row in rows]

    def begin_summary(
        self,
        transcript_id: int,
        *,
        prompt: PromptTemplate,
        system_contract: str,
        provider: str,
        model: str,
        settings: Mapping[str, Any] | None = None,
        context_plan: Mapping[str, Any] | None = None,
    ) -> SummaryRun:
        """Create a running summary with frozen prompt and planning inputs."""

        timestamp = now_iso()
        with self.database.connect() as connection:
            transcript = connection.execute(
                "SELECT id FROM transcript_runs WHERE id = ?", (transcript_id,)
            ).fetchone()
            if transcript is None:
                raise LibraryError(f"Transcript {transcript_id} was not found")
            cursor = connection.execute(
                """
                INSERT INTO summary_runs(
                    transcript_id, prompt_id, prompt_name, prompt_version,
                    prompt_instructions, system_contract, provider, model,
                    settings_json, context_plan_json, status, started_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    transcript_id,
                    prompt.id,
                    prompt.name,
                    prompt.version,
                    prompt.instructions,
                    system_contract,
                    provider,
                    model,
                    self._canonical_json(settings or {}),
                    (
                        None
                        if context_plan is None
                        else self._canonical_json(context_plan)
                    ),
                    timestamp,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            row = connection.execute(
                "SELECT * FROM summary_runs WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            assert row is not None
            return self._summary(row)

    def add_summary_step(
        self,
        summary_id: int,
        *,
        kind: str,
        output_text: str,
        input_segment_refs: Iterable[str] = (),
        input_step_indexes: Iterable[int] = (),
        usage: Mapping[str, int | float] | None = None,
    ) -> SummaryStep:
        """Append an auditable intermediate result to a running summary."""

        if kind not in {"source", "synthesis"}:
            raise ValueError("summary step kind must be source or synthesis")
        if not output_text.strip():
            raise ValueError("summary step output cannot be empty")
        segment_refs = tuple(input_segment_refs)
        step_indexes = tuple(input_step_indexes)
        timestamp = now_iso()
        with self.database.connect() as connection:
            summary = connection.execute(
                "SELECT status FROM summary_runs WHERE id = ?", (summary_id,)
            ).fetchone()
            if summary is None:
                raise LibraryError(f"Summary {summary_id} was not found")
            if summary["status"] != "running":
                raise LibraryError(
                    "summary steps can only be added to a running summary"
                )
            next_row = connection.execute(
                """
                SELECT coalesce(max(step_index), -1) + 1 AS step_index
                FROM summary_steps WHERE summary_id = ?
                """,
                (summary_id,),
            ).fetchone()
            assert next_row is not None
            index = int(next_row["step_index"])
            connection.execute(
                """
                INSERT INTO summary_steps(
                    summary_id, step_index, kind, input_segment_refs_json,
                    input_step_indexes_json, output_text, usage_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    index,
                    kind,
                    self._canonical_json(segment_refs),
                    self._canonical_json(step_indexes),
                    output_text.strip(),
                    self._canonical_json(usage or {}),
                    timestamp,
                ),
            )
            return SummaryStep(
                index=index,
                kind=kind,
                input_segment_refs=segment_refs,
                input_step_indexes=step_indexes,
                output_text=output_text.strip(),
                usage=dict(usage or {}),
            )

    def complete_summary(
        self, summary_id: int, sections: Iterable[SummarySection]
    ) -> SummaryRun:
        """Atomically attach final sections and seal a running summary."""

        materialized = list(sections)
        if not materialized:
            raise ValueError("a successful summary requires at least one section")
        if any(
            not section.heading.strip() or not section.body.strip()
            for section in materialized
        ):
            raise ValueError("summary sections require a heading and body")
        timestamp = now_iso()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM summary_runs WHERE id = ?", (summary_id,)
            ).fetchone()
            if row is None:
                raise LibraryError(f"Summary {summary_id} was not found")
            if row["status"] != "running":
                raise LibraryError("only a running summary can be completed")
            known_rows = connection.execute(
                "SELECT stable_ref FROM transcript_segments WHERE transcript_id = ?",
                (int(row["transcript_id"]),),
            ).fetchall()
            known_refs = {str(item["stable_ref"]) for item in known_rows}
            cited_refs = {
                ref for section in materialized for ref in section.segment_refs
            }
            unknown = sorted(cited_refs - known_refs)
            if unknown:
                raise ValueError(
                    f"unknown transcript segment references: {', '.join(unknown)}"
                )
            connection.executemany(
                """
                INSERT INTO summary_sections(
                    summary_id, section_index, heading, body, segment_refs_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary_id,
                        index,
                        section.heading.strip(),
                        section.body.strip(),
                        self._canonical_json(section.segment_refs),
                    )
                    for index, section in enumerate(materialized)
                ],
            )
            connection.execute(
                """
                UPDATE summary_runs
                SET status = 'succeeded', completed_at = ?
                WHERE id = ?
                """,
                (timestamp, summary_id),
            )
            completed = connection.execute(
                "SELECT * FROM summary_runs WHERE id = ?", (summary_id,)
            ).fetchone()
            assert completed is not None
            return self._summary(completed)

    def fail_summary(self, summary_id: int, error: str) -> SummaryRun:
        """Seal a running summary as failed while retaining its audit trail."""

        timestamp = now_iso()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE summary_runs
                SET status = 'failed', error = ?, completed_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (error, timestamp, summary_id),
            )
            if cursor.rowcount == 0:
                raise LibraryError(f"Running summary {summary_id} was not found")
            row = connection.execute(
                "SELECT * FROM summary_runs WHERE id = ?", (summary_id,)
            ).fetchone()
            assert row is not None
            return self._summary(row)

    def add_summary(
        self,
        transcript_id: int,
        *,
        provider: str,
        model: str,
        sections: Iterable[SummarySection],
        prompt_name: str = "detailed-notes",
        prompt_version: int = 1,
        prompt_instructions: str | None = None,
        system_contract: str = "Return grounded structured notes.",
        settings: Mapping[str, Any] | None = None,
        context_plan: Mapping[str, Any] | None = None,
    ) -> int:
        """Create and complete a summary run for simple adapter callers."""

        materialized_sections = list(sections)
        saved_prompt = self.get_prompt(prompt_name, prompt_version)
        if (
            prompt_instructions is not None
            and prompt_instructions.strip() != saved_prompt.instructions
        ):
            raise ValueError(
                "prompt instructions do not match the saved prompt version; "
                "save a new prompt version first"
            )
        run = self.begin_summary(
            transcript_id,
            prompt=saved_prompt,
            system_contract=system_contract,
            provider=provider,
            model=model,
            settings=settings,
            context_plan=context_plan,
        )
        return self.complete_summary(run.id, materialized_sections).id

    def get_summary(self, summary_id: int) -> SummaryRun:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM summary_runs WHERE id = ?", (summary_id,)
            ).fetchone()
            if row is None:
                raise LibraryError(f"Summary {summary_id} was not found")
            return self._summary(row)

    def get_summary_sections(self, summary_id: int) -> list[SummarySection]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM summary_sections
                WHERE summary_id = ? ORDER BY section_index
                """,
                (summary_id,),
            ).fetchall()
            if not rows:
                exists = connection.execute(
                    "SELECT id FROM summary_runs WHERE id = ?", (summary_id,)
                ).fetchone()
                if exists is None:
                    raise LibraryError(f"Summary {summary_id} was not found")
            return [
                SummarySection(
                    heading=str(row["heading"]),
                    body=str(row["body"]),
                    segment_refs=tuple(
                        cast(list[str], json.loads(row["segment_refs_json"]))
                    ),
                )
                for row in rows
            ]

    def get_summary_steps(self, summary_id: int) -> list[SummaryStep]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM summary_steps
                WHERE summary_id = ? ORDER BY step_index
                """,
                (summary_id,),
            ).fetchall()
            if not rows:
                exists = connection.execute(
                    "SELECT id FROM summary_runs WHERE id = ?", (summary_id,)
                ).fetchone()
                if exists is None:
                    raise LibraryError(f"Summary {summary_id} was not found")
            return [
                SummaryStep(
                    index=int(row["step_index"]),
                    kind=str(row["kind"]),
                    input_segment_refs=tuple(
                        cast(list[str], json.loads(row["input_segment_refs_json"]))
                    ),
                    input_step_indexes=tuple(
                        cast(list[int], json.loads(row["input_step_indexes_json"]))
                    ),
                    output_text=str(row["output_text"]),
                    usage=cast(dict[str, int | float], json.loads(row["usage_json"])),
                )
                for row in rows
            ]

    def list_summaries(self, recording_id: int) -> list[SummaryRun]:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            rows = connection.execute(
                """
                SELECT sr.*
                FROM summary_runs AS sr
                JOIN transcript_runs AS tr ON tr.id = sr.transcript_id
                WHERE tr.recording_id = ?
                ORDER BY sr.created_at DESC, sr.id DESC
                """,
                (recording_id,),
            ).fetchall()
            return [self._summary(row) for row in rows]

    def get_latest_successful_summary(self, recording_id: int) -> SummaryRun:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            row = connection.execute(
                """
                SELECT sr.* FROM summary_runs AS sr
                JOIN transcript_runs AS tr ON tr.id = sr.transcript_id
                WHERE tr.recording_id = ? AND sr.status = 'succeeded'
                ORDER BY sr.created_at DESC, sr.id DESC LIMIT 1
                """,
                (recording_id,),
            ).fetchone()
            if row is None:
                raise LibraryError(
                    f"Recording {recording_id} has no successful summary"
                )
            return self._summary(row)

    def record_publication(
        self,
        *,
        recording_id: int,
        transcript_id: int,
        summary_id: int | None,
        provider: str,
        remote_id: str,
        remote_url: str,
        title: str,
        content_hash: str,
        error: str | None = None,
    ) -> Publication:
        timestamp = now_iso()
        status = "failed" if error else "succeeded"
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            transcript_row = connection.execute(
                "SELECT recording_id FROM transcript_runs WHERE id = ?",
                (transcript_id,),
            ).fetchone()
            if (
                transcript_row is None
                or int(transcript_row["recording_id"]) != recording_id
            ):
                raise LibraryError(
                    f"Transcript {transcript_id} does not belong to recording "
                    f"{recording_id}"
                )
            if summary_id is not None:
                summary_row = connection.execute(
                    "SELECT transcript_id FROM summary_runs WHERE id = ?",
                    (summary_id,),
                ).fetchone()
                if (
                    summary_row is None
                    or int(summary_row["transcript_id"]) != transcript_id
                ):
                    raise LibraryError(
                        f"Summary {summary_id} does not belong to transcript "
                        f"{transcript_id}"
                    )
            cursor = connection.execute(
                """
                INSERT INTO publications(
                    recording_id, transcript_id, summary_id, provider,
                    remote_id, remote_url, title, content_hash, status,
                    error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recording_id,
                    transcript_id,
                    summary_id,
                    provider,
                    remote_id,
                    remote_url,
                    title,
                    content_hash,
                    status,
                    error,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            row = connection.execute(
                "SELECT * FROM publications WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            assert row is not None
            return self._publication(row)

    def find_publication_by_content(
        self, provider: str, content_hash: str
    ) -> Publication | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM publications
                WHERE provider = ? AND content_hash = ? AND status = 'succeeded'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (provider, content_hash),
            ).fetchone()
            return None if row is None else self._publication(row)

    def get_latest_publication(
        self, recording_id: int, *, provider: str
    ) -> Publication:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            row = connection.execute(
                """
                SELECT * FROM publications
                WHERE recording_id = ? AND provider = ? AND status = 'succeeded'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (recording_id, provider),
            ).fetchone()
            if row is None:
                raise LibraryError(
                    f"Recording {recording_id} has no {provider} publication"
                )
            return self._publication(row)

    def list_publications(self, recording_id: int) -> list[Publication]:
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            rows = connection.execute(
                """
                SELECT * FROM publications WHERE recording_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (recording_id,),
            ).fetchall()
            return [self._publication(row) for row in rows]

    def record_rendered_output(
        self,
        *,
        recording_id: int,
        transcript_id: int | None,
        summary_id: int | None,
        kind: str,
        format: str,
        path: Path,
        content_hash: str,
        replace: bool = False,
    ) -> RenderedOutput:
        timestamp = now_iso()
        resolved_path = path.expanduser().resolve()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM rendered_outputs WHERE path = ?", (str(resolved_path),)
            ).fetchone()
            if existing is not None:
                if (
                    existing["transcript_id"] == transcript_id
                    and existing["summary_id"] == summary_id
                    and existing["content_hash"] == content_hash
                ):
                    return self._rendered_output(existing)
                if replace:
                    connection.execute(
                        """
                        UPDATE rendered_outputs
                        SET recording_id = ?, transcript_id = ?, summary_id = ?,
                            kind = ?, format = ?, content_hash = ?, created_at = ?
                        WHERE id = ?
                        """,
                        (
                            recording_id,
                            transcript_id,
                            summary_id,
                            kind,
                            format,
                            content_hash,
                            timestamp,
                            int(existing["id"]),
                        ),
                    )
                    updated = connection.execute(
                        "SELECT * FROM rendered_outputs WHERE id = ?",
                        (int(existing["id"]),),
                    ).fetchone()
                    assert updated is not None
                    return self._rendered_output(updated)
                raise LibraryError(f"Output path is already recorded: {resolved_path}")
            cursor = connection.execute(
                """
                INSERT INTO rendered_outputs(
                    recording_id, transcript_id, summary_id, kind, format,
                    path, content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recording_id,
                    transcript_id,
                    summary_id,
                    kind,
                    format,
                    str(resolved_path),
                    content_hash,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            row = connection.execute(
                "SELECT * FROM rendered_outputs WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            assert row is not None
            return self._rendered_output(row)

    def find_rendered_transcript(self, transcript_id: int) -> RenderedOutput | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM rendered_outputs
                WHERE transcript_id = ? AND kind = 'transcript'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (transcript_id,),
            ).fetchone()
            return None if row is None else self._rendered_output(row)

    def mark_source_trashed(self, recording_id: int, original_path: Path) -> None:
        timestamp = now_iso()
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            connection.execute(
                """
                UPDATE recordings
                SET current_path = NULL, trashed_at = ?, trash_original_path = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, str(original_path), timestamp, recording_id),
            )

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        include_deleted: bool = False,
        limit: int = 20,
    ) -> list[SearchHit]:
        if kind not in (None, "transcript", "summary"):
            raise ValueError("kind must be transcript or summary")
        if limit < 1:
            raise ValueError("limit must be positive")
        fts_query = self._fts_query(query)
        conditions = ["search_index MATCH ?"]
        parameters: list[Any] = [fts_query]
        if kind is not None:
            conditions.append("search_index.kind = ?")
            parameters.append(kind)
        if not include_deleted:
            conditions.append("recordings.deleted_at IS NULL")
        parameters.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    search_index.kind,
                    CAST(search_index.recording_id AS INTEGER) AS recording_id,
                    CAST(search_index.artifact_id AS INTEGER) AS artifact_id,
                    search_index.location,
                    search_index.title,
                    snippet(search_index, 5, '[', ']', ' … ', 18) AS snippet,
                    bm25(search_index, 0.0, 0.0, 0.0, 0.0, 2.0, 1.0) AS rank,
                    coalesce(recordings.current_path, recordings.original_path)
                        AS recording_path,
                    CASE WHEN search_index.kind = 'transcript' THEN (
                        SELECT segment.start_ms
                        FROM transcript_segments AS segment
                        WHERE segment.transcript_id =
                            CAST(search_index.artifact_id AS INTEGER)
                          AND segment.stable_ref = search_index.location
                    ) END AS start_ms
                FROM search_index
                JOIN recordings
                  ON recordings.id = CAST(search_index.recording_id AS INTEGER)
                WHERE {" AND ".join(conditions)}
                ORDER BY rank, recording_id, artifact_id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            return [
                SearchHit(
                    kind=str(row["kind"]),
                    recording_id=int(row["recording_id"]),
                    artifact_id=int(row["artifact_id"]),
                    location=str(row["location"]),
                    title=str(row["title"]),
                    snippet=str(row["snippet"]),
                    rank=float(row["rank"]),
                    recording_path=Path(row["recording_path"]),
                    start_ms=(
                        None if row["start_ms"] is None else int(row["start_ms"])
                    ),
                )
                for row in rows
            ]

    def forget(self, recording_id: int) -> bool:
        timestamp = now_iso()
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            cursor = connection.execute(
                """
                UPDATE recordings
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (timestamp, timestamp, recording_id),
            )
            return cursor.rowcount > 0

    def restore(self, recording_id: int) -> bool:
        timestamp = now_iso()
        with self.database.connect() as connection:
            self._require_recording(connection, recording_id)
            cursor = connection.execute(
                """
                UPDATE recordings
                SET deleted_at = NULL, updated_at = ?
                WHERE id = ? AND deleted_at IS NOT NULL
                """,
                (timestamp, recording_id),
            )
            return cursor.rowcount > 0

    def stats(self) -> LibraryStats:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    count(*) AS recordings,
                    count(*) FILTER (WHERE deleted_at IS NOT NULL)
                        AS deleted_recordings,
                    (SELECT count(*) FROM transcript_runs) AS transcripts,
                    (SELECT count(*) FROM summary_runs) AS summaries
                FROM recordings
                """
            ).fetchone()
            assert row is not None
            return LibraryStats(
                recordings=int(row["recordings"]),
                deleted_recordings=int(row["deleted_recordings"]),
                transcripts=int(row["transcripts"]),
                summaries=int(row["summaries"]),
            )

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not tokens:
            raise ValueError("search query must contain a word or number")
        return " AND ".join(
            f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens
        )

    @staticmethod
    def _validate_segments(segments: list[Segment]) -> None:
        for expected_index, segment in enumerate(segments):
            if segment.index != expected_index:
                raise ValueError("segment indexes must be contiguous and start at zero")
            if segment.start_ms < 0 or segment.end_ms < segment.start_ms:
                raise ValueError(f"invalid timestamps for segment {segment.index}")
            if not segment.text.strip():
                raise ValueError(f"segment {segment.index} has no text")

    @staticmethod
    def _validate_turns(turns: list[SpeakerTurn]) -> None:
        for expected_index, turn in enumerate(turns):
            if turn.index != expected_index:
                raise ValueError(
                    "speaker turn indexes must be contiguous and start at zero"
                )
            if turn.start_ms < 0 or turn.end_ms < turn.start_ms:
                raise ValueError(f"invalid timestamps for speaker turn {turn.index}")
            if not turn.speaker.strip() or not turn.source_speaker.strip():
                raise ValueError(f"speaker turn {turn.index} has no speaker")
            if turn.confidence is not None and not 0 <= turn.confidence <= 1:
                raise ValueError(f"invalid confidence for speaker turn {turn.index}")

    @staticmethod
    def _validate_diarization_assignments(
        connection: sqlite3.Connection,
        *,
        recording_id: int,
        transcript_id: int,
        assignments: list[SpeakerAssignment],
    ) -> None:
        transcript = connection.execute(
            "SELECT recording_id FROM transcript_runs WHERE id = ?",
            (transcript_id,),
        ).fetchone()
        if transcript is None or int(transcript["recording_id"]) != recording_id:
            raise LibraryError(
                f"Transcript {transcript_id} does not belong to recording "
                f"{recording_id}"
            )
        segment_rows = connection.execute(
            """
            SELECT segment_index, stable_ref FROM transcript_segments
            WHERE transcript_id = ? ORDER BY segment_index
            """,
            (transcript_id,),
        ).fetchall()
        if len(assignments) != len(segment_rows):
            raise ValueError("speaker assignments must cover every transcript segment")
        for assignment, segment in zip(assignments, segment_rows, strict=True):
            if assignment.segment_index != int(
                segment["segment_index"]
            ) or assignment.stable_ref != str(segment["stable_ref"]):
                raise ValueError(
                    "speaker assignments must match transcript segments in order"
                )
            if assignment.status not in {"assigned", "mixed", "unassigned"}:
                raise ValueError(
                    f"invalid speaker assignment status {assignment.status}"
                )
            if assignment.overlap_ms < 0 or not 0 <= assignment.confidence <= 1:
                raise ValueError(
                    f"invalid speaker assignment for {assignment.stable_ref}"
                )

    @staticmethod
    def _insert_diarization_assignments(
        connection: sqlite3.Connection,
        *,
        diarization_id: int,
        transcript_id: int,
        assignments: list[SpeakerAssignment],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO diarization_assignments(
                diarization_id, transcript_id, segment_index, stable_ref,
                speaker, overlap_ms, confidence, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    diarization_id,
                    transcript_id,
                    assignment.segment_index,
                    assignment.stable_ref,
                    assignment.speaker,
                    assignment.overlap_ms,
                    assignment.confidence,
                    assignment.status,
                )
                for assignment in assignments
            ],
        )

    @staticmethod
    def _require_recording(connection: sqlite3.Connection, recording_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"Recording {recording_id} was not found")

    @staticmethod
    def _recording(row: sqlite3.Row) -> Recording:
        return Recording(
            id=int(row["id"]),
            fingerprint=str(row["fingerprint"]),
            original_path=Path(row["original_path"]),
            current_path=(
                None if row["current_path"] is None else Path(row["current_path"])
            ),
            file_size_bytes=int(row["file_size_bytes"]),
            duration_ms=None if row["duration_ms"] is None else int(row["duration_ms"]),
            language=None if row["language"] is None else str(row["language"]),
            created_at=str(row["created_at"]),
            deleted_at=None if row["deleted_at"] is None else str(row["deleted_at"]),
        )

    @staticmethod
    def _transcript(row: sqlite3.Row) -> TranscriptRun:
        return TranscriptRun(
            id=int(row["id"]),
            recording_id=int(row["recording_id"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            status=str(row["status"]),
            language=None if row["language"] is None else str(row["language"]),
            is_preferred=bool(row["is_preferred"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _diarization(row: sqlite3.Row) -> DiarizationRun:
        return DiarizationRun(
            id=int(row["id"]),
            recording_id=int(row["recording_id"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            status=str(row["status"]),
            is_preferred=bool(row["is_preferred"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _prompt(row: sqlite3.Row) -> PromptTemplate:
        return PromptTemplate(
            id=int(row["id"]),
            name=str(row["name"]),
            version=int(row["version"]),
            instructions=str(row["instructions"]),
            is_builtin=bool(row["is_builtin"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _summary(row: sqlite3.Row) -> SummaryRun:
        return SummaryRun(
            id=int(row["id"]),
            transcript_id=int(row["transcript_id"]),
            prompt_name=str(row["prompt_name"]),
            prompt_version=int(row["prompt_version"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _rendered_output(row: sqlite3.Row) -> RenderedOutput:
        return RenderedOutput(
            id=int(row["id"]),
            recording_id=int(row["recording_id"]),
            transcript_id=(
                None if row["transcript_id"] is None else int(row["transcript_id"])
            ),
            summary_id=None if row["summary_id"] is None else int(row["summary_id"]),
            kind=str(row["kind"]),
            format=str(row["format"]),
            path=Path(row["path"]),
            content_hash=str(row["content_hash"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _publication(row: sqlite3.Row) -> Publication:
        return Publication(
            id=int(row["id"]),
            recording_id=int(row["recording_id"]),
            transcript_id=int(row["transcript_id"]),
            summary_id=None if row["summary_id"] is None else int(row["summary_id"]),
            provider=str(row["provider"]),
            remote_id=str(row["remote_id"]),
            remote_url=str(row["remote_url"]),
            title=str(row["title"]),
            content_hash=str(row["content_hash"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
        )
