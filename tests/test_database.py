import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tranpro.library.database import Database, DatabaseError
from tranpro.library.schema import APPLICATION_ID, LATEST_SCHEMA_VERSION
from tranpro.paths import AppPaths


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")


def test_initialize_creates_current_strict_schema(app_paths: AppPaths) -> None:
    database = Database(app_paths)

    version = database.initialize()

    with sqlite3.connect(app_paths.database_file) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        application_id = connection.execute("PRAGMA application_id").fetchone()
        user_version = connection.execute("PRAGMA user_version").fetchone()

    assert version == LATEST_SCHEMA_VERSION
    assert application_id == (APPLICATION_ID,)
    assert user_version == (LATEST_SCHEMA_VERSION,)
    assert {
        "recordings",
        "transcript_runs",
        "transcript_segments",
        "summary_runs",
        "summary_sections",
        "search_index",
    } <= tables


def test_existing_database_is_backed_up_before_migration(app_paths: AppPaths) -> None:
    app_paths.data_dir.mkdir(parents=True)
    with sqlite3.connect(app_paths.database_file) as connection:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("CREATE TABLE legacy_marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserved')")

    fixed_time = datetime(2026, 11, 2, 3, 4, 5, 6789, tzinfo=UTC)
    Database(app_paths, clock=lambda: fixed_time).initialize()

    backups = list(app_paths.backup_dir.glob("*.sqlite3"))
    assert [path.name for path in backups] == [
        "library-20261102T030405006789Z-v0.sqlite3"
    ]
    with sqlite3.connect(backups[0]) as backup:
        value = backup.execute("SELECT value FROM legacy_marker").fetchone()
        assert value == ("preserved",)


def test_initialize_refuses_database_from_another_application(
    app_paths: AppPaths,
) -> None:
    app_paths.data_dir.mkdir(parents=True)
    with sqlite3.connect(app_paths.database_file) as connection:
        connection.execute("PRAGMA application_id = 12345")

    with pytest.raises(DatabaseError, match="non-tranpro"):
        Database(app_paths).initialize()


def test_initialize_refuses_unmarked_database_with_existing_tables(
    app_paths: AppPaths,
) -> None:
    app_paths.data_dir.mkdir(parents=True)
    with sqlite3.connect(app_paths.database_file) as connection:
        connection.execute("CREATE TABLE someone_elses_data(value TEXT)")

    with pytest.raises(DatabaseError, match="unrecognized SQLite database"):
        Database(app_paths).initialize()


def test_initialize_refuses_newer_schema(app_paths: AppPaths) -> None:
    app_paths.data_dir.mkdir(parents=True)
    with sqlite3.connect(app_paths.database_file) as connection:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}")

    with pytest.raises(DatabaseError, match="newer than this tranpro version"):
        Database(app_paths).initialize()


def test_initialize_wraps_application_directory_errors(tmp_path: Path) -> None:
    file_instead_of_directory = tmp_path / "occupied"
    file_instead_of_directory.write_text("not a directory", encoding="utf-8")
    paths = AppPaths(
        data_dir=file_instead_of_directory / "data",
        cache_dir=tmp_path / "cache",
    )

    with pytest.raises(DatabaseError, match="Could not prepare application directory"):
        Database(paths).initialize()
