from config.paths import INPUT_DIR, TEXT_DIR, LLAMA_MODEL_PATH
from watchdog.observers import Observer
from handlers.audio_handler import AudioHandler
from handlers.text_handler import TextHandler
from llama_cpp import Llama


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

    print(
        str(
            f"The audio event handler is now watching {audio_event_handler.watched_folder}"
        )
    )
    print(
        str(
            f"The text event handler is now watching {text_event_handler.watched_folder}"
        )
    )
    return [audio_observer, text_observer]


if __name__ == "__main__":
    setup_obervers()
