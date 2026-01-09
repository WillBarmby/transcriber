import logging
from pathlib import Path
from llama_cpp import Llama
from transcriber.services.text import summarize_file, SummarizationError
from transcriber.pipelines.base_pipeline import BasePipeline
from transcriber.core.types import (
    ProcessingResult,
    ProcessingRequest,
    ProcessingStatus,
    Artifact,
)

logger = logging.getLogger(__name__)


class TextPipeline(BasePipeline):

    extensions = {".txt"}
    prompt = "Put this text file into summarization pipeline?"

    def run_pipeline(self, request: ProcessingRequest) -> ProcessingResult:
        path: Path = request.input_path
        output_dir: Path = request.output_dir

        final_path = output_dir / path.name
        assert output_dir.exists()
        assert Artifact.SUMMARY in request.requested_outputs

        try:
            summarize_file(
                txt_file=path,
                final_path=final_path,
                nlp=self.nlp,
                llm=self.llm,
            )
        except SummarizationError as e:
            return ProcessingResult(
                status=ProcessingStatus.FAILED, input_path=path, error=e
            )

        result = ProcessingResult(
            status=ProcessingStatus.SUCCESS,
            input_path=path,
            output_path=final_path,
            error=None,
        )
        return result
