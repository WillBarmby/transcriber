import subprocess
import shutil
import logging
from pathlib import Path
from typing import TypeAlias
from dataclasses import dataclass
from enum import Enum, auto
from watchdog.events import FileSystemEventHandler


class ProcessingStatus(Enum):
    SUCCESS = auto()
    SKIPPED = auto()
    FAILED = auto()


# Intending this to be result of the process method for better error handling and structural soundness
@dataclass
class ProcessingResult:
    status: ProcessingStatus
    input_path: Path
    output_path: Path | None = None
    error: Exception | None = None

    def __post_init__(self):
        if self.status is ProcessingStatus.SUCCESS:
            assert self.output_path is not None
            assert self.error is None


StrPathLike: TypeAlias = str | bytes | bytearray | memoryview


class BasePipeline(FileSystemEventHandler):
    extensions: set[str] = set()
    prompt: str = ""

    def __init__(self, watched_folder):
        self.seen_files: set[Path] = set()
        self.watched_folder = watched_folder
        self.logger = logging.getLogger(self.__class__.__name__)

    # methods that could trigger when file is added
    def on_created(self, event):
        self.handle(event)

    def on_moved(self, event):
        self.handle(event)

    def on_modified(self, event):
        self.handle(event)

    def handle(self, event):
        path: Path = self._normalize_path(event.src_path)
        can_process = self.check_processability(path)

        if not can_process:
            return

        self.seen_files.add(path)

        if self.user_confirms():
            result = self.process(path)
            self.handle_result(result)

    def handle_result(self, result: ProcessingResult):
        if result.status is ProcessingStatus.SUCCESS:
            self.logger.info("Successfully processed %s", result.input_path.name)
            return
        if result.status is ProcessingStatus.SKIPPED:
            self.logger.info("Skipped %s", result.input_path.name)
            return
        if result.status is ProcessingStatus.FAILED:
            self.logger.error(
                "Failed to process %s: %s", result.input_path.name, result.error
            )
            return

        raise RuntimeError(f"Unhandled ProcessingResult status: {result.status}")

    def process(self, path: Path) -> ProcessingResult:
        raise NotImplementedError

    def user_confirms(self) -> bool:
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
            self.logger.info("User declined to move file through pipeline")
            return False
        return True

    def check_processability(self, path: Path) -> bool:
        if path.is_dir():
            return False
        if path in self.seen_files:
            return False
        if path.suffix.lower() not in self.extensions:
            return False
        return True

    def _normalize_path(self, src_path: StrPathLike) -> Path:
        if isinstance(src_path, bytes | bytearray | memoryview):
            src_path = bytes(src_path).decode(errors="surrogateescape")
        return Path(src_path)

    def move_to_archive(self, file_path: Path, archive_dir: Path):
        final_path = archive_dir / file_path.name
        shutil.move(str(file_path), str(final_path))
