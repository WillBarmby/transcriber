# Transcript library

tranpro uses one application-owned SQLite database as the canonical record of
processing history. The source audio remains an external file; the database
stores its path, metadata, and a streaming SHA-256 content fingerprint.

## Identity and versions

```text
recordings
├── transcript_runs
│   ├── transcript_segments
│   └── summary_runs
│       ├── summary_steps
│       └── summary_sections
└── publication records (planned)
```

A recording is identified by audio content rather than filename. Registering the
same bytes at another path returns the existing recording. A different provider,
model, or explicit retranscription creates another transcript run instead of
overwriting an earlier result.

Transcript segments receive stable references such as `s000001`. Summary
sections preserve the segment references used as evidence, allowing renderers to
add grounded timestamps later without asking a language model to invent them.

Summary runs freeze the exact prompt instructions, provider, model, settings,
and context plan used. Multi-pass summaries append their intermediate source and
synthesis steps before the final sections are sealed. Failed runs retain those
steps for diagnosis; completed and failed runs cannot be edited back into a new
result.

## Prompts

`tp prompt list` shows the latest version of each reusable prompt. The built-in
`detailed-notes` prompt asks for an overview, key arguments, key terms, new
concepts, and sources cited or mentioned. User prompts are append-only versions:

```shell
tp prompt save lecture-notes --file prompt.md
tp prompt show lecture-notes
tp prompt list --all
```

Saving the same name again creates `lecture-notes@2`; it does not change runs
that used `lecture-notes@1`.

## Schema changes and backups

The SQLite `user_version` pragma records the current ordered migration. Before
tranpro modifies an existing older schema, it creates a consistent backup using
SQLite's online backup API:

```text
~/Library/Application Support/tranpro/backups/
└── library-20261102T030405006789Z-v0.sqlite3
```

The database carries a tranpro application identifier. Migration refuses a file
marked as another application's database, an unmarked database containing
unknown tables, or a schema newer than the installed tranpro version. These
checks turn likely path mistakes and downgrade attempts into explicit errors.

## Search

SQLite FTS5 indexes transcript segment text, speaker names, summary headings, and
summary bodies. Search results retain the recording, artifact version, stable
segment or section location, and transcript start time. Normal search excludes
soft-deleted recordings; `--all` includes them.

FTS is intentionally lexical in this milestone. The future semantic index will
be derived from versioned transcript passages and combined with FTS results; it
will not replace canonical transcript storage.

## Deletion semantics

`tp forget ID` timestamps the recording as deleted. It does not remove database
rows or touch source and output files. `tp restore ID` reverses that state. A
future permanent-purge operation will be separate, explicit, and confirmed.

The later `--trash-source` transcription option will use the operating-system
Trash only after all requested outputs succeed. That is independent of forgetting
a library record.
