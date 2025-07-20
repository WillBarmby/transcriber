from pathlib import Path
import spacy 
from core.config import CHUNK_SIZE, CLEANUP_SYSTEM_PROMPT, CLEANUP_USER_PROMPT
from llama_cpp import Llama

def chunk_text(text:str):
    nlp = spacy.load("en_core_web_trf")
    doc = nlp(text=text)
    sentences = list(doc.sents)
    chunks = list()
    for i in range(0, len(sentences), CHUNK_SIZE):
        chunk_sentences = sentences[i:i+CHUNK_SIZE]
        chunk_text = " ".join(sentence.text for sentence in chunk_sentences)
        chunks.append(chunk_text)
    return chunks

def rewrite_chunk(llm:Llama, chunk: str) -> str:
    prompt = f"""
    {CLEANUP_USER_PROMPT}
    Transcript chunk:
    {chunk}
    Cleaned chunk:"""

    result = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": CLEANUP_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        max_tokens= 2048
        )
    print("GREAT SUCCESS")
    return result["choices"][0]["message"]["content"]


if __name__ == "__main__":
    llm = Llama(
        model_path="/Users/willbarmby/Tools/llama_models/llama-3.2-3b-instruct-q4_k_m.gguf",
        n_ctx=131072,
        n_gpu_layers=16,
        verbose=False)
    
    filepath = Path("chat_gpt/Deep Questions with Cal Newport Ep. 359.txt")
    with filepath.open() as f:
        text = f.read()
    chunks = chunk_text(text)
    new_chunks = list()
    for index, chunk in enumerate(chunks):
        print(f"Rewriting chunk number: {index}")
        rewritten_chunk = rewrite_chunk(llm=llm, chunk=chunk)
        new_chunks.append(rewritten_chunk)
        # if index >= 3:
        #     break
    
    with open("podcast.txt","w") as file:
        for chunk in new_chunks:
            file.write(chunk)
            file.write("\n")
