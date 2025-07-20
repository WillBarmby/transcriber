import utils
import shutil
import subprocess
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from config import INPUT_DIR, OUTPUT_DIR, TEXT_DIR, ARCHIVE_DIR

class AudioHandler(FileSystemEventHandler):
    def __init__(self):
        self.audio_extensions = {".mp3", ".wav", ".m4a"}
        self.seen_files = list()

    # methods that could trigger when file is added
    def on_created(self, event):
        if not event.is_directory:
            self.handle_file(event.src_path)
    
    def on_moved(self, event):
        if not event.is_directory:
            self.handle_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.handle_file(event.src_path)

    # Helper Methods
    def convert_file(self, path:Path):
        wav_path = OUTPUT_DIR / path.with_suffix(".wav").name

        if path.suffix != ".wav":
            utils.convert_to_wav(str(path), str(wav_path))
        else:
            shutil.copy2(str(path), str(wav_path))
        return wav_path    

    def should_process(self, path:Path):
        return path.suffix.lower() in self.audio_extensions and path not in self.seen_files
    
    def handle_file(self,file_path):
        path = Path(file_path)
        if not self.should_process(path):
            # print(f"file is not in accepted audio format: {self.audio_extensions}")
            print(str(path.suffix.lower()))
            return 
        
        self.seen_files.append(path)

        result = subprocess.run(
            ["osascript",
            "-e",
            'display dialog "Put this new file into translation pipeline?" buttons {"No", "Yes"} default button "Yes"'], capture_output=True, text=True)

        if "returned:No" in str(result):
            print("User Declined to move file through pipeline")
            return
        
        wav_path = self.convert_file(path)
        utils.move_to_archive(path, ARCHIVE_DIR)
        txt_path = utils.transcribe_audio(wav_path, TEXT_DIR / path.with_suffix(".txt").name)
        return txt_path # Currently unused, I believe