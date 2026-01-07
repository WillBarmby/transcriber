import argparse
from pathlib import Path


def directory(value: str) -> Path:
    try:
        path_value = Path(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not a valid path")
    if path_value.is_dir():
        return path_value
    else:
        raise argparse.ArgumentTypeError(f"{value} is not a valid directory")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--verbose", "-v", help="displays debugging log entries", action="store_true"
    )

    subparser = parser.add_subparsers(dest="command", required=True)

    file_parser = subparser.add_parser("file")
    file_parser.add_argument(
        "path", type=Path, help="the path to the audio file to transcribe"
    )

    batch_parser = subparser.add_parser("batch")
    batch_parser.add_argument(
        "directory",
        type=directory,
        help="the directory containing the files to transcribe",
    )

    watch_parser = subparser.add_parser("watch")
    watch_parser.add_argument(
        "directory",
        type=directory,
        help="the directory to watch for files to transcribe (default: ~/Downloads)",
        default=Path.home() / "Downloads",
    )

    return parser.parse_args()
