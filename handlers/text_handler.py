from pathlib import Path
from llama_cpp import Llama
from config.paths import FINAL_DIR
from core.text import chunk_text, rewrite_chunk
from handlers.base_pipeline_handler import BasePipelineHandler


class TextHandler(BasePipelineHandler):
    extensions = {".txt"}
    prompt = "Put this text file into summarization pipeline?"

    def __init__(self, watched_folder, llm: Llama):
        super().__init__(watched_folder)
        self.llm = llm

    def process(self, path: Path) -> Path:
        final_path = FINAL_DIR / path.name
        with path.open() as f:
            text = f.read()
        chunks = chunk_text(text)

        new_chunks = []

        for index, chunk in enumerate(chunks):
            print(f"Rewriting chunk number: {index + 1}")
            rewritten_chunk = rewrite_chunk(llm=self.llm, chunk=chunk)
            new_chunks.append(rewritten_chunk)

        with open(str(final_path), "w") as file:
            for chunk in new_chunks:
                file.write(chunk)
                file.write("\n")
        return final_path
