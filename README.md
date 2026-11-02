# tranpro

`tranpro` is becoming a local-first transcript library with a straightforward
one-shot command-line workflow:

```text
audio -> durable transcript -> optional summary -> optional Google Doc
```

The Python distribution and import package are named `tranpro`; the command is
the shorter `tp`.

The current development branch provides local transcription, the persistent
transcript library, and explicit local summarization. Google Docs publication
remains a roadmap milestone.

## Installation

tranpro currently targets Python 3.11 or newer on Apple Silicon Macs. Install
the CLI and its local Parakeet backend with one command:

```shell
python3 -m pip install tranpro
tp --version
tp recording.m4a
```

The first transcription downloads the model from Hugging Face and caches it for
later runs. Parakeet MLX is installed automatically only on Apple Silicon;
other platforms receive the portable CLI and database without that dependency.

This is an alpha release: the transcript database is designed to persist, but
commands and configuration may still change before 1.0.

## Current commands

After installation:

```shell
tp --help
tp --version
tp recording.m4a
tp recording.m4a --output -
tp recording.m4a --no-save
tp recording.m4a --retranscribe
tp 2 --retranscribe
tp recording.m4a --retranscribe --live
tp recording.m4a --no-progress
tp recording.m4a --trash-source
tp recording.m4a --summarize
tp summarize RECORDING_ID
tp summarize RECORDING_ID --model gemma4:12b
tp summarize RECORDING_ID --profile openai
tp paths
tp config show
tp config init
tp config edit
tp prompt list
tp prompt show detailed-notes
tp prompt save my-notes --file prompt.md
tp library init
tp library status
tp list
tp show RECORDING_ID
tp search "budget constraints"
tp forget RECORDING_ID
tp restore RECORDING_ID
```

Library commands use an embedded SQLite database with automatic schema
migrations and pre-migration backups. `forget` is a recoverable soft deletion:
it does not remove source audio, transcripts, or summaries. Full-text search uses
SQLite FTS5 across timestamped transcript segments and summary sections. See the
[database design](docs/DATABASE.md) for identity, versioning, and safety details.

Prompt commands prepare reusable instructions for the upcoming summary workflow.
Each save creates an immutable version so an old summary can always identify the
exact instructions that produced it.

Local summaries use Ollama and structured JSON output. Install Ollama separately,
start it, and pull the configured model before the first summary. The default is
`gemma4:12b`; model and effective context can be changed per command or profile.
Long transcripts automatically use grounded, auditable multi-pass summarization
without splitting transcript segments or silently truncating input. See the
[summarization guide](docs/SUMMARIZATION.md).

The opt-in OpenAI summary profile uses `gpt-6.1-terra` through the Responses API
with strict structured output, actual token accounting, and an estimated standard
cost stored per step. Set `OPENAI_API_KEY` and pass `--profile openai`; the key is
never stored in SQLite or `config.toml`. See the [OpenAI profile guide](docs/OPENAI.md).

Transcription is the default operation. The equivalent explicit form is also
available:

```shell
tp recording.m4a
tp transcribe recording.m4a
```

By default, tranpro saves a versioned library record and writes
`recording.transcript.md` beside the source. `--output -` prints Markdown to
stdout, while `--no-save` skips SQLite. Existing equivalent runs are reused;
`--retranscribe` creates another immutable version. `--trash-source`/`-d` moves
the source to the operating-system Trash only after output succeeds.
Parakeet's `--live` mode prints finalized timestamped sentences as they become
available while retaining the complete saved library and Markdown outputs.
Interactive terminals show an animated progress bar by default. `--no-progress`
disables it; redirected and non-interactive output disables it automatically.

See the [transcription guide](docs/TRANSCRIPTION.md) and
[roadmap](docs/ROADMAP.md).

## Development setup

tranpro requires Python 3.11 or newer. From a clone:

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
tp --version
```

On Apple Silicon, the normal installation includes Parakeet MLX. Its model
downloads to the Hugging Face cache on first use.

Run the same checks used in continuous integration:

```shell
ruff check .
ruff format --check .
mypy src/tranpro
pytest
python -m build
twine check dist/*
```

Maintainers can find the tagged-release process in
[docs/RELEASING.md](docs/RELEASING.md).

The first supported local runtime target is macOS on Apple Silicon. The core,
database, and hosted-provider abstractions are intended to remain portable;
Linux and Windows are best-effort until they are tested in CI and on real hosts.

## Project principles

- Local and free by default; hosted providers are explicit opt-ins.
- Transcription is the default action; summarization is explicit.
- SQLite is the source of truth. Markdown and Google Docs are rendered outputs.
- Provider boundaries keep model selection out of the core workflow.
- Source media is never deleted permanently by a normal command.
- No server, account system, or telemetry is required.

## License

[MIT](LICENSE)
