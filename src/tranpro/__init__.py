"""tranpro: a local-first transcript library."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tranpro")
except PackageNotFoundError:  # pragma: no cover - only outside packaging
    __version__ = "0+unknown"

__all__ = ["__version__"]
