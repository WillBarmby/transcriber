import logging
import time
import argparse
import queue
import threading
from pathlib import Path
from watchdog.observers import Observer
from transcriber.core.logging import set_up_logging
from transcriber.core.cli import parse_args
from transcriber.pipelines.audio_pipeline import AudioPipeline
from transcriber.core.handlers import Watcher
from transcriber.core.worker import worker_loop, Sentinel, STOP
from transcriber.config.paths import FINAL_DIR, TEXT_DIR, ARCHIVE_DIR


logger = logging.getLogger(__name__)


def main():
    args = parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    set_up_logging(level=level)
    if args.command == "file":
        run_file_mode(args)
    if args.command == "batch":
        run_batch_mode(args)
    if args.command == "watch":
        run_watch_mode(args)


def enqueue(q: queue.Queue, path: Path | Sentinel):
    q.put(path)


def run_file_mode(args: argparse.Namespace):
    path = args.path
    pipeline = AudioPipeline()
    q = queue.Queue()

    worker = threading.Thread(target=worker_loop, args=(q, pipeline), daemon=True)
    worker.start()

    enqueue(q, path)
    enqueue(q, STOP)
    worker.join()


def run_batch_mode(args: argparse.Namespace):
    return


def run_watch_mode(args: argparse.Namespace):
    q = queue.Queue()
    pipeline = AudioPipeline()
    worker = threading.Thread(target=worker_loop, args=(q, pipeline), daemon=True)

    INPUT_DIR = args.directory

    for path in [INPUT_DIR, FINAL_DIR, ARCHIVE_DIR, TEXT_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    audio_observer = Observer()
    audio_event_handler = Watcher(
        extensions={".mp3", ".wav", ".m4a"}, enqueue_fn=enqueue, queue=q
    )

    audio_observer.schedule(audio_event_handler, str(INPUT_DIR), recursive=False)
    logger.info("The audio event handler is now watching %s", INPUT_DIR)

    audio_observer.start()
    worker.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        enqueue(q, STOP)
        audio_observer.stop()
        worker.join()

    audio_observer.join()


if __name__ == "__main__":
    main()
