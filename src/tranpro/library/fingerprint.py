"""Stable streaming fingerprints for source recordings."""

from __future__ import annotations

import hashlib
from pathlib import Path


def fingerprint_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a versioned SHA-256 fingerprint without loading the file in memory."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
