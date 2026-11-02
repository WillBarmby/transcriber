"""SQLite connection, migration, and backup management."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from tranpro.library.schema import APPLICATION_ID, LATEST_SCHEMA_VERSION, MIGRATIONS
from tranpro.paths import AppPaths


class DatabaseError(RuntimeError):
    """Raised when the transcript library cannot be opened safely."""


def utc_now() -> datetime:
    return datetime.now(UTC)


class Database:
    """Own the lifecycle of the user's embedded transcript library."""

    def __init__(
        self,
        paths: AppPaths | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.paths = paths or AppPaths.for_user()
        self._clock = clock

    def initialize(self) -> int:
        """Create or migrate the database and return its schema version."""

        try:
            self.paths.create_private_directories()
        except OSError as error:
            message = (
                f"Could not prepare application directory "
                f"{self.paths.data_dir}: {error}"
            )
            raise DatabaseError(message) from error
        existed = self.paths.database_file.exists()
        connection = self._open()
        try:
            current_version = self._schema_version(connection)
            self._validate_migration_target(connection)
            if current_version > LATEST_SCHEMA_VERSION:
                raise DatabaseError(
                    "Library schema is newer than this tranpro version "
                    f"({current_version} > {LATEST_SCHEMA_VERSION})"
                )
            if current_version == LATEST_SCHEMA_VERSION:
                self._validate_application_id(connection)
                return current_version

            if existed and self.paths.database_file.stat().st_size > 0:
                self._backup(connection, current_version)

            for version in range(current_version + 1, LATEST_SCHEMA_VERSION + 1):
                self._apply_migration(connection, version)
            return LATEST_SCHEMA_VERSION
        finally:
            connection.close()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection to an initialized library."""

        self.initialize()
        connection = self._open()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _open(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.paths.database_file, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except sqlite3.Error as error:
            if connection is not None:
                connection.close()
            raise DatabaseError(
                f"Could not open transcript library {self.paths.database_file}: {error}"
            ) from error

    def _schema_version(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("PRAGMA user_version").fetchone()
        assert row is not None
        return int(row[0])

    def _validate_application_id(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("PRAGMA application_id").fetchone()
        assert row is not None
        if int(row[0]) != APPLICATION_ID:
            raise DatabaseError(
                f"Refusing unexpected SQLite database at {self.paths.database_file}"
            )

    def _validate_migration_target(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("PRAGMA application_id").fetchone()
        assert row is not None
        application_id = int(row[0])
        if application_id not in (0, APPLICATION_ID):
            raise DatabaseError(
                f"Refusing non-tranpro SQLite database at {self.paths.database_file}"
            )
        if application_id == 0:
            user_tables = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                LIMIT 1
                """
            ).fetchone()
            if user_tables is not None:
                raise DatabaseError(
                    "Refusing unrecognized SQLite database without a tranpro marker "
                    f"at {self.paths.database_file}"
                )

    def _backup(self, connection: sqlite3.Connection, version: int) -> Path:
        timestamp = self._clock().astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = self.paths.backup_dir / (
            f"library-{timestamp}-v{version}.sqlite3"
        )
        backup_connection = sqlite3.connect(backup_path)
        try:
            connection.backup(backup_connection)
        finally:
            backup_connection.close()
        return backup_path

    def _apply_migration(self, connection: sqlite3.Connection, version: int) -> None:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise DatabaseError(f"Missing database migration {version}")
        applied_at = self._clock().astimezone(UTC).isoformat()
        escaped_applied_at = applied_at.replace("'", "''")
        script = f"""
            BEGIN IMMEDIATE;
            {migration}
            INSERT INTO schema_migrations(version, applied_at)
            VALUES ({version}, '{escaped_applied_at}');
            PRAGMA application_id = {APPLICATION_ID};
            PRAGMA user_version = {version};
            COMMIT;
        """
        try:
            connection.executescript(script)
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.rollback()
            raise DatabaseError(
                f"Database migration {version} failed: {error}"
            ) from error
