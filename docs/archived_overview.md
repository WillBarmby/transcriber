# Transcriber Codebase Overview

## High-Level Purpose
Transcriber automates the pipeline for turning newly downloaded audio files into polished summaries. Watchdog observers monitor configured folders, convert audio into text with `whisper.cpp`, optionally run large-language-model cleanup, and deposit the final outputs in archive and summary directories.

## Repository Layout
- `main.py` – entry point that prepares directories and launches watchdog observers for audio and text workflows.
- `config/paths.py` – centralizes filesystem locations and model paths. These values currently point to user-specific absolute paths and should be adjusted per environment.
- `core/config.py` – runtime configuration such as chunk sizes and prompt templates for the cleanup LLM.
- `core/utils.py` – shared helpers for audio conversion, transcription, text chunking, and chunk rewriting.
- `interface/` – user-facing components that react to filesystem events:
  - `audio_handler.py` – responds to new audio by prompting the user, converting to mono WAV, invoking Whisper, and archiving inputs.
  - `text_handler.py` – reacts to text transcripts, optionally sends them through a llama.cpp summarization pass, and writes cleaned text.
  - `watchers.py` – ties the handlers together and instantiates watchdog observers.
- `scripts/make_docs.py` – optional tool for pairing summaries and transcripts, then creating Google Docs via the Drive and Docs APIs.
- `fonts/` – contains font resources for PDF generation when `core.utils.create_pdf` is used.

## Runtime Flow
1. `main.py` ensures the configured directories exist and starts the observers.
2. `AudioHandler` notices a new audio file, optionally confirms user intent, converts or copies to WAV, triggers Whisper transcription, and moves the source to an archive directory.
3. The Whisper transcription lands in the text folder, triggering `TextHandler`. After user confirmation it loads a llama.cpp model, chunks the transcript, rewrites each chunk with the cleanup prompt, and saves the polished text into the final folder.
4. The optional `scripts/make_docs.py` script can take matching transcript/final text pairs and publish them to Google Docs.

## Key Dependencies
- [`watchdog`](https://python-watchdog.readthedocs.io/) for filesystem monitoring.
- `ffmpeg` CLI for audio conversion.
- `whisper.cpp` CLI for speech-to-text.
- `spacy` (with the `en_core_web_trf` model) for sentence segmentation.
- `llama-cpp-python` for on-device summarization.
- Optional Google APIs (`google-api-python-client`, `google-auth`) for document publishing.

Ensure these dependencies and model files are installed where `config/paths.py` expects them, or update the configuration accordingly.

## Setup & Usage Tips
1. Install required Python packages (watchdog, spacy with the transformer model, llama-cpp-python, fpdf, google API packages if needed).
2. Download the spaCy model via `python -m spacy download en_core_web_trf`.
3. Install `ffmpeg`, `whisper.cpp`, and the desired llama.cpp model.
4. Update `config/paths.py` to point at directories on your machine and provide the correct model binaries.
5. Run `python main.py` to start the watchers.

## Next Steps for New Contributors
- **Configuration hardening:** Replace absolute paths in `config/paths.py` with environment-aware settings (e.g., `.env` file or CLI arguments).
- **Error handling & logging:** Add structured logging and robust exception handling around subprocess calls and model loading.
- **Testing:** Introduce unit tests for `core.utils` and integration tests that mock filesystem events.
- **User experience:** Replace macOS-specific `osascript` prompts with cross-platform alternatives, and consider adding a GUI or CLI to control the pipeline.
- **Performance tuning:** Cache the loaded Llama model across file events and explore batch processing for multiple transcripts.

## Additional Resources
- Whisper.cpp: <https://github.com/ggerganov/whisper.cpp>
- llama.cpp: <https://github.com/ggerganov/llama.cpp>
- Watchdog Documentation: <https://python-watchdog.readthedocs.io/>

