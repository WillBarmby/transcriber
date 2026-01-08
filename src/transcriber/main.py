import logging
import time
import argparse
import queue
import threading
import sys
from pathlib import Path
from watchdog.observers import Observer
from transcriber.core.logging import set_up_logging
from transcriber.core.cli import parse_args
from transcriber.pipelines.audio_pipeline import AudioPipeline
from transcriber.core.handlers import Watcher
from transcriber.core.worker import worker_loop, Sentinel, STOP
from transcriber.config.paths import FINAL_DIR, TEXT_DIR, ARCHIVE_DIR


logger = logging.getLogger(__name__)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}


def main() -> int:
    exit_code = 0
    args = parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.CRITICAL + 1
    set_up_logging(level=level)

    if args.command == "file":
        exit_code = run_file_mode(args)
    elif args.command == "batch":
        exit_code = run_batch_mode(args)
    elif args.command == "watch":
        exit_code = run_watch_mode(args)
    return exit_code


def enqueue(q: queue.Queue, path: Path | Sentinel):
    logger.debug("Enqueueing %s", path)
    q.put(path)


def run_file_mode(args: argparse.Namespace) -> int:
    path = args.path
    output_dir = ensure_output_dir(args.output_dir)
    pipeline = AudioPipeline()

    logger.info("Running in file mode on %s", path)
    q, worker = start_worker(pipeline, output_dir)

    enqueue(q, path)
    enqueue(q, STOP)
    worker.join()
    return 0


def run_batch_mode(args: argparse.Namespace) -> int:
    directory: Path = args.directory
    pipeline = AudioPipeline()
    output_dir = ensure_output_dir(args.output_dir)

    if not directory.exists():
        logger.error("Inputted directory does not exist: %s", directory)
        return 1

    logger.info("Running in batch mode on %s", directory)
    q, worker = start_worker(pipeline, output_dir)

    files_queued = False

    for path in sorted(directory.iterdir()):
        if path.suffix in pipeline.extensions:
            enqueue(q, path)
            files_queued = True
    if not files_queued:
        logger.info("No files ending in %s found in %s", pipeline.extensions, directory)
        return 0

    enqueue(q, STOP)
    worker.join()
    logger.debug("Worker thread shut down cleanly")

    return 0


def run_watch_mode(args: argparse.Namespace) -> int:
    directory = args.directory
    pipeline = AudioPipeline()
    output_dir = ensure_output_dir(args.output_dir)

    logger.info("Running in watch mode on %s", directory)
    q, worker = start_worker(pipeline, output_dir)

    for path in [directory, FINAL_DIR, ARCHIVE_DIR, TEXT_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    audio_observer = Observer()
    audio_event_handler = Watcher(
        extensions=AUDIO_EXTENSIONS, enqueue_fn=enqueue, queue=q
    )

    audio_observer.schedule(audio_event_handler, str(directory), recursive=False)
    logger.info("The audio event handler is now watching %s", directory)

    audio_observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        enqueue(q, STOP)
        logger.info("Shutting down watcher and worker")
        audio_observer.stop()
        worker.join()

    audio_observer.join()
    logger.debug("Worker thread shut down cleanly")

    return 0


def start_worker(
    pipeline: AudioPipeline, output_dir: Path
) -> tuple[queue.Queue, threading.Thread]:
    q = queue.Queue()
    worker = threading.Thread(
        target=worker_loop,
        args=(q, pipeline, output_dir),
        daemon=True,
    )
    worker.start()
    logger.debug("Worker thread started")
    return q, worker


def ensure_output_dir(path: Path) -> Path:
    if not path.exists():
        logger.info("Output directory did not exist; creating %s", path)
        path.mkdir(parents=True, exist_ok=True)
    return path


if __name__ == "__main__":
    sys.exit(main())
