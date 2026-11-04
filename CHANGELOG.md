# Changelog

All notable changes to tranpro are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## 0.2.0a1 - Unreleased

Second public alpha.

### Added

- Grounded local Ollama and hosted OpenAI summarization with reusable versioned prompts.
- Google Docs publication with secure OAuth, immutable snapshots, and opt-in timestamps.
- Optional local Nemotron speaker diarization, available to summaries and publications.
- Open a published Google Doc directly from the CLI with `tp publish --open`.

## 0.1.0a1 - 2026-11-02

First public alpha.

### Added

- One-shot local transcription with Parakeet MLX on Apple Silicon.
- Animated terminal progress and optional live timestamped output.
- A persistent SQLite transcript library with immutable transcript runs.
- Recording fingerprinting, reuse, full-text search, and recording-ID input.
- Timestamped Markdown output and recoverable source-file trashing.
- Provider boundaries for Parakeet MLX and whisper.cpp.
- Versioned prompts and grounded local or hosted summaries.
- Optional Google Docs publication with Keychain-backed OAuth.

### Deferred

- Speaker diarization.
