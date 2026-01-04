import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verbose", "-v", help="displays debugging log entries", action="store_true"
    )
    return parser.parse_args()
