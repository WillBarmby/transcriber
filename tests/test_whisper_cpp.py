import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tranpro.transcription.models import TranscriptionError
from tranpro.transcription.whisper_cpp import WhisperCppProvider


def test_parse_whisper_json_normalizes_offsets_and_language() -> None:
    payload: dict[str, Any] = {
        "result": {"language": "en"},
        "transcription": [
            {"offsets": {"from": 100, "to": 1200}, "text": " Hello"},
            {"offsets": {"from": 1200, "to": 2000}, "text": " world"},
        ],
    }

    result = WhisperCppProvider._parse_output(payload)

    assert result.language == "en"
    assert result.duration_ms == 2000
    assert [segment.text for segment in result.segments] == ["Hello", "world"]


def test_whisper_transcribe_converts_audio_and_keeps_gpu_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    executable = tmp_path / "whisper-cli"
    executable.write_text("binary", encoding="utf-8")
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "--output-file" in command:
            base = Path(command[command.index("--output-file") + 1])
            base.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "result": {"language": "en"},
                        "transcription": [
                            {
                                "offsets": {"from": 0, "to": 500},
                                "text": "Test",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    provider = WhisperCppProvider(model=model, executable=executable)

    result = provider.transcribe(source)

    assert len(commands) == 2
    assert commands[0][0] == "ffmpeg"
    assert "--output-json" in commands[1]
    assert "--no-gpu" not in commands[1]
    assert result.segments[0].text == "Test"


def test_whisper_requires_model_and_executable(tmp_path: Path) -> None:
    provider = WhisperCppProvider(
        model=tmp_path / "missing.bin", executable=tmp_path / "missing-cli"
    )

    with pytest.raises(TranscriptionError, match="whisper-cli was not found"):
        provider.transcribe(tmp_path / "audio.wav")
