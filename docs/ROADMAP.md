# Roadmap

Work is intentionally divided into reviewable pull requests. Each pull request
must install independently, keep the command usable, and include tests for its
behavior.

## 1. Application foundation

- Package `tranpro` with the `tp` console command
- Establish platform-native paths and versioned TOML configuration
- Document architecture, support policy, and project vision
- Add linting, typing, tests, build validation, and CI

## 2. Transcript library

- SQLite migrations and pre-migration backups
- Recording fingerprints and versioned artifact records
- Stable transcript segment representation
- Soft delete, restore, list, show, and FTS5 search

## 3. Local transcription

- Parakeet MLX as the Apple Silicon default
- Accelerated whisper.cpp fallback
- Provider/model selection through profiles
- Deduplication, `--retranscribe`, Markdown output, and `--no-save`
- Trash source media only after successful completion
- Retire the legacy watcher/archive pipeline

## 4. Summaries and prompts

- Ollama with Gemma 4 12B as the local default
- Built-in detailed-notes preset and versioned user prompts
- Explicit `--summarize` and standalone summarize commands
- Context feasibility planning and hierarchical fallback
- Grounded segment references and Markdown rendering

## 5. OpenAI profile

- Hosted transcription with `gpt-transcribe`
- Hosted summaries with `gpt-6.1-terra`
- Usage and estimated-cost records
- Mocked provider tests; no network calls in the test suite

## 6. Google Docs publication

- Bring-your-own desktop OAuth credentials and Keychain token storage
- Polished native Google Docs styles
- Immutable publication snapshots, reuse, and explicit updates
- Transcript-only and transcript-plus-summary publication

## 7. Release polish

- Optional fzf-based interactive browsing
- Doctor/setup commands and shell completion
- Clean-environment wheel and source-distribution installation checks
- Migration notes and TestPyPI release rehearsal

Semantic search is a planned extension after the core library stabilizes. Its
passage index will be versioned and derived from canonical transcript segments so
it can coexist with SQLite FTS without changing recording identity.
