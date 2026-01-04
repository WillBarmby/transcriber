from pathlib import Path

# Directories
BASE_DIR = Path(__file__).resolve().parents[1] / "data"
INPUT_DIR = Path.home() / "Downloads"
TEXT_DIR = BASE_DIR / "txt_files"
FINAL_DIR = BASE_DIR / "final"
ARCHIVE_DIR = BASE_DIR / "audio_file_archive"


# Model Paths
MODEL_PATH = Path("/Users/willbarmby/Tools/whisper.cpp/models/ggml-medium.en.bin")
WHISPER_CLI_PATH = Path(
    "/Users/willbarmby/Tools/whisper.cpp/build/bin/whisper-cli"
)  # "/Users/willbarmby/Tools/llama_models/llama-3.2-3b-instruct-q4_k_m.gguf"
LLAMA_MODEL_PATH = (
    "/Users/willbarmby/Tools/llama_models/3.1-8B/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
)
