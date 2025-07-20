from config import WHISPER_CLI_PATH, MODEL_PATH
from fpdf import FPDF
import subprocess
from pathlib import Path
import shutil

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
        archive_dir.mkdir(parents=True,exist_ok=True)
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
        wav_path.unlink(missing_ok=True)
        return output_path # This my problem line - .with_suffix(".txt")
