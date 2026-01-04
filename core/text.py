from core.config import CHUNK_SIZE, CLEANUP_SYSTEM_PROMPT, CLEANUP_USER_PROMPT
from llama_cpp import Llama, CreateChatCompletionResponse
from collections.abc import Iterator
import spacy

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
