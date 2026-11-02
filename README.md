# tranpro

`tranpro` is becoming a local-first transcript library with a straightforward
one-shot command-line workflow:

```text
audio -> durable transcript -> optional summary -> optional Google Doc
```

The Python distribution and import package are named `tranpro`; the command is
the shorter `tp`.

> [!IMPORTANT]
> This branch contains the new application foundation, not the finished
> transcription pipeline. The old `transcriber` source remains in the repository
> temporarily while its behavior is replaced in reviewable increments. It is not
> included in the `tranpro` wheel.

## Current commands

After installation:

```shell
tp --help
tp --version
tp paths
tp config show
tp config init
tp config edit
```

The planned one-shot interface will make transcription the default operation and
summarization explicit:

```shell
tp recording.m4a
tp recording.m4a --summarize
tp summarize 42 --prompt detailed-notes
```

Those workflow commands will arrive with the transcription, library, and
summarization milestones. See [the roadmap](docs/ROADMAP.md).

## Development setup

tranpro requires Python 3.11 or newer. From a clone:

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
tp --version
```

Run the same checks used in continuous integration:

```shell
ruff check .
ruff format --check .
mypy src/tranpro
pytest
python -m build
twine check dist/*
```

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
