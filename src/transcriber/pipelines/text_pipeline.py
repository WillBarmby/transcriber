from pathlib import Path
from llama_cpp import Llama
from transcriber.config.paths import FINAL_DIR
from transcriber.core.text import chunk_text, rewrite_all_chunks
from transcriber.pipelines.base_pipeline import (
    BasePipeline,
    ProcessingResult,
    ProcessingStatus,
)


class TextPipeline(BasePipeline):
    extensions = {".txt"}
    prompt = "Put this text file into summarization pipeline?"

    def __init__(self, watched_folder, llm: Llama):
        super().__init__(watched_folder)
        self.llm = llm

    def process(self, path: Path) -> ProcessingResult:
        final_path = FINAL_DIR / path.name
        assert FINAL_DIR.exists()

        try:
            with path.open() as f:
                text = f.read()
            chunks = chunk_text(text)
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
