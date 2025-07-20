from pathlib import Path
from watchdog.events import FileSystemEventHandler
from llama_cpp import Llama
from config.paths import LLAMA_MODEL_PATH, FINAL_DIR
from core.utils import chunk_text, rewrite_chunk


class TextHandler(FileSystemEventHandler):
    def __init__(self):
        self.text_extensions = {".txt"}
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
   
    def should_process(self, path:Path):
        return path.suffix.lower() in self.text_extensions and path.name not in self.seen_files
    
    def handle_file(self,file_path):
        path = Path(file_path)

        if not self.should_process(path):
            return
        
        self.seen_files.append(path.name)
        
        llm = Llama(
        model_path = LLAMA_MODEL_PATH,
        n_ctx=131072,
        n_gpu_layers=16,
        verbose=False)
    
        with path.open() as f:
            text = f.read()
        chunks = chunk_text(text)
        
        new_chunks = list()
        for index, chunk in enumerate(chunks):
            print(f"Rewriting chunk number: {index + 1}")
            rewritten_chunk = rewrite_chunk(llm=llm, chunk=chunk)
            new_chunks.append(rewritten_chunk)

        final_path = FINAL_DIR / path.name
        with open(str(final_path), "w") as file:
            for chunk in new_chunks:
                file.write(chunk)
                file.write("\n")