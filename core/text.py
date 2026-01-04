import spacy
import logging
from llama_cpp import Llama
from collections.abc import Iterator
from core.config import CHUNK_SIZE, CLEANUP_SYSTEM_PROMPT, CLEANUP_USER_PROMPT

logger = logging.getLogger(__name__)
nlp = spacy.load("en_core_web_trf")


def chunk_text(text: str):
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
