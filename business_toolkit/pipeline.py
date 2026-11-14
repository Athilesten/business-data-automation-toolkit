"""Classify an order batch and publish a complete, auditable run."""

import csv
import json
import logging
from collections import Counter
from datetime import UTC, datetime
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from . import __version__
from .config import ToolkitError
from .ingest import prepare_sources
from .validation import ISSUES, money, validate

LOG = logging.getLogger(__name__)
ACCEPTED_FIELDS = (
    "source_id", "record_ref", "order_id", "order_date", "currency", "status",
    "quantity", "unit_price", "line_total",
)
REJECTED_FIELDS = (
    "source_id", "record_ref", "issue_codes", "issue_messages",
    "duplicate_of_source_id", "duplicate_of_record_ref",
)
ARTIFACTS = ("accepted.csv", "exceptions.csv", "quality.json")


def _write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _classify(sources, settings, stage):
    started = perf_counter()
    seen = {}
    issue_counts = Counter()
    line_counts = Counter()
    totals = Counter()
    source_reports = []
    total = accepted = 0
    remaining_bytes = settings.max_batch_bytes

    with (
        (stage / "accepted.csv").open("w", encoding="utf-8", newline="") as accepted_file,
        (stage / "exceptions.csv").open("w", encoding="utf-8", newline="") as rejected_file,
    ):
        accepted_writer = csv.writer(accepted_file)
        rejected_writer = csv.writer(rejected_file)
        accepted_writer.writerow(ACCEPTED_FIELDS)
        rejected_writer.writerow(REJECTED_FIELDS)
        for source in sources:
            content, report = source.read(remaining_bytes)
            remaining_bytes -= report["bytes"]
            source_total = source_accepted = 0
            for reference, record, parse_issue in source.records(content):
                total += 1
                source_total += 1
                if total > settings.max_records:
                    raise ToolkitError(f"{source.source_id}: batch record limit exceeded.")
                order, issues = (None, [parse_issue]) if parse_issue else validate(record)
                duplicate_of = ("", "")
                if order is not None and order.order_id in seen:
                    issues = ["DUPLICATE_ID"]
                    duplicate_of = seen[order.order_id]
                if issues:
                    issue_counts.update(issues)
                    rejected_writer.writerow((
                        source.source_id, reference, "|".join(issues),
                        " | ".join(ISSUES[code] for code in issues), *duplicate_of,
                    ))
                    continue
                seen[order.order_id] = (source.source_id, reference)
                accepted += 1
                source_accepted += 1
                group = (order.currency, order.status)
                line_counts[group] += 1
                totals[group] += order.total_cents
                accepted_writer.writerow((
                    source.source_id, reference, order.order_id, order.order_date,
                    order.currency, order.status, order.quantity,
                    money(order.unit_price_cents), money(order.total_cents),
                ))
            report.update(records=source_total, accepted=source_accepted,
                          rejected=source_total - source_accepted)
            source_reports.append(report)
            LOG.info("source=%s records=%s accepted=%s rejected=%s", source.source_id,
                     source_total, source_accepted, source_total - source_accepted)

    rejected = total - accepted
    if accepted == 0:
        decision, reason = "HOLD", "NO_ACCEPTED_RECORDS"
    elif rejected * 10_000 > settings.max_reject_bps * total:
        decision, reason = "HOLD", "REJECT_RATE_EXCEEDED"
    else:
        decision, reason = "PASS", "WITHIN_LIMIT"
    return {
        "decision": decision,
        "reason": reason,
        "records": total,
        "accepted": accepted,
        "rejected": rejected,
        "rejected_percent": round(rejected * 100 / total, 4) if total else None,
        "max_reject_bps": settings.max_reject_bps,
        "issues": dict(issue_counts),
        "totals": [
            {"currency": currency, "status": status, "lines": line_counts[currency, status],
             "line_value": money(totals[currency, status])}
            for currency, status in sorted(totals)
        ],
        "sources": source_reports,
        "processing_seconds": round(perf_counter() - started, 6),
    }


def run(paths, settings):
    sources = prepare_sources(paths)
    timestamp = datetime.now(UTC)
    run_id = f"{timestamp:%Y%m%dT%H%M%SZ}-{uuid4().hex}"
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    destination = settings.output_dir / run_id
    with TemporaryDirectory(prefix=".staging-", dir=settings.output_dir) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        report = _classify(sources, settings, stage)
        _write_json(stage / "quality.json", report)
        manifest = {
            "schema_version": 1,
            "toolkit_version": __version__,
            "run_id": run_id,
            "started_at_utc": timestamp.isoformat(),
            "inputs": [
                {field: source[field] for field in ("source_id", "format", "bytes", "sha256")}
                for source in report["sources"]
            ],
            "artifact_sha256": {name: _digest(stage / name) for name in ARTIFACTS},
        }
        _write_json(stage / "manifest.json", manifest)
        stage.rename(destination)
    return destination, report


def verify(run_dir):
    """Verify the required artifact digests against the run manifest."""
    try:
        with (run_dir / "manifest.json").open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        expected = manifest["artifact_sha256"]
        if (manifest["schema_version"] != 1 or not isinstance(expected, dict)
                or expected.keys() != set(ARTIFACTS)):
            raise ToolkitError("Manifest schema is unsupported or incomplete.")
        for name in ARTIFACTS:
            if _digest(run_dir / name) != expected[name]:
                raise ToolkitError(f"Artifact checksum mismatch: {name}.")
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ToolkitError("Could not read the run manifest or its required artifacts.") from None
