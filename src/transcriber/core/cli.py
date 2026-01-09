import argparse
from pathlib import Path
from transcriber.config.paths import TEXT_DIR


def directory(value: str) -> Path:
    path_value = Path(value)
    if path_value.is_dir():
        return path_value
    else:
        raise argparse.ArgumentTypeError(f"{value} is not a valid directory")


def output_directory(value: str) -> Path:
    return Path(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--verbose", "-v", help="displays debugging log entries", action="store_true"
    )
    group.add_argument(
        "--quiet", "-q", help="hides debugging log entries", action="store_true"
    )

    subparser = parser.add_subparsers(dest="command", required=True)

    file_parser = subparser.add_parser("file")
    file_parser.add_argument(
        "path", type=Path, help="the path to the audio file to transcribe"
    )
    add_command_args(file_parser)

    batch_parser = subparser.add_parser("batch")
    batch_parser.add_argument(
        "directory",
        type=directory,
        help="the directory containing the files to transcribe",
    )
    add_command_args(batch_parser)

    watch_parser = subparser.add_parser("watch")
    watch_parser.add_argument(
        "directory",
        type=directory,
        nargs="?",
        help="the directory to watch for files to transcribe (default: ~/Downloads)",
        default=Path.home() / "Downloads",
    )
    add_command_args(watch_parser)

    return parser.parse_args()


def add_command_args(parser):
    add_output_arg(parser)
    add_auto_confirm(parser)
    add_summarize(parser)


def add_output_arg(parser):
    parser.add_argument(
        "--output",
        "-o",
        dest="output_dir",
        type=output_directory,
        help=f"output directory, default {TEXT_DIR}",
        default=TEXT_DIR,
    )


def add_auto_confirm(parser):
    parser.add_argument(
        "--autoconfirm",
        "-ac",
        help="Skips user confirmation panes",
        action="store_true",
    )


def add_summarize(parser):
    parser.add_argument(
        "--summarize",
        "-s",
        help="outputs addtional transcript summary and collated transcript + summary files",
        action="store_true",
    )
