import logging
from pathlib import Path
from dataclasses import dataclass
from enum import Enum, auto


class ProcessingStatus(Enum):
    SUCCESS = auto()
    SKIPPED = auto()
    FAILED = auto()


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


class BasePipeline:

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def process(self, path, output_dir: Path):
        result = self.run_pipeline(path, output_dir)
        self.process_result(result)

    def process_result(self, result: ProcessingResult):
        if result.status is ProcessingStatus.SUCCESS:
            self.logger.info(
                "Successfully processed %s, text_file at: %s",
                result.input_path.name,
                result.output_path,
            )
            return
        if result.status is ProcessingStatus.SKIPPED:
            self.logger.info("Skipped %s", result.input_path.name)
            return
        if result.status is ProcessingStatus.FAILED:
            self.logger.error(
                "Failed to process %s: %s", result.input_path.name, result.error
            )
            return

        raise RuntimeError(f"Unhandled ProcessingResult status: {result.status}")

    def run_pipeline(self, path: Path, output_dir: Path) -> ProcessingResult:
        raise NotImplementedError
