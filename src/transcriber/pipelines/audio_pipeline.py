import shutil
from pathlib import Path
from spacy import load
from transcriber.services.audio import (
    convert_to_wav,
    transcribe_audio,
    TranscriptionError,
)
from transcriber.services.text import SummarizationError, summarize_file
from transcriber.pipelines.base_pipeline import BasePipeline
from transcriber.core.types import (
    ProcessingResult,
    ProcessingRequest,
    ProcessingStatus,
    Artifact,
)
from transcriber.config.paths import LLAMA_MODEL_PATH


class AudioPipeline(BasePipeline):
    def __init__(self, *, output_dir: Path, archive_dir: Path):
        super().__init__()
        self.extensions = {".mp3", ".wav", ".m4a"}
        self.archive_dir = archive_dir
        self.output_dir = output_dir

    def run_pipeline(self, request: ProcessingRequest) -> ProcessingResult:
        path: Path = request.input_path
        output_dir: Path = request.output_dir
        requested_output = request.requested_outputs
        assert Artifact.TRANSCRIPT in requested_output

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
        self.move_to_archive(path, self.archive_dir)

        if Artifact.SUMMARY in requested_output:
            from transcriber.services.text import summarize_file

            transcript_dir: Path = output_dir / "transcripts"
            txt_path = self.move_to_archive(
                file_path=txt_path, archive_dir=transcript_dir
            )

            summary_path: Path = output_dir / "summaries" / path.name
            summary_path = summary_path.with_suffix(".txt")
            summary_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                summarize_file(
                    txt_file=txt_path,
                    final_path=summary_path,
                    nlp=self.nlp,
                    llm=self.llm,
                )
            except SummarizationError as e:
                return ProcessingResult(
                    status=ProcessingStatus.FAILED, input_path=path, error=e
                )

        return ProcessingResult(
            status=ProcessingStatus.SUCCESS, input_path=path, output_path=txt_path
        )

    def convert_file(self, path: Path) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")
        wav_path = self.output_dir / path.with_suffix(".wav").name

        if path.suffix != ".wav":
            convert_to_wav(str(path), str(wav_path))
        else:
            shutil.copy2(str(path), str(wav_path))
        return wav_path

    def move_to_archive(self, file_path: Path, archive_dir: Path) -> Path:
        archive_dir.mkdir(exist_ok=True, parents=True)
        final_path = archive_dir / file_path.name
        shutil.move(str(file_path), str(final_path))
        return final_path
