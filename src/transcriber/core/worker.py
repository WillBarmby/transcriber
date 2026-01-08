import subprocess
import logging
from queue import Queue
from pathlib import Path
from dataclasses import dataclass
from transcriber.pipelines.base_pipeline import BasePipeline, ProcessingStatus


class Sentinel:
    pass


@dataclass(frozen=True)
class WorkerItem:
    input_path: Path
    autoconfirm: bool = False


logger = logging.getLogger(__name__)
STOP = Sentinel()


def worker_loop(
    queue: Queue[WorkerItem | Sentinel], pipeline: BasePipeline, output_dir: Path
):
    seen_paths: set[Path] = set()
    while True:
        item = queue.get()
        if isinstance(item, Sentinel):
            break

        if item.input_path in seen_paths:
            continue
        seen_paths.add(item.input_path)
        if not item.autoconfirm and not user_confirms(item.input_path):
            continue
        pipeline.process(item.input_path, output_dir)


def user_confirms(path: Path) -> bool:
    script = 'display dialog "move through pipeline?" buttons {"No", "Yes"} default button "Yes"'
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
        logger.info("user declined moving %s through pipeline", path.name)
        return False
    logger.info("user confirmed moving %s through pipeline", path.name)
    return True
