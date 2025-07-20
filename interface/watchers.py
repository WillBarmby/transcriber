from config.paths import  INPUT_DIR, TEXT_DIR, ARCHIVE_DIR, FINAL_DIR
import time
from watchdog.observers import Observer
from interface.audio_handler import AudioHandler
from interface.text_handler import TextHandler

      
def run_watchers():
    for path in [FINAL_DIR, ARCHIVE_DIR, TEXT_DIR, FINAL_DIR]:
        path.mkdir(parents=True,exist_ok=True)
    
    audio_observer = Observer()
    text_observer = Observer()
    
    audio_event_handler = AudioHandler()
    text_event_handler = TextHandler()

    audio_observer.schedule(audio_event_handler,str(INPUT_DIR),recursive=False) 
    text_observer.schedule(text_event_handler,str(TEXT_DIR), recursive=False)

    audio_observer.start()
    text_observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        audio_observer.stop()
        text_observer.stop()
    audio_observer.join()
    text_observer.join()

if __name__ == "__main__":
    run_watchers()