import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", help="displays debugging log entries")
    return parser
