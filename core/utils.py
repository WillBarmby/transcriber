from config.paths import WHISPER_CLI_PATH, MODEL_PATH
from core.config import CHUNK_SIZE, CLEANUP_SYSTEM_PROMPT, CLEANUP_USER_PROMPT
import subprocess
import shutil
import spacy 
from pathlib import Path
from llama_cpp import Llama
from fpdf import FPDF

def create_pdf(text, output_path:str):
        pdf_file = FPDF()
        pdf_file.add_font(family="Charis", fname="Charis-Regular.ttf", style="")
        pdf_file.set_font(family="Charis", style="", size=12)
        pdf_file.add_page()
        pdf_file.multi_cell(0,10,text)
        pdf_file.output(output_path)
        return pdf_file

def convert_to_wav(input_path:str, output_path:str):
        ffmpeg_conversion_command = [
        "ffmpeg",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        output_path]
        subprocess.run(ffmpeg_conversion_command,check=True)
        
def move_to_archive(file_path:Path, archive_dir:Path):
        final_path = archive_dir / file_path.name 
        shutil.move(str(file_path), str(final_path))

def transcribe_audio(wav_path:Path, output_path:Path):
        whisper_cpp_command = [
            str(WHISPER_CLI_PATH),
            "-m", str(MODEL_PATH),
            "-f", str(wav_path),
            "-t", "6",
            "--output-txt",
            "-of", str(output_path.with_suffix(""))
        ]
        print(f"Transcribing with whisper.cpp: {wav_path.name}")
        subprocess.run(whisper_cpp_command, check=True)
        return output_path


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

def rewrite_chunk(llm:Llama, chunk: str):
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