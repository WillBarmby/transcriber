import shutil
from pathlib import Path
from transcriber.core.audio import convert_to_wav, transcribe_audio, TranscriptionError
from transcriber.config.paths import FINAL_DIR, TEXT_DIR, ARCHIVE_DIR
from transcriber.pipelines.base_pipeline import (
    BasePipeline,
    ProcessingResult,
    ProcessingStatus,
)


class AudioPipeline(BasePipeline):
    extensions = {".mp3", ".wav", ".m4a"}
    prompt: str = "Continue with transcription pipeline?"

    def run_pipeline(self, path: Path, output_dir: Path) -> ProcessingResult:
        try:
            wav_path = self.convert_file(path)
            txt_path = transcribe_audio(
                wav_path=wav_path,
                output_path=output_dir / path.with_suffix(".txt").name,
            )
        except TranscriptionError as e:
            return ProcessingResult(
                status=ProcessingStatus.FAILED, input_path=path, error=e
            )

        wav_path.unlink(missing_ok=True)
        self.move_to_archive(path, ARCHIVE_DIR)
        return ProcessingResult(
            status=ProcessingStatus.SUCCESS, input_path=path, output_path=txt_path
        )

    def convert_file(self, path: Path) -> Path:
        assert FINAL_DIR.exists()
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")
        wav_path = FINAL_DIR / path.with_suffix(".wav").name

        if path.suffix != ".wav":
            convert_to_wav(str(path), str(wav_path))
        else:
            shutil.copy2(str(path), str(wav_path))
        return wav_path

    def move_to_archive(self, file_path: Path, archive_dir: Path):
        final_path = archive_dir / file_path.name
        shutil.move(str(file_path), str(final_path))
