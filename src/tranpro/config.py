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
summary_context_tokens = 65536
summary_output_tokens = 4096

[profiles.openai]
transcription_provider = "openai"
transcription_model = "gpt-transcribe"
summary_provider = "openai"
summary_model = "gpt-6.1-terra"

[profiles.whisper]
transcription_provider = "whisper-cpp"
transcription_model = "/path/to/ggml-model.bin"
whisper_cli = "/path/to/whisper-cli"
language = "auto"
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

    def profile(self, name: str) -> dict[str, Any]:
        profiles = self.values.get("profiles")
        if not isinstance(profiles, dict):
            raise ConfigError(f"Config has no [profiles] table: {self.path}")
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            available = ", ".join(sorted(str(key) for key in profiles))
            raise ConfigError(
                f"Unknown profile {name!r}; available profiles: {available or 'none'}"
            )
        return dict(profile)

    @property
    def default_transcription_profile(self) -> str:
        defaults = self.values.get("defaults")
        if not isinstance(defaults, dict):
            raise ConfigError(f"Config has no [defaults] table: {self.path}")
        profile = defaults.get("transcription_profile")
        if not isinstance(profile, str) or not profile:
            raise ConfigError("defaults.transcription_profile must be a profile name")
        return profile

    @property
    def default_summary_profile(self) -> str:
        defaults = self.values.get("defaults")
        if not isinstance(defaults, dict):
            raise ConfigError(f"Config has no [defaults] table: {self.path}")
        profile = defaults.get("summary_profile")
        if not isinstance(profile, str) or not profile:
            raise ConfigError("defaults.summary_profile must be a profile name")
        return profile


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
