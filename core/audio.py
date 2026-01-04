from config.paths import WHISPER_CLI_PATH, MODEL_PATH
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised during a transcription failure"""

    pass


def transcribe_audio(wav_path: Path, output_path: Path):
    base_path = output_path.with_suffix("")
    whisper_cpp_command = [
        str(WHISPER_CLI_PATH),
        "-m",
        str(MODEL_PATH),
        "-f",
        str(wav_path),
        "-t",
        "3",
        "--no-gpu",
        "--output-txt",
        "-of",
        str(base_path),
    ]

    logger.info("Transcribing with whisper.cpp: %s", wav_path.name)

    result = subprocess.run(
        whisper_cpp_command,
        stdout=None,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise TranscriptionError(
            f"whisper.cpp failed on {wav_path.name}\n{result.stderr}"
        )
    return output_path


def convert_to_wav(input_path: str, output_path: str):
    ffmpeg_conversion_command = [
        "ffmpeg",
        "-i",
        input_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        output_path,
    ]
    result = subprocess.run(
        ffmpeg_conversion_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.strip()}")
