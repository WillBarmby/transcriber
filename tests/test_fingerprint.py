import hashlib
from pathlib import Path

import pytest

from tranpro.library.fingerprint import fingerprint_file


def test_fingerprint_matches_sha256_across_small_chunks(tmp_path: Path) -> None:
    source = tmp_path / "recording.bin"
    content = b"five-hour-podcast-placeholder" * 100
    source.write_bytes(content)

    fingerprint = fingerprint_file(source, chunk_size=7)

    assert fingerprint == f"sha256:{hashlib.sha256(content).hexdigest()}"


def test_fingerprint_rejects_invalid_chunk_size(tmp_path: Path) -> None:
    source = tmp_path / "recording.bin"
    source.write_bytes(b"audio")

    with pytest.raises(ValueError, match="positive"):
        fingerprint_file(source, chunk_size=0)
