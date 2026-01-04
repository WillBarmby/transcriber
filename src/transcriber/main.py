import logging
import time
from transcriber.core.logging import set_up_logging
from transcriber.core.cli import parse_args
from transcriber.pipelines.observers import setup_observers
from transcriber.config.paths import TEXT_DIR, ARCHIVE_DIR, FINAL_DIR


def main(verbose: bool | None = None):
    args = parse_args()
    if verbose is None:
        verbose = args.verbose

    level = logging.DEBUG if verbose else logging.INFO
    set_up_logging(level=level)

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
