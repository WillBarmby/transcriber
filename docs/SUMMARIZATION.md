# Summarization

Summarization is always explicit. Transcribe first and summarize later:

```shell
tp recording.mp3
tp summarize 1
```

Or request both operations in one command:

```shell
tp recording.mp3 --summarize
```

The number passed to `tp summarize` is the recording ID shown by `tp list`.
tranpro uses its preferred transcript unless `--transcript ID` selects an exact
run. Every summary freezes its transcript, prompt version, provider, model,
settings, context plan, intermediate passes, and final grounded sections.

## Local setup

The default local profile uses Ollama with `gemma4:12b`:

```shell
brew install --cask ollama
open -a Ollama
ollama pull gemma4:12b
tp summarize 1
```

Gemma 4 12B is the current default because it is sized for laptops and supports
a 256K model context; its Q4 Ollama artifact is roughly 8 GB. tranpro defaults to
a more conservative 65,536-token runtime window on a 32 GB Apple Silicon Mac so
there is room for model weights, the KV cache, the operating system, and output.
Change the runtime limit without changing code:

```shell
tp summarize 1 --context-tokens 32768
tp summarize 1 --model qwen3.5:9b
```

The model is a profile setting, not a workflow dependency. Permanent changes go
in `~/Library/Application Support/tranpro/config.toml` under a named profile.
Google documents Gemma 4 12B as a laptop/desktop model with a 256K context, and
Ollama lists the current 12B artifact and runtime metadata:

- [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4)
- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core)
- [Ollama Gemma 4 tags](https://ollama.com/library/gemma4/tags)

## Long recordings

Before any model call, tranpro estimates the fully rendered input against the
configured runtime window, reserved output, and a safety margin. The Ollama API
does not currently expose a standalone tokenizer endpoint, so the preflight uses
a conservative UTF-8 estimate; actual `prompt_eval_count` and `eval_count` values
returned by Ollama are stored with each step.

If the entire transcript fits, tranpro sends it once. Otherwise it groups whole,
contiguous transcript segments, summarizes each group under the same prompt, and
synthesizes the partial notes. Synthesis is recursive when needed, so a five-hour
recording does not become one oversized final request. Nothing is silently
truncated.

Ollama's structured-output support constrains every response to summary sections
with headings, bodies, and transcript references. tranpro rejects invented
references before saving the result. See Ollama's
[structured outputs documentation](https://ollama.com/blog/structured-outputs).

## Prompts

The built-in `detailed-notes` prompt requests an overview, key arguments and
details, key terms, new concepts, and sources cited or mentioned. Inspect it or
save your own immutable prompt versions:

```shell
tp prompt show detailed-notes
tp prompt save seminar --file seminar-prompt.md
tp summarize 1 --prompt seminar
tp summarize 1 --prompt seminar --prompt-version 1
```

Saving `seminar` again creates a new version without changing old summary runs.

## Output

The default projection is `recording.summary.md` beside the source. Each section
shows validated evidence as a timestamp and stable segment reference. Use
`--output PATH` for an explicit destination and `--force` to replace that exact
path. SQLite remains canonical, so Markdown can be regenerated later.
