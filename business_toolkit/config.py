"""Read and validate the operator's environment configuration."""

import os
import re
from dataclasses import dataclass
from pathlib import Path


class ToolkitError(Exception):
    """An operator-facing error with a message safe for logs."""


@dataclass(frozen=True)
class Settings:
    output_dir: Path
    max_reject_bps: int
    max_batch_bytes: int
    max_records: int
    log_level: str

    @classmethod
    def from_env(cls):
        output = os.environ.get("BDAT_OUTPUT_DIR", "runs")
        if not output.strip():
            raise ToolkitError("BDAT_OUTPUT_DIR must be a nonempty path.")
        level = os.environ.get("BDAT_LOG_LEVEL", "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ToolkitError("BDAT_LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR.")
        return cls(
            Path(output),
            _integer("BDAT_MAX_REJECT_BPS", 500, 0, 10_000),
            _integer("BDAT_MAX_BATCH_BYTES", 8 * 1024 * 1024, 1, 64 * 1024 * 1024),
            _integer("BDAT_MAX_RECORDS", 50_000, 1, 250_000),
            level,
        )


def _integer(name, default, minimum, maximum):
    value = os.environ.get(name, str(default))
    if re.fullmatch(r"[0-9]{1,9}", value):
        number = int(value)
        if minimum <= number <= maximum:
            return number
    raise ToolkitError(f"{name} must be an integer from {minimum} through {maximum}.")
