import logging
from llama_cpp import Llama
from watchdog.observers import Observer
from config.paths import INPUT_DIR, TEXT_DIR, LLAMA_MODEL_PATH
from handlers.audio_handler import AudioHandler
from handlers.text_handler import TextHandler

logger = logging.getLogger(__name__)


def setup_obervers():
    audio_observer = Observer()
    text_observer = Observer()
    audio_event_handler = AudioHandler(INPUT_DIR)
    llm = Llama(
        model_path=LLAMA_MODEL_PATH, n_ctx=131072, n_gpu_layers=16, verbose=False
    )
    text_event_handler = TextHandler(TEXT_DIR, llm=llm)
    audio_observer.schedule(audio_event_handler, str(INPUT_DIR), recursive=False)
    text_observer.schedule(text_event_handler, str(TEXT_DIR), recursive=False)
    logger.info(
        "The audio event handler is now watching %s", audio_event_handler.watched_folder
    )
    logger.info(
        "The audio event handler is now watching %s", text_event_handler.watched_folder
    )
    return [audio_observer, text_observer]


if __name__ == "__main__":
    setup_obervers()
