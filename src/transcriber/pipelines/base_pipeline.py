import logging
from pathlib import Path
from spacy import load
from llama_cpp import Llama
from spacy.language import Language
from transcriber.core.types import ProcessingRequest, ProcessingStatus, ProcessingResult
from transcriber.config.paths import LLAMA_MODEL_PATH


class BasePipeline:

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._llm: Llama | None = None
        self._llm_model_path: Path = Path(LLAMA_MODEL_PATH)
        self._nlp = None

    @property
    def llm(self) -> Llama:
        if self._llm is None:
            self.logger.info("Initialzing LLM from %s", self._llm_model_path)
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

    def process(self, request: ProcessingRequest):  # path, output_dir: Path
        result = self.run_pipeline(request)
        self.process_result(result)

    def process_result(self, result: ProcessingResult):
        if result.status is ProcessingStatus.SUCCESS:
            self.logger.info(
                "Successfully processed %s, text_file at: %s",
                result.input_path.name,
                result.output_path,
            )
            return
        if result.status is ProcessingStatus.SKIPPED:
            self.logger.info("Skipped %s", result.input_path.name)
            return
        if result.status is ProcessingStatus.FAILED:
            self.logger.error(
                "Failed to process %s: %s", result.input_path.name, result.error
            )
            return

        raise RuntimeError(f"Unhandled ProcessingResult status: {result.status}")

    def run_pipeline(self, request: ProcessingRequest) -> ProcessingResult:
        raise NotImplementedError
