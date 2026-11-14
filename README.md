# Business Data Automation Toolkit

Validate CSV and JSON order-line exports before reconciliation. The order operations lead uses the batch decision to approve or hold a release. The analyst receives normalized order values and source references for exceptions.

The supplied mixed-format batch was **held** after the toolkit quarantined 4 of 12 rows. The corrected batch **passed** with 11 accepted rows and zero rejections. Both report bundles passed checksum verification. [Measurements and bundle locations](evidence/2026-11-14/measurements.json)

## Start here

Open a terminal in this project directory. Use Python 3.11 or later. The submitted run used Python 3.14.6 on Windows. Runtime, tests, and demo use the Python standard library.

```text
python --version
python -m business_toolkit --help
python -m business_toolkit run examples/web.csv examples/marketplace_dirty.json
python -m business_toolkit run examples/web_corrected.csv examples/marketplace_corrected.json
```

The first run intentionally returns **3** and prints its report directory. The second returns **0** with a separate directory. Use either printed path to verify the bundle. Replace `PATH_TO_RUN` with that path.

```text
python -m business_toolkit verify "PATH_TO_RUN"
python -m unittest discover -s tests -v
python scripts/reproduce.py runs/mentor-review
```

The reproduction script expects a new destination directory. It runs the tests, executes both sample batches, verifies their artifacts, and measures two synthetic workloads. Review [the live demo guide](docs/demo.md) for the expected findings.

## Read a run

| File | Use |
| --- | --- |
| `quality.json` | Check `decision` and `reason` first. Review counts, issue frequencies, source metrics, and exact totals grouped by currency and status. |
| `exceptions.csv` | Give source owners the source ID, row reference, and issue codes. Duplicate entries also identify the earlier accepted source and row. |
| `accepted.csv` | Import only from a passing run. Each row contains normalized fields and computed line value. |
| `manifest.json` | Match numbered sources to inputs by command-line order and SHA-256. Verify the three report files against their recorded hashes. |

`S01` refers to the first path on the command line. For CSV, `record_ref` is the starting physical line, with the header on line 1. For JSON it is the one-based array position. Keep the input path list and source files in your controlled workflow so analysts can resolve references.

| Exit status | Meaning |
| --- | --- |
| 0 | Batch passed or artifact verification succeeded |
| 1 | Configuration, input, I/O, or verification failed |
| 2 | Command-line usage error |
| 3 | Batch held with complete diagnostic reports |

## Configure a run

Set variables in the terminal that launches the CLI. For example, PowerShell accepts `$env:BDAT_OUTPUT_DIR = 'runs/reconciliation'`. A POSIX shell accepts `export BDAT_OUTPUT_DIR='runs/reconciliation'`. With defaults, the sample outcomes above are reproducible.

| Environment variable | Default | Accepted values |
| --- | --- | --- |
| `BDAT_OUTPUT_DIR` | `runs` | Nonempty writable directory path |
| `BDAT_MAX_REJECT_BPS` | `500` (5%) | 0–10,000 basis points, where 100 basis points equal 1 percentage point |
| `BDAT_MAX_BATCH_BYTES` | `8388608` (8 MiB) | 1–67,108,864 combined input bytes |
| `BDAT_MAX_RECORDS` | `50000` | 1–250,000 combined CSV records and JSON elements |
| `BDAT_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

A passing batch has at least one accepted line and a rejection rate at or below the limit. The gate compares integers so displayed rounding cannot affect the decision. Lower the limit to zero when every row must be valid. Cancelled orders remain visible in their own totals. These totals represent submitted order-line values.

## Submission materials

| Material | Location |
| --- | --- |
| Scope, stakeholders, and acceptance criteria | [Requirements](docs/requirements.md) |
| Schema, research, decisions, and roadmap | [Design and implementation](docs/design.md) |
| Review checklist and observed results | [Validation review](docs/validation.md) |
| Mentor walkthrough and viva prompts | [Live demo guide](docs/demo.md) |
| Reproducible evidence | [Test transcript](evidence/2026-11-14/tests.txt) and [measurements](evidence/2026-11-14/measurements.json) |
| Source and automated tests | `business_toolkit/` and `tests/` |
