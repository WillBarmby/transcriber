from enum import Enum, auto
from dataclasses import dataclass
from pathlib import Path


class Sentinel:
    pass


class Artifact(Enum):
    TRANSCRIPT = auto()
    SUMMARY = auto()
    COLLATED_FILE = auto()


class ProcessingStatus(Enum):
    SUCCESS = auto()
    SKIPPED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class WorkerItem:
    input_path: Path
    requested_outputs: frozenset[Artifact]
    autoconfirm: bool = False


@dataclass(frozen=True)
class ProcessingRequest:
    input_path: Path
    output_dir: Path
    requested_outputs: frozenset[Artifact]


@dataclass
class ProcessingResult:
    status: ProcessingStatus
    input_path: Path
    output_path: Path | None = None
    error: Exception | None = None

    def __post_init__(self):
        if self.status is ProcessingStatus.SUCCESS:
            assert self.output_path is not None
            assert self.error is None
