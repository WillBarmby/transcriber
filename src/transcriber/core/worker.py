import subprocess
import logging
from queue import Queue
from pathlib import Path
from transcriber.pipelines.base_pipeline import BasePipeline


class Sentinel:
    pass


logger = logging.getLogger(__name__)
STOP = Sentinel()


def worker_loop(queue: Queue, pipeline: BasePipeline):
    seen_files = set()
    while True:
        item = queue.get()
        if item is STOP:
            break
        if item in seen_files:
            continue
        seen_files.add(item)
        if not user_confirms():
            continue
        pipeline.process(item)


def user_confirms() -> bool:
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
        logger.info("User declined to move file through pipeline")
        return False
    return True
