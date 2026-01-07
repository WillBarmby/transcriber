from pathlib import Path
from typing import TypeAlias
from watchdog.events import FileSystemEventHandler

StrPathLike: TypeAlias = str | bytes | bytearray | memoryview


class Watcher(FileSystemEventHandler):
    def __init__(self, extensions, enqueue_fn, queue) -> None:
        super().__init__()
        self.extensions = extensions
        self.enqueue = enqueue_fn
        self.queue = queue

    def on_created(self, event):
        self.handle(event)

    def on_moved(self, event):
        self.handle(event)

    def on_modified(self, event):
        self.handle(event)

    def handle(self, event):
        path: Path = self._normalize_path(event.src_path)
        can_process = self.check_processability(path)

        if can_process:
            self.enqueue(self.queue, path)

    def check_processability(self, path: Path) -> bool:
        if path.is_dir():
            return False

        if path.suffix.lower() not in self.extensions:
            return False
        return True

    def _normalize_path(self, src_path: StrPathLike) -> Path:
        if isinstance(src_path, bytes | bytearray | memoryview):
            src_path = bytes(src_path).decode(errors="surrogateescape")
        return Path(src_path)
