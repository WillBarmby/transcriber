"""User configuration loading and initialization."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tranpro.paths import AppPaths

DEFAULT_CONFIG = """\
version = 1

[defaults]
transcription_profile = "local"
summary_profile = "local"

[profiles.local]
transcription_provider = "parakeet-mlx"
transcription_model = "mlx-community/parakeet-tdt-0.6b-v3"
summary_provider = "ollama"
summary_model = "gemma4:12b"

[profiles.openai]
transcription_provider = "openai"
transcription_model = "gpt-transcribe"
summary_provider = "openai"
summary_model = "gpt-6.1-terra"
"""


class ConfigError(ValueError):
    """Raised when user configuration cannot be parsed or validated."""


@dataclass(frozen=True, slots=True)
class Config:
    """Parsed configuration plus its source path."""

    path: Path
    values: dict[str, Any]

    @classmethod
    def load(cls, paths: AppPaths | None = None) -> Config:
        app_paths = paths or AppPaths.for_user()
        path = app_paths.config_file
        if not path.exists():
            return cls(path=path, values=parse_config(DEFAULT_CONFIG, path=path))
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise ConfigError(f"Could not read {path}: {error}") from error
        return cls(path=path, values=parse_config(content, path=path))


def parse_config(content: str, *, path: Path) -> dict[str, Any]:
    try:
        values = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Invalid TOML in {path}: {error}") from error

    if values.get("version") != 1:
        raise ConfigError(f"Unsupported config version in {path}; expected version = 1")
    return values


def initialize_config(paths: AppPaths | None = None) -> tuple[Path, bool]:
    """Create the default config without overwriting an existing file."""

    app_paths = paths or AppPaths.for_user()
    app_paths.create_private_directories()
    path = app_paths.config_file
    if path.exists():
        return path, False
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    path.chmod(0o600)
    return path, True
