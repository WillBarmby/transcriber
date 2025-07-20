import time
from interface.watchers import setup_obervers
from config.paths import TEXT_DIR, ARCHIVE_DIR, FINAL_DIR

def main():
    for path in [FINAL_DIR, ARCHIVE_DIR, TEXT_DIR, FINAL_DIR]:
        path.mkdir(parents=True,exist_ok=True)

    observers = setup_obervers()
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