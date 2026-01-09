import logging
from spacy import load
from spacy.language import Language
from pathlib import Path
from llama_cpp import Llama
from transcriber.services.text import chunk_text, rewrite_all_chunks
from transcriber.pipelines.base_pipeline import (
    BasePipeline,
    ProcessingResult,
    ProcessingStatus,
)

logger = logging.getLogger(__name__)


class TextPipeline(BasePipeline):

    extensions = {".txt"}
    prompt = "Put this text file into summarization pipeline?"

    def __init__(self, *, llm_model_path: Path):
        super().__init__()
        self._llm: Llama | None = None
        self._llm_model_path: Path = llm_model_path
        self._nlp = None

    @property
    def llm(self) -> Llama:
        if self._llm is None:
            logger.info("Initialzing LLM from %s", self._llm_model_path)
            self._llm = Llama(
                model_path=str(self._llm_model_path),
                n_ctx=131072,
                n_gpu_layers=16,
                verbose=False,
            )
        return self._llm

    @property
    def nlp(self) -> Language:
        if self._nlp is None:
            self._nlp = load("en_core_web_trf")
        return self._nlp

    def run_pipeline(self, path: Path, output_dir: Path) -> ProcessingResult:
        final_path = output_dir / path.name
        assert output_dir.exists()

        try:
            with path.open() as f:
                text = f.read()

            chunks = chunk_text(text, self.nlp)
        except Exception as e:
            return ProcessingResult(
                status=ProcessingStatus.FAILED, input_path=path, error=e
            )

        if not chunks:
            return ProcessingResult(
                status=ProcessingStatus.FAILED,
                input_path=path,
                error=ValueError("chunk_text returned no chunks"),
            )

        try:
            new_chunks = rewrite_all_chunks(chunks=chunks, llm=self.llm)
        except Exception as e:
            return ProcessingResult(
                status=ProcessingStatus.FAILED, input_path=path, error=e
            )

        with open(str(final_path), "w") as file:
            for chunk in new_chunks:
                file.write(chunk)
                file.write("\n")
        assert final_path.exists()
        assert final_path.stat().st_size > 0

        self.logger.info("Finished processing %s → %s", path.name, final_path)

        result = ProcessingResult(
            status=ProcessingStatus.SUCCESS,
            input_path=path,
            output_path=final_path,
            error=None,
        )
        return result
