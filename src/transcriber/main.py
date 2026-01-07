import logging
import time
import argparse
from transcriber.core.logging import set_up_logging
from transcriber.core.cli import parse_args
from transcriber.pipelines.observers import setup_observers
from transcriber.config.paths import TEXT_DIR, ARCHIVE_DIR, FINAL_DIR


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


def run_file_mode(args: argparse.Namespace):
    return


def run_batch_mode(args: argparse.Namespace):
    return


def run_watch_mode(args: argparse.Namespace):

    for path in [FINAL_DIR, ARCHIVE_DIR, TEXT_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    observers = setup_observers()
    for observer in observers:
        observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for observer in observers:
            observer.stop()
    for observer in observers:
        observer.join()


if __name__ == "__main__":
    main()
