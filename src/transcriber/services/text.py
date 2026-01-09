from pathlib import Path
from spacy.language import Language
import logging
from llama_cpp import Llama
from collections.abc import Iterator
from transcriber.config.settings import (
    CHUNK_SIZE,
    CLEANUP_SYSTEM_PROMPT,
    CLEANUP_USER_PROMPT,
)
from transcriber.core.types import ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)


class SummarizationError(Exception):
    """Raised during a summarization failure"""

    pass


def summarize_file(*, txt_file: Path, final_path: Path, nlp: Language, llm: Llama):
    if txt_file.suffix != ".txt":
        raise SummarizationError(f"Expected .txt file, got {txt_file}")

    try:
        with txt_file.open() as f:
            text = f.read()
    except Exception as e:
        raise SummarizationError(f"Failed to read input file: {txt_file}") from e

    try:
        chunks = chunk_text(text, nlp)
    except Exception as e:
        raise SummarizationError("chunk_text failed") from e

    if not chunks:
        raise SummarizationError("chunk_text returned no chunks")

    try:
        new_chunks = rewrite_all_chunks(chunks=chunks, llm=llm)
    except Exception as e:
        raise SummarizationError("rewrite_all_chunks failed") from e

    final_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(final_path), "w") as file:
        for chunk in new_chunks:
            file.write(chunk)
            file.write("\n")

    assert final_path.exists()
    assert final_path.stat().st_size > 0

    logger.info("Finished processing %s → %s", txt_file.name, final_path)


def chunk_text(text: str, nlp: Language):
    doc = nlp(text=text)
    sentences = list(doc.sents)
    chunks = []
    for i in range(0, len(sentences), CHUNK_SIZE):
        chunk_sentences = sentences[i : i + CHUNK_SIZE]
        chunk_text = " ".join(sentence.text for sentence in chunk_sentences)
        chunks.append(chunk_text)
    return chunks


def rewrite_chunk(llm: Llama, chunk: str) -> str:
    prompt = f"""
    {CLEANUP_USER_PROMPT}
    Transcript chunk:
    {chunk}
    Cleaned chunk:"""
    result = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": CLEANUP_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
    )
    if isinstance(result, Iterator):
        raise RuntimeError("Streaming not supported yet")

    content = result["choices"][0]["message"]["content"]
    if content is None:
        raise RuntimeError("LLM returned empty content")

    return content


def rewrite_all_chunks(chunks: list[str], llm: Llama) -> list[str]:
    new_chunks = []
    for index, chunk in enumerate(chunks):
        logger.debug("Rewriting chunk %d/%d", index + 1, len(chunks))
        rewritten_chunk = rewrite_chunk(llm=llm, chunk=chunk)
        new_chunks.append(rewritten_chunk)
    return new_chunks
