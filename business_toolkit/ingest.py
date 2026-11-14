"""Bounded input reads and parsing with source references."""

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path

from .config import ToolkitError

FIELDS = ("order_id", "order_date", "currency", "status", "quantity", "unit_price")
FIELD_SET = frozenset(FIELDS)


@dataclass(frozen=True)
class Source:
    source_id: str
    path: Path
    format: str

    def read(self, remaining_bytes):
        try:
            with self.path.open("rb") as stream:
                content = stream.read(remaining_bytes + 1)
        except OSError:
            raise ToolkitError(f"{self.source_id}: could not read input.") from None
        if len(content) > remaining_bytes:
            raise ToolkitError(f"{self.source_id}: batch byte limit exceeded.")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeError:
            raise ToolkitError(f"{self.source_id}: input must be UTF-8.") from None
        metadata = {
            "source_id": self.source_id,
            "format": self.format,
            "bytes": len(content),
            "sha256": sha256(content).hexdigest(),
        }
        return decoded, metadata

    def records(self, content):
        if self.format == "csv":
            yield from self._csv_records(content)
        else:
            yield from self._json_records(content)

    def _csv_records(self, content):
        with io.StringIO(content, newline="") as stream:
            reader = csv.reader(stream, strict=True)
            try:
                header = next(reader, None)
                if header is None or len(header) != len(FIELDS) or set(header) != FIELD_SET:
                    raise ToolkitError(f"{self.source_id}: CSV header does not match the schema.")
                while True:
                    first_line = reader.line_num + 1
                    cells = next(reader, None)
                    if cells is None:
                        break
                    if len(cells) == len(header):
                        yield first_line, dict(zip(header, cells)), None
                    else:
                        yield first_line, None, "CSV_WIDTH"
            except csv.Error:
                raise ToolkitError(f"{self.source_id}: malformed CSV near line {reader.line_num}.") from None

    def _json_records(self, content):
        try:
            array = json.loads(content, parse_float=Decimal, parse_constant=_invalid_constant,
                               object_pairs_hook=_unique_keys)
        except json.JSONDecodeError as error:
            raise ToolkitError(f"{self.source_id}: malformed JSON near line {error.lineno}.") from None
        except (ValueError, InvalidOperation, RecursionError):
            raise ToolkitError(f"{self.source_id}: unsupported JSON number, depth, or duplicate property.") from None
        if not isinstance(array, list):
            raise ToolkitError(f"{self.source_id}: JSON must contain an array.")
        for index, value in enumerate(array, start=1):
            yield index, value, None


def _invalid_constant(_value):
    raise ValueError("Invalid JSON numeric constant")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def prepare_sources(paths):
    if not 1 <= len(paths) <= 32:
        raise ToolkitError("Supply between 1 and 32 input files.")
    sources = []
    seen = set()
    for index, path in enumerate(paths, start=1):
        source_id = f"S{index:02d}"
        path = path.resolve()
        file_format = path.suffix.lower().removeprefix(".")
        if file_format not in {"csv", "json"}:
            raise ToolkitError(f"{source_id}: use a .csv or .json file.")
        if path in seen:
            raise ToolkitError(f"{source_id}: input path was already supplied.")
        if not path.is_file():
            raise ToolkitError(f"{source_id}: input must be a readable regular file.")
        seen.add(path)
        sources.append(Source(source_id, path, file_format))
    return sources
