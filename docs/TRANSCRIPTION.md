# Local transcription

## Default workflow

On Apple Silicon, the default profile uses Parakeet MLX with
`mlx-community/parakeet-tdt-0.6b-v3`:

```shell
python -m pip install 'tranpro[local]'
tp podcast.m4a
```

The first run downloads the model through Hugging Face. Later runs use the
provider-managed cache. Parakeet handles long recordings with 120-second chunks
and 15 seconds of overlap by default; tranpro stores those settings as part of
transcript identity. Equivalent provider, model, and settings reuse a successful
run unless `--retranscribe` is present.

## Live terminal output

Interactive terminals show a spinner, completion bar, elapsed time, and estimated
remaining time by default. The animation is written to stderr so `--output -`
remains safe to pipe. It automatically disappears in non-interactive contexts;
pass `--no-progress` to disable it explicitly.

Parakeet can print finalized timestamped sentences while it processes a
recording:

```shell
tp podcast.m4a --retranscribe --live
```

Live mode incrementally runs Parakeet's normal chunk decoder and prints only
sentences that are safely outside the next chunk's overlap window. The final
chunks use the same overlap merge as batch transcription, preserving its aligned
timestamps and quality. The completed result is saved normally in SQLite and
Markdown. Its run settings record streaming mode, so it remains distinct from
batch transcripts for reuse and comparison.

`--live` cannot be combined with `--output -`, which prints a complete Markdown
document only after processing. Live output is currently available only with
the `parakeet-mlx` provider.

Parakeet MLX documents its current API and timestamp behavior in the
[upstream project](https://github.com/senstella/parakeet-mlx). Local Parakeet is
supported on Apple Silicon. Other platforms can use a hosted provider in a later
milestone or configure whisper.cpp themselves.

## Outputs

The normal command creates readable timestamped Markdown beside the source:

```text
podcast.m4a
podcast.transcript.md
```

The Markdown front matter records source, provider, model, recording ID, and
transcript ID. If a different transcript would collide with an existing default
file, tranpro creates `podcast.transcript.2.md` rather than overwriting it.

An explicit output path is stricter:

```shell
tp podcast.m4a --output notes.md
```

If `notes.md` already differs, the command stops. `--force` is required to
replace it. Standard output is useful in pipelines:

```shell
tp podcast.m4a --no-save --output -
```

## Source safety

Transcription never archives or moves source media by default. The old folder
watcher and automatic archive pipeline have been removed.

`--trash-source` (short form `-d`) uses the operating-system Trash, never a
permanent unlink. It is finalized only after database persistence and requested
Markdown or stdout output succeed. If transcription or rendering fails, the
source stays in place. The library records the original path and trash time.

## Profiles and model switching

Profiles live in `config.toml`. Inspect their location and defaults with:

```shell
tp paths
tp config show
tp config edit
```

Select or override a profile at invocation time:

```shell
tp podcast.m4a --profile local
tp podcast.m4a --provider parakeet-mlx --model another/model
```

The built-in whisper.cpp adapter is an explicit fallback. It converts inputs to
16 kHz mono WAV with ffmpeg, requests JSON timestamps, and leaves GPU and flash
attention enabled:

```toml
[profiles.whisper]
transcription_provider = "whisper-cpp"
transcription_model = "/path/to/ggml-model.bin"
whisper_cli = "/path/to/whisper-cli"
language = "auto"
```

```shell
tp podcast.m4a --profile whisper
```

The upstream [whisper.cpp CLI documentation](https://github.com/ggml-org/whisper.cpp/tree/master/examples/cli)
describes its supported models and decoder options.
