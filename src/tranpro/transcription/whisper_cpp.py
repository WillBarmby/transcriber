"""whisper.cpp command-line provider."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tranpro.library.models import Segment
from tranpro.transcription.models import (
    ProviderDescriptor,
    TranscriptionError,
    TranscriptionEventSink,
    TranscriptionOutput,
)


class WhisperCppProvider:
    """Run accelerated whisper.cpp and parse its JSON sidecar."""

    def __init__(
        self,
        *,
        model: Path,
        executable: Path | None = None,
        ffmpeg: str = "ffmpeg",
        language: str = "auto",
    ) -> None:
        self.model_path = model.expanduser()
        discovered = shutil.which("whisper-cli") if executable is None else None
        self.executable = Path(discovered) if discovered else executable
        self.ffmpeg = ffmpeg
        self.language = language

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="whisper-cpp",
            model=str(self.model_path),
            settings={
                "executable": None if self.executable is None else str(self.executable),
                "language": self.language,
            },
        )

    def transcribe(
        self, source: Path, *, emit: TranscriptionEventSink | None = None
    ) -> TranscriptionOutput:
        executable = self._validated_executable()
        if not self.model_path.is_file():
            raise TranscriptionError(f"whisper.cpp model not found: {self.model_path}")

        with tempfile.TemporaryDirectory(prefix="tranpro-whisper-") as temp_dir:
            temp_path = Path(temp_dir)
            wav_path = temp_path / "audio.wav"
            output_base = temp_path / "transcript"
            self._convert_to_wav(source, wav_path)
            command = [
                str(executable),
                "--model",
                str(self.model_path),
                "--file",
                str(wav_path),
                "--language",
                self.language,
                "--output-json",
                "--output-file",
                str(output_base),
                "--no-prints",
            ]
            try:
                result = subprocess.run(command, capture_output=True, text=True)
            except OSError as error:
                raise TranscriptionError(
                    f"Could not run whisper-cli: {error}"
                ) from error
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise TranscriptionError(f"whisper.cpp failed: {detail}")
            json_path = output_base.with_suffix(".json")
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise TranscriptionError(
                    f"Could not read whisper.cpp JSON output: {error}"
                ) from error
        return self._parse_output(payload)

    def _validated_executable(self) -> Path:
        if self.executable is None or not self.executable.is_file():
            raise TranscriptionError(
                "whisper-cli was not found; set whisper_cli in the selected profile"
            )
        return self.executable

    def _convert_to_wav(self, source: Path, destination: Path) -> None:
        command = [
            self.ffmpeg,
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(destination),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except OSError as error:
            raise TranscriptionError(f"Could not run ffmpeg: {error}") from error
        if result.returncode != 0:
            raise TranscriptionError(f"ffmpeg failed: {result.stderr.strip()}")

    @staticmethod
    def _parse_output(payload: dict[str, Any]) -> TranscriptionOutput:
        nested_result = payload.get("result")
        result_metadata = nested_result if isinstance(nested_result, dict) else {}
        raw_segments = payload.get("transcription")
        if raw_segments is None:
            raw_segments = result_metadata.get("transcription", [])
        if not isinstance(raw_segments, list):
            raise TranscriptionError("whisper.cpp JSON has no transcription array")

        segments: list[Segment] = []
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                continue
            text = str(raw_segment.get("text", "")).strip()
            if not text:
                continue
            offsets = raw_segment.get("offsets", {})
            if not isinstance(offsets, dict):
                offsets = {}
            start_ms = max(0, int(offsets.get("from", 0)))
            end_ms = max(start_ms, int(offsets.get("to", start_ms)))
            segments.append(Segment(len(segments), start_ms, end_ms, text))

        language_value = result_metadata.get("language") or payload.get("language")
        language = None if language_value is None else str(language_value)
        duration_ms = max((segment.end_ms for segment in segments), default=None)
        return TranscriptionOutput(tuple(segments), language, duration_ms)
