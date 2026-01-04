import time
import logging
from handlers.watchers import setup_observers
from config.paths import TEXT_DIR, ARCHIVE_DIR, FINAL_DIR
from core.logging_config import set_up_logging


def main(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    set_up_logging(level=level)

    for path in [FINAL_DIR, ARCHIVE_DIR, TEXT_DIR, FINAL_DIR]:
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
