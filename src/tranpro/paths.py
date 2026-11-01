"""Cross-platform locations for tranpro's private application data."""

from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved user paths with no filesystem side effects."""

    data_dir: Path
    cache_dir: Path

    @classmethod
    def for_user(cls) -> "AppPaths":
        dirs = PlatformDirs(appname="tranpro", appauthor=False)
        return cls(
            data_dir=Path(dirs.user_data_dir),
            cache_dir=Path(dirs.user_cache_dir),
        )

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.toml"

    @property
    def database_file(self) -> Path:
        return self.data_dir / "library.sqlite3"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    def create_private_directories(self) -> None:
        """Create directories needed for application-owned state."""

        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
