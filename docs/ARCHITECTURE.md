# Architecture

## Product boundary

tranpro is a local command-line application and library, not a hosted service.
It owns metadata, transcripts, summaries, prompts, and publication records in an
embedded SQLite database. Audio stays outside the database and is identified by
a streaming content fingerprint.

SQLite is canonical. Markdown files and Google Docs are projections that can be
recreated from stored artifacts.

## Dependency direction

The finished backend will follow these boundaries:

```text
CLI -> application workflows -> domain models
                    |                 ^
                    v                 |
        provider/repository ports ----+
                    ^
                    |
       SQLite, Parakeet, Ollama, OpenAI, Google adapters
```

- **Domain models** describe recordings, timestamped transcript segments,
  transcript runs, prompt versions, summaries, and publications. They do not
  import a model SDK, Typer, or SQLite.
- **Application workflows** implement use cases such as transcribe, summarize,
  search, publish, forget, and restore.
- **Ports** define the capabilities workflows need: transcription,
  summarization, persistence, rendering, and publication.
- **Adapters** contain provider-specific APIs and filesystem/database details.
- **CLI** translates user intent into workflow calls and renders results.

Provider model names belong in profiles, not workflow code. A workflow receives
a selected provider through a registry and consumes normalized domain objects.

## Application data

On macOS, `platformdirs` resolves the application state to:

```text
~/Library/Application Support/tranpro/
├── config.toml
├── library.sqlite3
└── backups/

~/Library/Caches/tranpro/
```

User-facing Markdown remains beside the source audio unless `--output` says
otherwise. Provider-managed model caches remain provider-managed. OAuth secrets
will be stored in the operating-system keychain rather than SQLite or TOML.

The database will use explicit, ordered schema migrations. Before a migration,
tranpro will make a timestamped SQLite backup. Records are soft-deleted by
default. A normal delete flag moves source media to the operating-system Trash
only after every requested output succeeds.

## Versioned artifacts

A recording is stable identity; processing results are immutable runs:

```text
Recording
├── Transcript run 1 (provider, model, settings)
│   ├── Summary run 1 (prompt version, model, settings)
│   └── Summary run 2
└── Transcript run 2
```

A repeated fingerprint plus equivalent transcription settings may reuse a
successful transcript. Retranscription creates a run instead of overwriting
history. Summaries always point to the exact transcript and prompt versions used.

## Context planning

Summary providers expose their effective runtime context budget. Before a call,
the planner accounts for the system contract, rendered prompt, transcript,
reserved output, and a safety margin. Whole-transcript summarization is preferred
when it fits. Otherwise the planner creates coherent timestamped sections,
summarizes each under the same user instructions, and synthesizes the section
notes. The calculation and intermediate artifacts are persisted for auditability.

Summary evidence refers to stable transcript segment IDs. Renderers turn those
IDs into timestamps and links after validation, so models never invent display
timestamps.

The context planner is deterministic and provider-independent. Providers supply
their token counter or conservative estimator and effective context window; the
planner first tests the complete rendered input, then greedily groups contiguous
transcript segments when a hierarchical pass is required. It rejects a single
segment that cannot fit instead of silently truncating it. The resulting token
counts, limits, and segment groups are serializable and stored on the summary
run. Provider-reported actual usage is stored on each completed step.

## Explicit non-goals for version 1

- A server, web UI, accounts, or telemetry
- Folder watching
- Storing audio blobs in SQLite
- Two-way Google Docs synchronization
- A separate vector database
- Permanent deletion as a convenience flag
