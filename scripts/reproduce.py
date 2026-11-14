"""Reproduce the mentor demo, test transcript, and synthetic workload measurements."""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]


def invoke(args, output, expected_status, env, **overrides):
    command = [sys.executable, *args]
    result = subprocess.run(command, cwd=ROOT, env=env | overrides, encoding="utf-8",
                            capture_output=True, check=False)
    if output is not None:
        output.write_text(
            f"Exit status: {result.returncode}\n\nSTDOUT\n{result.stdout}\nSTDERR\n{result.stderr}",
            encoding="utf-8",
        )
    if result.returncode != expected_status:
        raise SystemExit(f"Unexpected exit status for {args!r}: {result.returncode}\n{result.stderr}")


def load_run(directory):
    (run_dir,) = (item for item in directory.iterdir() if not item.name.startswith("."))
    return run_dir, json.loads((run_dir / "quality.json").read_text(encoding="utf-8"))


def measure(batch_size, working_dir, env):
    path = working_dir / "synthetic.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("order_id", "order_date", "currency", "status", "quantity", "unit_price"))
        for index in range(1, batch_size + 1):
            writer.writerow((f"ORD-B{index}", "2026-11-10", "INR", "PAID",
                             0 if index % 100 == 0 else 1, "10.25"))
    timings = []
    for trial in range(3):
        destination = working_dir / f"benchmark-{batch_size}-{trial}"
        started = perf_counter()
        invoke(["-m", "business_toolkit", "run", str(path)], None, 0, env,
               BDAT_OUTPUT_DIR=str(destination), BDAT_LOG_LEVEL="WARNING")
        wall = perf_counter() - started
        _, report = load_run(destination)
        rejected = batch_size // 100
        if (report["accepted"], report["rejected"]) != (batch_size - rejected, rejected):
            raise SystemExit("Synthetic workload did not reconcile.")
        timings.append({"wall_seconds": round(wall, 6),
                        "processing_seconds": report["processing_seconds"]})
    return {
        "records": batch_size,
        "rejected": rejected,
        "input_bytes": path.stat().st_size,
        "trials": timings,
        "median_wall_seconds": median(trial["wall_seconds"] for trial in timings),
        "median_processing_seconds": median(trial["processing_seconds"] for trial in timings),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New evidence directory")
    args = parser.parse_args()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    base_env = {key: value for key, value in os.environ.items() if not key.startswith("BDAT_")}
    with tempfile.TemporaryDirectory(prefix=".work-", dir=destination) as temporary:
        work = Path(temporary)
        env = base_env | {"TEMP": str(work), "TMP": str(work), "TMPDIR": str(work),
                          "PYTHONIOENCODING": "utf-8"}
        invoke(["-m", "unittest", "discover", "-s", "tests", "-v"], destination / "tests.txt", 0, env)
        comparison = {}
        for label, filenames, expected, counts in (
            ("dirty", ("web.csv", "marketplace_dirty.json"), 3, (12, 8, 4)),
            ("corrected", ("web_corrected.csv", "marketplace_corrected.json"), 0, (11, 11, 0)),
        ):
            folder = destination / label
            invoke(["-m", "business_toolkit", "run", *(f"examples/{name}" for name in filenames)],
                   destination / f"{label}-run.txt", expected, env, BDAT_OUTPUT_DIR=str(folder))
            run_dir, report = load_run(folder)
            if tuple(report[field] for field in ("records", "accepted", "rejected")) != counts:
                raise SystemExit(f"Unexpected fixture counts in the {label} case.")
            invoke(["-m", "business_toolkit", "verify", str(run_dir)],
                   destination / f"{label}-verify.txt", 0, env)
            comparison[label] = {
                **{field: report[field] for field in (
                    "decision", "records", "accepted", "rejected", "rejected_percent")},
                "bundle": run_dir.relative_to(destination).as_posix(),
            }
        evidence = {
            "environment": {"python": platform.python_version(), "os": platform.system(),
                            "machine": platform.machine()},
            "fixture_comparison": comparison,
            "benchmark": [measure(size, work, env) for size in (1000, 10_000)],
        }
        (destination / "measurements.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8",
        )
    print(f"Demo and validation evidence written to {destination}")


if __name__ == "__main__":
    main()
