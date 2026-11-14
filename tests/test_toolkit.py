"""Contract, safety, and CLI regression tests."""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

from business_toolkit.config import Settings, ToolkitError
from business_toolkit.ingest import FIELDS
from business_toolkit.pipeline import run, verify
from business_toolkit.validation import validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
GOOD = dict(order_id="ORD-1", order_date="2024-02-29", currency="usd",
            status="paid", quantity=3, unit_price="0.10")


class ValidationTests(unittest.TestCase):
    def test_normalization_and_exact_money(self):
        order, issues = validate(GOOD | {"order_id": " ord-a1 ", "unit_price": Decimal("0.10")})
        self.assertEqual(issues, [])
        self.assertEqual((order.order_id, order.status, order.currency), ("ORD-A1", "PAID", "USD"))
        self.assertEqual(order.total_cents, 30)

    def test_money_is_independent_of_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            order, issues = validate(GOOD | {"unit_price": "99999.99"})
        self.assertEqual(issues, [])
        self.assertEqual(order.total_cents, 29_999_997)

    def test_missing_and_multiple_issues(self):
        _, issues = validate(GOOD | {"currency": None, "status": "unknown", "quantity": True,
                                     "unit_price": "1.001", "order_date": "2025-02-29",
                                     "extra": "value"})
        self.assertEqual(issues, ["EXTRA_FIELDS", "ORDER_DATE", "MISSING_CURRENCY", "STATUS",
                                  "QUANTITY", "UNIT_PRICE"])

    def test_formula_and_unicode_ids_rejected(self):
        for token in ("=1+1", "ord-ſ", "+ORD-A", "ORD-A\nB"):
            with self.subTest(token=token):
                self.assertEqual(validate(GOOD | {"order_id": token})[1], ["ORDER_ID"])

    def test_numeric_boundaries(self):
        for changes in ({"quantity": 10_001}, {"quantity": Decimal("1.0")},
                        {"unit_price": "1000000.01"}, {"unit_price": "-0.00"}):
            with self.subTest(changes=changes):
                self.assertIsNone(validate(GOOD | changes)[0])
        order, issues = validate(GOOD | {"quantity": 10000, "unit_price": "1000000.00"})
        self.assertEqual(issues, [])
        self.assertEqual(order.total_cents, 1_000_000_000_000)


class RunTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.settings = Settings(self.root / "runs", 500, 1_000_000, 1000, "INFO")

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def json_records(self, records, name="source.json"):
        return self.write(name, json.dumps(records))

    def rows(self, path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def cli(self, *args, **settings):
        env = {name: value for name, value in os.environ.items() if not name.startswith("BDAT_")}
        env["BDAT_OUTPUT_DIR"] = str(self.settings.output_dir)
        env.update(settings)
        return subprocess.run([sys.executable, "-m", "business_toolkit", *map(str, args)],
                              cwd=ROOT, env=env, capture_output=True, text=True, check=False)

    def test_mixed_fixture_reconciles_and_redacts(self):
        folder, report = run([EXAMPLES / "web.csv", EXAMPLES / "marketplace_dirty.json"], self.settings)
        self.assertEqual((report["records"], report["accepted"], report["rejected"]), (12, 8, 4))
        self.assertEqual(report["decision"], "HOLD")
        totals = {(row["currency"], row["status"]): row["line_value"] for row in report["totals"]}
        self.assertEqual(totals, {("EUR", "CANCELLED"): "9.00", ("EUR", "PENDING"): "15.00",
                                  ("INR", "CANCELLED"): "99.99", ("INR", "PAID"): "419.00",
                                  ("USD", "PAID"): "10.45", ("USD", "PENDING"): "24.99"})
        rejected = self.rows(folder / "exceptions.csv")
        self.assertEqual([(row["source_id"], row["record_ref"], row["issue_codes"]) for row in rejected],
                         [("S01", "4", "ORDER_DATE"), ("S01", "7", "QUANTITY|UNIT_PRICE"),
                          ("S02", "1", "DUPLICATE_ID"), ("S02", "3", "ORDER_ID")])
        self.assertEqual((rejected[2]["duplicate_of_source_id"], rejected[2]["duplicate_of_record_ref"]),
                         ("S01", "3"))
        self.assertEqual(len(self.rows(folder / "accepted.csv")), 8)
        self.assertNotIn("REDACTED-FIXTURE", (folder / "exceptions.csv").read_text())
        verify(folder)

    def test_corrected_fixture_passes(self):
        _, report = run([EXAMPLES / "web_corrected.csv", EXAMPLES / "marketplace_corrected.json"],
                        self.settings)
        self.assertEqual((report["decision"], report["accepted"], report["rejected"]), ("PASS", 11, 0))

    def test_invalid_record_cannot_claim_id(self):
        source = self.json_records([GOOD | {"quantity": 0}, GOOD, GOOD])
        folder, report = run([source], self.settings)
        self.assertEqual(report["accepted"], 1)
        self.assertEqual(self.rows(folder / "exceptions.csv")[-1]["duplicate_of_record_ref"], "2")

    def test_threshold_is_inclusive_and_exact(self):
        sources = [self.json_records([GOOD, False, GOOD | {"order_id": "ORD-2"}])]
        for limit, decision in ((3333, "HOLD"), (3334, "PASS")):
            with self.subTest(limit=limit):
                _, report = run(sources, replace(self.settings, max_reject_bps=limit))
                self.assertEqual(report["decision"], decision)
        _, report = run([self.json_records([GOOD, False])],
                        replace(self.settings, max_reject_bps=5000))
        self.assertEqual(report["decision"], "PASS")

    def test_empty_and_all_invalid_are_held(self):
        for records in ([], [None]):
            _, report = run([self.json_records(records)], replace(self.settings, max_reject_bps=10000))
            self.assertEqual((report["decision"], report["reason"]), ("HOLD", "NO_ACCEPTED_RECORDS"))
            self.assertEqual(report["rejected_percent"], 100 if records else None)

    def test_csv_reordered_header_bom_and_multiline_positions(self):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        columns = FIELDS[::-1]
        writer.writerow(columns)
        writer.writerow([str((GOOD | {"order_id": "ORD-A\nB"})[column]) for column in columns])
        writer.writerow(["short"])
        writer.writerow([str(GOOD[column]) for column in columns])
        folder, _ = run([self.write("reordered.CSV", "\ufeff" + stream.getvalue())], self.settings)
        self.assertEqual([row["record_ref"] for row in self.rows(folder / "exceptions.csv")], ["2", "4"])
        self.assertEqual(self.rows(folder / "accepted.csv")[0]["record_ref"], "5")

    def test_bad_source_structures_defer_publication(self):
        previous, _ = run([self.json_records([GOOD])], self.settings)
        for name, content in (
            ("bad.csv", "x,y\n1,2\n"),
            ("quotes.csv", ",".join(FIELDS) + '\n"unclosed'),
            ("syntax.json", "[{"),
            ("object.json", "{}"),
            ("duplicate.json", '[{"qty":1,"qty":2}]'),
            ("nonfinite.json", "[NaN]"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ToolkitError):
                    run([self.json_records([GOOD]), self.write(name, content)], self.settings)
                self.assertEqual(list(self.settings.output_dir.iterdir()), [previous])

    def test_invalid_utf8_is_a_batch_error(self):
        source = self.root / "bad.json"
        source.write_bytes(b"\xff\xff")
        with self.assertRaisesRegex(ToolkitError, "UTF-8"):
            run([source], self.settings)
        self.assertEqual(list(self.settings.output_dir.iterdir()), [])

    def test_limits_count_across_files(self):
        first = self.json_records([GOOD])
        second = self.json_records([GOOD], "second.json")
        for overrides, message in (({"max_records": 1}, "record limit"),
                                   ({"max_batch_bytes": first.stat().st_size}, "byte limit")):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ToolkitError, message):
                run([first, second], replace(self.settings, **overrides))
        self.assertEqual(list(self.settings.output_dir.iterdir()), [])

    def test_same_file_twice_fails_preflight(self):
        path = self.json_records([GOOD])
        with self.assertRaisesRegex(ToolkitError, "already supplied"):
            run([path, path], self.settings)
        self.assertFalse(self.settings.output_dir.exists())

    def test_manifest_matches_inputs_and_detects_changed_output(self):
        import hashlib

        path = self.json_records([GOOD])
        folder, _ = run([path], self.settings)
        manifest = json.loads((folder / "manifest.json").read_text())
        self.assertEqual(manifest["inputs"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        (folder / "accepted.csv").write_text("changed")
        with self.assertRaisesRegex(ToolkitError, "checksum mismatch"):
            verify(folder)

    def test_missing_artifact_and_bad_manifest(self):
        folder, _ = run([self.json_records([GOOD])], self.settings)
        (folder / "exceptions.csv").unlink()
        with self.assertRaises(ToolkitError):
            verify(folder)
        (folder / "manifest.json").write_text('{"schema_version": 1, "artifact_sha256": []}')
        with self.assertRaises(ToolkitError):
            verify(folder)

    def test_report_failure_cleans_stage(self):
        source = self.json_records([GOOD])
        with patch("business_toolkit.pipeline._write_json", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                run([source], self.settings)
        self.assertEqual(list(self.settings.output_dir.iterdir()), [])

    def test_parallel_retries_publish_distinct_complete_runs(self):
        source = self.json_records([GOOD])
        with ThreadPoolExecutor(max_workers=2) as executor:
            folders = list(executor.map(lambda _: run([source], self.settings)[0], range(2)))
        self.assertEqual(len(set(folders)), 2)
        for folder in folders:
            verify(folder)
        self.assertEqual(set(self.settings.output_dir.iterdir()), set(folders))

    def test_cli_exit_codes_and_configuration(self):
        mixed = (EXAMPLES / "web.csv", EXAMPLES / "marketplace_dirty.json")
        held = self.cli("run", *mixed)
        self.assertEqual(held.returncode, 3, held.stderr)
        self.assertIn("HOLD", held.stdout)
        self.assertNotIn("REDACTED-FIXTURE", held.stdout + held.stderr)
        passed = self.cli("run", *mixed, BDAT_MAX_REJECT_BPS="4000", BDAT_LOG_LEVEL="WARNING")
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("PASS", passed.stdout)
        self.assertEqual(passed.stderr, "")
        path = passed.stdout.strip().rsplit(" | ", 1)[-1]
        self.assertEqual(self.cli("verify", path).returncode, 0)
        self.assertEqual(self.cli("run", *mixed, BDAT_MAX_REJECT_BPS="-1").returncode, 1)
        self.assertEqual(self.cli("run", "missing.json").returncode, 1)
        self.assertEqual(self.cli("run").returncode, 2)


if __name__ == "__main__":
    unittest.main()
