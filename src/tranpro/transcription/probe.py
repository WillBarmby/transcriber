"""Best-effort media metadata probing."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe_duration_ms(source: Path, *, executable: str = "ffprobe") -> int | None:
    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(source),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout)
        seconds = float(payload["format"]["duration"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return max(0, round(seconds * 1000))
