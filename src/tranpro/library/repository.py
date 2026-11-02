"""Repository API for recordings and their versioned derived artifacts."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tranpro.library.database import Database
from tranpro.library.fingerprint import fingerprint_file
from tranpro.library.models import (
    LibraryStats,
    Recording,
    SearchHit,
    Segment,
    SummaryRun,
    SummarySection,
    TranscriptRun,
)


class LibraryError(RuntimeError):
    """Base exception for transcript library operations."""


class RecordNotFoundError(LibraryError):
    """Raised when a requested recording does not exist."""


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
                return self._recording(existing), False

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

    def add_summary(
        self,
        transcript_id: int,
        *,
        provider: str,
        model: str,
        sections: Iterable[SummarySection],
        prompt_name: str = "detailed-notes",
        prompt_version: int = 1,
        prompt_instructions: str = "Create detailed notes.",
        system_contract: str = "Return grounded structured notes.",
    ) -> int:
        """Atomically add one successful, immutable summary run."""

        timestamp = now_iso()
        materialized_sections = list(sections)
        if not materialized_sections:
            raise ValueError("a successful summary requires at least one section")
        if any(not section.body.strip() for section in materialized_sections):
            raise ValueError("summary sections must contain body text")
        with self.database.connect() as connection:
            transcript = connection.execute(
                "SELECT id FROM transcript_runs WHERE id = ?", (transcript_id,)
            ).fetchone()
            if transcript is None:
                raise LibraryError(f"Transcript {transcript_id} was not found")
            cursor = connection.execute(
                """
                INSERT INTO summary_runs(
                    transcript_id, prompt_name, prompt_version,
                    prompt_instructions, system_contract, provider, model,
                    status, started_at, completed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'succeeded', ?, ?, ?)
                """,
                (
                    transcript_id,
                    prompt_name,
                    prompt_version,
                    prompt_instructions,
                    system_contract,
                    provider,
                    model,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            assert cursor.lastrowid is not None
            summary_id = int(cursor.lastrowid)
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
                        section.heading,
                        section.body,
                        self._canonical_json(section.segment_refs),
                    )
                    for index, section in enumerate(materialized_sections)
                ],
            )
            return summary_id

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
        if not segments:
            raise ValueError("a successful transcript requires at least one segment")
        for expected_index, segment in enumerate(segments):
            if segment.index != expected_index:
                raise ValueError("segment indexes must be contiguous and start at zero")
            if segment.start_ms < 0 or segment.end_ms < segment.start_ms:
                raise ValueError(f"invalid timestamps for segment {segment.index}")
            if not segment.text.strip():
                raise ValueError(f"segment {segment.index} has no text")

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
