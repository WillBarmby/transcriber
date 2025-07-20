import time
from watchdog.observers import Observer
from core.config import  INPUT_DIR, OUTPUT_DIR, TEXT_DIR, ARCHIVE_DIR, FINAL_DIR
from file_handlers import audio_handler, text_handler
      
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True,exist_ok=True)
    TEXT_DIR.mkdir(parents=True,exist_ok=True)
    FINAL_DIR.mkdir(parents=True,exist_ok=True)

    audio_observer = Observer()
    text_observer = Observer()
    
    audio_event_handler = audio_handler.AudioHandler()
    text_event_handler = text_handler.TextHandler()

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
    main()