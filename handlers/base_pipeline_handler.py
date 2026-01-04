import subprocess
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from typing import TypeAlias
import shutil

StrPathLike: TypeAlias = str | bytes | bytearray | memoryview


class BasePipelineHandler(FileSystemEventHandler):
    extensions: set[str] = set()
    prompt: str = ""

    def __init__(self, watched_folder):
        self.seen_files: set[Path] = set()
        self.watched_folder = watched_folder

    # methods that could trigger when file is added
    def on_created(self, event):
        self.maybe_handle(event)

    def on_moved(self, event):
        self.maybe_handle(event)

    def on_modified(self, event):
        self.maybe_handle(event)

    def ask_user(self) -> bool:
        script = f'display dialog "{self.prompt}" buttons {{"No", "Yes"}} default button "Yes"'
        result = subprocess.run(
            [
                "osascript",
                "-e",
                script,
            ],
            capture_output=True,
            text=True,
        )
        if "button returned:No" in result.stdout:
            print("User Declined to move file through pipeline")
            return False
        return True

    def should_process(self, path: Path) -> bool:
        if path.suffix.lower() in self.extensions and path not in self.seen_files:
            return self.ask_user()
        return False

    def process(self, path: Path) -> Path | None:
        raise NotImplementedError

    def _normalize_path(self, src_path: StrPathLike) -> Path:
        if isinstance(src_path, bytes | bytearray | memoryview):
            src_path = bytes(src_path).decode(errors="surrogateescape")
        return Path(src_path)

    def maybe_handle(self, event):
        if event.is_directory:
            return
        path = self._normalize_path(event.src_path)
        self.seen_files.add(path)
        if self.should_process(path):
            self.process(path)

    def move_to_archive(self, file_path: Path, archive_dir: Path):
        final_path = archive_dir / file_path.name
        shutil.move(str(file_path), str(final_path))
