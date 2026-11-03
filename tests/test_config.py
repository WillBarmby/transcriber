from pathlib import Path

import pytest

from tranpro.config import Config, ConfigError, initialize_config
from tranpro.paths import AppPaths


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")


def test_load_uses_defaults_without_creating_files(app_paths: AppPaths) -> None:
    config = Config.load(app_paths)

    assert config.values["defaults"]["transcription_profile"] == "local"
    assert config.values["profiles"]["local"]["summary_provider"] == "ollama"
    assert not app_paths.data_dir.exists()


def test_profile_access_and_default_name(app_paths: AppPaths) -> None:
    config = Config.load(app_paths)

    assert config.default_transcription_profile == "local"
    assert config.default_summary_profile == "local"
    assert config.default_diarization_profile == "local"
    assert config.profile("local")["transcription_provider"] == "parakeet-mlx"
    assert config.profile("local")["diarization_provider"] == "nemotron-mlx"
    assert config.profile("local")["summary_context_tokens"] == 65_536


def test_unknown_profile_lists_available_names(app_paths: AppPaths) -> None:
    config = Config.load(app_paths)

    with pytest.raises(ConfigError, match="local, openai, whisper"):
        config.profile("missing")


def test_initialize_config_is_idempotent(app_paths: AppPaths) -> None:
    path, created = initialize_config(app_paths)
    original = path.read_text(encoding="utf-8")
    path.write_text(f"{original}\n# user edit\n", encoding="utf-8")

    repeated_path, repeated_created = initialize_config(app_paths)

    assert created is True
    assert repeated_path == path
    assert repeated_created is False
    assert path.read_text(encoding="utf-8").endswith("# user edit\n")
    assert app_paths.backup_dir.is_dir()
    assert app_paths.cache_dir.is_dir()


def test_load_rejects_unknown_config_version(app_paths: AppPaths) -> None:
    app_paths.data_dir.mkdir(parents=True)
    app_paths.config_file.write_text("version = 2\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="expected version = 1"):
        Config.load(app_paths)


def test_load_explains_invalid_toml(app_paths: AppPaths) -> None:
    app_paths.data_dir.mkdir(parents=True)
    app_paths.config_file.write_text("not valid = [", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid TOML"):
        Config.load(app_paths)
