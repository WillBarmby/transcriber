import shutil
import core.utils as utils
from pathlib import Path
from config.paths import FINAL_DIR, TEXT_DIR, ARCHIVE_DIR
from handlers.base_pipeline_handler import BasePipelineHandler


class AudioHandler(BasePipelineHandler):
    extensions = {".mp3", ".wav", ".m4a"}
    prompt: str = "Continue with transcription pipeline?"

    def convert_file(self, path: Path):
        wav_path = FINAL_DIR / path.with_suffix(".wav").name

        if path.suffix != ".wav":
            utils.convert_to_wav(str(path), str(wav_path))
        else:
            shutil.copy2(str(path), str(wav_path))
        return wav_path

    def process(self, path: Path) -> Path | None:
        wav_path = self.convert_file(path)
        try:
            txt_path = utils.transcribe_audio(
                wav_path=wav_path, output_path=TEXT_DIR / path.with_suffix(".txt").name
            )
        except utils.TranscriptionError as e:
            print(f"Transcription Error and stuff: {e}")
            return None
        wav_path.unlink(missing_ok=True)
        utils.move_to_archive(path, ARCHIVE_DIR)
        return txt_path
