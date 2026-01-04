import logging
from llama_cpp import Llama
from watchdog.observers import Observer
from transcriber.config.paths import INPUT_DIR, TEXT_DIR, LLAMA_MODEL_PATH
from transcriber.pipelines.audio_pipeline import AudioPipeline
from transcriber.pipelines.text_pipeline import TextPipeline

logger = logging.getLogger(__name__)


def setup_observers():
    audio_observer = Observer()
    text_observer = Observer()
    audio_event_handler = AudioPipeline(INPUT_DIR)
    llm = Llama(
        model_path=LLAMA_MODEL_PATH, n_ctx=131072, n_gpu_layers=16, verbose=False
    )
    text_event_handler = TextPipeline(TEXT_DIR, llm=llm)
    audio_observer.schedule(audio_event_handler, str(INPUT_DIR), recursive=False)
    text_observer.schedule(text_event_handler, str(TEXT_DIR), recursive=False)
    logger.info(
        "The audio event handler is now watching %s", audio_event_handler.watched_folder
    )
    logger.info(
        "The text event handler is now watching %s", text_event_handler.watched_folder
    )
    return [audio_observer, text_observer]


if __name__ == "__main__":
    setup_observers()
