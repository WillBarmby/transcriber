# OpenAI profile

The hosted profile is an explicit opt-in. Local Parakeet transcription and local
Ollama summaries remain the defaults and require no API account.

## Setup

Create an API key in the OpenAI platform and expose it to the command process:

```shell
export OPENAI_API_KEY="your-api-key"
tp summarize 1 --profile openai
```

tranpro does not write the key to its configuration file or SQLite database. For
a persistent shell setup, store the variable through your preferred macOS secret
manager or shell environment rather than committing it to this repository.

The Python SDK is installed with tranpro, but no hosted request occurs unless an
OpenAI profile is explicitly selected.

## Summary model and context

The default hosted summary model is `gpt-6.1-terra`. OpenAI documents a
1,050,000-token model context, structured-output support, and standard prices of
$1 per million input tokens and $5 per million output tokens. tranpro uses a
272,000-token effective window by default. After reserving output and a safety
margin, this keeps normal requests below the threshold where long-context pricing
begins.

Every response uses the Responses API with strict structured output, reasoning
effort `none`, and remote response storage disabled. The API's actual input and
output token counts are stored on the corresponding summary step. tranpro also
records a standard-rate cost estimate using the current default model rates;
account-specific tiers, regional processing, and future price changes can make
the final invoice differ.

Model, context, and prompt selection remain ordinary command options:

```shell
tp summarize 1 --profile openai
tp summarize 1 --profile openai --model gpt-6.1-terra
tp summarize 1 --profile openai --prompt seminar
tp summarize 1 --profile openai --context-tokens 120000
```

Official references:

- [GPT-6.1 Terra model](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
- [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

## Hosted transcription

Hosted transcription is intentionally separate from this summary adapter. The
current recommended `gpt-transcribe` model accepts completed files up to 25 MB
but does not provide the timestamped segments tranpro uses for grounded evidence.
Adding it cleanly requires an explicit representation for coarse or unavailable
timestamps plus a tested large-file splitting policy; it should not fabricate
precise timestamps merely to fit the existing domain model.

The current OpenAI transcription guidance and limits are documented in the
[file transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text).
