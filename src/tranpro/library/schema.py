"""Ordered SQLite schema migrations."""

APPLICATION_ID = 0x5450524F  # ASCII: TPRO

MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        ) STRICT;

        CREATE TABLE recordings (
            id INTEGER PRIMARY KEY,
            fingerprint TEXT NOT NULL UNIQUE,
            original_path TEXT NOT NULL,
            current_path TEXT,
            file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
            file_mtime_ns INTEGER,
            duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
            language TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            trashed_at TEXT,
            trash_original_path TEXT
        ) STRICT;

        CREATE INDEX recordings_created_at_idx
            ON recordings(created_at DESC);
        CREATE INDEX recordings_deleted_at_idx
            ON recordings(deleted_at);

        CREATE TABLE transcript_runs (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            settings_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            language TEXT,
            is_preferred INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0, 1)),
            started_at TEXT,
            completed_at TEXT,
            error TEXT,
            created_at TEXT NOT NULL
        ) STRICT;

        CREATE INDEX transcript_runs_recording_idx
            ON transcript_runs(recording_id, created_at DESC);
        CREATE UNIQUE INDEX transcript_runs_one_preferred_idx
            ON transcript_runs(recording_id)
            WHERE is_preferred = 1;

        CREATE TABLE transcript_segments (
            id INTEGER PRIMARY KEY,
            transcript_id INTEGER NOT NULL
                REFERENCES transcript_runs(id) ON DELETE CASCADE,
            segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
            stable_ref TEXT NOT NULL,
            speaker TEXT,
            start_ms INTEGER NOT NULL CHECK (start_ms >= 0),
            end_ms INTEGER NOT NULL CHECK (end_ms >= start_ms),
            text TEXT NOT NULL CHECK (length(trim(text)) > 0),
            UNIQUE (transcript_id, segment_index),
            UNIQUE (transcript_id, stable_ref)
        ) STRICT;

        CREATE INDEX transcript_segments_timeline_idx
            ON transcript_segments(transcript_id, start_ms);

        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version >= 1),
            instructions TEXT NOT NULL,
            is_builtin INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0, 1)),
            created_at TEXT NOT NULL,
            UNIQUE (name, version)
        ) STRICT;

        CREATE TABLE summary_runs (
            id INTEGER PRIMARY KEY,
            transcript_id INTEGER NOT NULL
                REFERENCES transcript_runs(id) ON DELETE CASCADE,
            prompt_id INTEGER REFERENCES prompts(id) ON DELETE SET NULL,
            prompt_name TEXT NOT NULL,
            prompt_version INTEGER NOT NULL CHECK (prompt_version >= 1),
            prompt_instructions TEXT NOT NULL,
            system_contract TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            settings_json TEXT NOT NULL DEFAULT '{}',
            context_plan_json TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            started_at TEXT,
            completed_at TEXT,
            error TEXT,
            created_at TEXT NOT NULL
        ) STRICT;

        CREATE INDEX summary_runs_transcript_idx
            ON summary_runs(transcript_id, created_at DESC);

        CREATE TABLE summary_sections (
            id INTEGER PRIMARY KEY,
            summary_id INTEGER NOT NULL REFERENCES summary_runs(id) ON DELETE CASCADE,
            section_index INTEGER NOT NULL CHECK (section_index >= 0),
            heading TEXT NOT NULL,
            body TEXT NOT NULL CHECK (length(trim(body)) > 0),
            segment_refs_json TEXT NOT NULL DEFAULT '[]',
            UNIQUE (summary_id, section_index)
        ) STRICT;

        CREATE VIRTUAL TABLE search_index USING fts5(
            kind UNINDEXED,
            recording_id UNINDEXED,
            artifact_id UNINDEXED,
            location UNINDEXED,
            title,
            body,
            tokenize = 'unicode61 remove_diacritics 2'
        );

        CREATE TRIGGER transcript_segments_search_insert
        AFTER INSERT ON transcript_segments
        BEGIN
            INSERT INTO search_index(
                kind, recording_id, artifact_id, location, title, body
            )
            SELECT
                'transcript', tr.recording_id, NEW.transcript_id,
                NEW.stable_ref, coalesce(NEW.speaker, ''), NEW.text
            FROM transcript_runs AS tr
            WHERE tr.id = NEW.transcript_id;
        END;

        CREATE TRIGGER transcript_segments_search_delete
        AFTER DELETE ON transcript_segments
        BEGIN
            DELETE FROM search_index
            WHERE kind = 'transcript'
              AND artifact_id = OLD.transcript_id
              AND location = OLD.stable_ref;
        END;

        CREATE TRIGGER transcript_segments_search_update
        AFTER UPDATE ON transcript_segments
        BEGIN
            DELETE FROM search_index
            WHERE kind = 'transcript'
              AND artifact_id = OLD.transcript_id
              AND location = OLD.stable_ref;
            INSERT INTO search_index(
                kind, recording_id, artifact_id, location, title, body
            )
            SELECT
                'transcript', tr.recording_id, NEW.transcript_id,
                NEW.stable_ref, coalesce(NEW.speaker, ''), NEW.text
            FROM transcript_runs AS tr
            WHERE tr.id = NEW.transcript_id;
        END;

        CREATE TRIGGER summary_sections_search_insert
        AFTER INSERT ON summary_sections
        BEGIN
            INSERT INTO search_index(
                kind, recording_id, artifact_id, location, title, body
            )
            SELECT
                'summary', tr.recording_id, NEW.summary_id,
                printf('section-%04d', NEW.section_index + 1), NEW.heading, NEW.body
            FROM summary_runs AS sr
            JOIN transcript_runs AS tr ON tr.id = sr.transcript_id
            WHERE sr.id = NEW.summary_id;
        END;

        CREATE TRIGGER summary_sections_search_delete
        AFTER DELETE ON summary_sections
        BEGIN
            DELETE FROM search_index
            WHERE kind = 'summary'
              AND artifact_id = OLD.summary_id
              AND location = printf('section-%04d', OLD.section_index + 1);
        END;

        CREATE TRIGGER summary_sections_search_update
        AFTER UPDATE ON summary_sections
        BEGIN
            DELETE FROM search_index
            WHERE kind = 'summary'
              AND artifact_id = OLD.summary_id
              AND location = printf('section-%04d', OLD.section_index + 1);
            INSERT INTO search_index(
                kind, recording_id, artifact_id, location, title, body
            )
            SELECT
                'summary', tr.recording_id, NEW.summary_id,
                printf('section-%04d', NEW.section_index + 1), NEW.heading, NEW.body
            FROM summary_runs AS sr
            JOIN transcript_runs AS tr ON tr.id = sr.transcript_id
            WHERE sr.id = NEW.summary_id;
        END;
    """,
    2: """
        CREATE TABLE rendered_outputs (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
            transcript_id INTEGER REFERENCES transcript_runs(id) ON DELETE CASCADE,
            summary_id INTEGER REFERENCES summary_runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('transcript', 'summary', 'collated')),
            format TEXT NOT NULL,
            path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (transcript_id IS NOT NULL OR summary_id IS NOT NULL),
            UNIQUE (path)
        ) STRICT;

        CREATE INDEX rendered_outputs_recording_idx
            ON rendered_outputs(recording_id, created_at DESC);
        CREATE INDEX rendered_outputs_transcript_idx
            ON rendered_outputs(transcript_id, created_at DESC);
    """,
    3: """
        INSERT INTO prompts(name, version, instructions, is_builtin, created_at)
        VALUES (
            'detailed-notes',
            1,
            'Create faithful, detailed notes organized by topic. Include a ' ||
            'concise overview, key arguments and supporting details, key terms, ' ||
            'new concepts introduced, and sources cited or mentioned. Distinguish ' ||
            'claims made in the recording from verified facts. Ground every ' ||
            'section in the supplied transcript segment references and do not ' ||
            'invent citations.',
            1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        )
        ON CONFLICT(name, version) DO NOTHING;

        CREATE TABLE summary_steps (
            id INTEGER PRIMARY KEY,
            summary_id INTEGER NOT NULL
                REFERENCES summary_runs(id) ON DELETE CASCADE,
            step_index INTEGER NOT NULL CHECK (step_index >= 0),
            kind TEXT NOT NULL CHECK (kind IN ('source', 'synthesis')),
            input_segment_refs_json TEXT NOT NULL DEFAULT '[]',
            input_step_indexes_json TEXT NOT NULL DEFAULT '[]',
            output_text TEXT NOT NULL,
            usage_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE (summary_id, step_index)
        ) STRICT;

        CREATE INDEX summary_steps_summary_idx
            ON summary_steps(summary_id, step_index);
    """,
    4: """
        CREATE TABLE publications (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER NOT NULL
                REFERENCES recordings(id) ON DELETE CASCADE,
            transcript_id INTEGER NOT NULL
                REFERENCES transcript_runs(id) ON DELETE CASCADE,
            summary_id INTEGER REFERENCES summary_runs(id) ON DELETE SET NULL,
            provider TEXT NOT NULL,
            remote_id TEXT NOT NULL,
            remote_url TEXT NOT NULL,
            title TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
            error TEXT,
            created_at TEXT NOT NULL
        ) STRICT;

        CREATE INDEX publications_recording_idx
            ON publications(recording_id, created_at DESC);
        CREATE INDEX publications_remote_idx
            ON publications(provider, remote_id, created_at DESC);
        CREATE INDEX publications_content_idx
            ON publications(provider, content_hash, created_at DESC);
    """,
    5: """
        CREATE TABLE diarization_runs (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER NOT NULL
                REFERENCES recordings(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            settings_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL
                CHECK (status IN ('running', 'succeeded', 'failed')),
            is_preferred INTEGER NOT NULL DEFAULT 0
                CHECK (is_preferred IN (0, 1)),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            error TEXT,
            created_at TEXT NOT NULL
        ) STRICT;

        CREATE INDEX diarization_runs_recording_idx
            ON diarization_runs(recording_id, created_at DESC);
        CREATE UNIQUE INDEX diarization_runs_one_preferred_idx
            ON diarization_runs(recording_id)
            WHERE is_preferred = 1;

        CREATE TABLE speaker_turns (
            id INTEGER PRIMARY KEY,
            diarization_id INTEGER NOT NULL
                REFERENCES diarization_runs(id) ON DELETE CASCADE,
            turn_index INTEGER NOT NULL CHECK (turn_index >= 0),
            source_speaker TEXT NOT NULL,
            speaker TEXT NOT NULL,
            start_ms INTEGER NOT NULL CHECK (start_ms >= 0),
            end_ms INTEGER NOT NULL CHECK (end_ms >= start_ms),
            confidence REAL CHECK (
                confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
            ),
            UNIQUE (diarization_id, turn_index)
        ) STRICT;

        CREATE INDEX speaker_turns_timeline_idx
            ON speaker_turns(diarization_id, start_ms, end_ms);

        CREATE TABLE diarization_assignments (
            id INTEGER PRIMARY KEY,
            diarization_id INTEGER NOT NULL
                REFERENCES diarization_runs(id) ON DELETE CASCADE,
            transcript_id INTEGER NOT NULL
                REFERENCES transcript_runs(id) ON DELETE CASCADE,
            segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
            stable_ref TEXT NOT NULL,
            speaker TEXT,
            overlap_ms INTEGER NOT NULL CHECK (overlap_ms >= 0),
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            status TEXT NOT NULL
                CHECK (status IN ('assigned', 'mixed', 'unassigned')),
            UNIQUE (diarization_id, transcript_id, segment_index),
            UNIQUE (diarization_id, transcript_id, stable_ref)
        ) STRICT;

        CREATE INDEX diarization_assignments_transcript_idx
            ON diarization_assignments(transcript_id, diarization_id);
    """,
    6: """
        ALTER TABLE summary_runs ADD COLUMN diarization_id INTEGER
            REFERENCES diarization_runs(id) ON DELETE SET NULL;
        CREATE INDEX summary_runs_diarization_idx
            ON summary_runs(diarization_id, created_at DESC);

        ALTER TABLE publications ADD COLUMN diarization_id INTEGER
            REFERENCES diarization_runs(id) ON DELETE SET NULL;
        CREATE INDEX publications_diarization_idx
            ON publications(diarization_id, created_at DESC);

        ALTER TABLE rendered_outputs RENAME TO rendered_outputs_old;

        CREATE TABLE rendered_outputs (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER NOT NULL
                REFERENCES recordings(id) ON DELETE CASCADE,
            transcript_id INTEGER REFERENCES transcript_runs(id) ON DELETE CASCADE,
            summary_id INTEGER REFERENCES summary_runs(id) ON DELETE CASCADE,
            diarization_id INTEGER
                REFERENCES diarization_runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL
                CHECK (kind IN ('transcript', 'diarized', 'summary', 'collated')),
            format TEXT NOT NULL,
            path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (
                transcript_id IS NOT NULL OR summary_id IS NOT NULL
                OR diarization_id IS NOT NULL
            ),
            UNIQUE (path)
        ) STRICT;

        INSERT INTO rendered_outputs(
            id, recording_id, transcript_id, summary_id, diarization_id,
            kind, format, path, content_hash, created_at
        )
        SELECT
            id, recording_id, transcript_id, summary_id, NULL,
            kind, format, path, content_hash, created_at
        FROM rendered_outputs_old;

        DROP TABLE rendered_outputs_old;

        CREATE INDEX rendered_outputs_recording_idx
            ON rendered_outputs(recording_id, created_at DESC);
        CREATE INDEX rendered_outputs_transcript_idx
            ON rendered_outputs(transcript_id, created_at DESC);
        CREATE INDEX rendered_outputs_diarization_idx
            ON rendered_outputs(diarization_id, created_at DESC);
    """,
}

LATEST_SCHEMA_VERSION = max(MIGRATIONS)
