from config.paths import  INPUT_DIR, TEXT_DIR
from watchdog.observers import Observer
from interface.audio_handler import AudioHandler
from interface.text_handler import TextHandler
      
def setup_obervers():
    audio_observer = Observer()
    text_observer = Observer()
    
    audio_event_handler = AudioHandler()
    text_event_handler = TextHandler()

    audio_observer.schedule(audio_event_handler,str(INPUT_DIR),recursive=False) 
    text_observer.schedule(text_event_handler,str(TEXT_DIR), recursive=False)
    return [audio_observer, text_observer]
if __name__ == "__main__":
    setup_obervers()