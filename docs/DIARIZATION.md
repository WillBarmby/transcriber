# Speaker diarization

Tranpro can identify who spoke when with NVIDIA Nemotron 3 Diarization through
MLX Audio on Apple Silicon. Diarization is an explicit second pass: transcription
stays fast and unchanged until you request speaker labels.

## Install the optional runtime

MLX Audio is deliberately not part of the base installation. For a new pipx
installation, install the optional dependency group:

```console
pipx install "tranpro[diarization]"
```

To add it to an existing pipx installation:

```console
pipx inject tranpro "mlx-audio>=0.6.2,<0.7"
```

With a regular virtual environment, use:

```console
python -m pip install "tranpro[diarization]"
```

The model weights are downloaded from Hugging Face on first use and are not
bundled with tranpro. An `HF_TOKEN` is optional, but avoids anonymous Hub rate
limits. MLX Audio is MIT licensed; the Nemotron model has its own Open Model
Development and Weights License on its Hugging Face model card.

## Use it

First transcribe and save a recording, then diarize its library ID:

```console
tp interview.mp3
tp diarize 2
```

Tranpro uses the preferred transcript unless `--transcript ID` selects an exact
run. An equivalent successful diarization is reused. To intentionally create a
new immutable run:

```console
tp diarize 2 --rediarize
```

Useful tuning options include:

```console
tp diarize 2 --threshold 0.45 --min-duration 0.2 --merge-gap 0.15
tp diarize 2 --preset low
tp diarize 2 --model mlx-community/Nemotron-3-Diarization-8bit
```

The default `offline` preset favors accuracy. The `low`, `very-low`, and
`ultra-low` presets reduce buffering latency and are mainly useful for future
live-input workflows. Long recordings use bounded speaker-cache context rather
than loading a five-hour attention window at once.

## What is stored

Each run preserves:

- the provider, exact model and inference settings;
- the original speaker-activity timeline;
- stable generic labels in first-arrival order (`Speaker 1`, `Speaker 2`, ...);
- the deterministic assignment from that timeline to each transcript segment;
- ambiguous handoffs as `Mixed`, rather than invented word boundaries.

The original transcript is never modified. A later retranscription can reuse the
same recording-level speaker timeline and produce its own immutable alignment.
