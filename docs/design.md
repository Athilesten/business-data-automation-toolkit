# Design and implementation

## Order-line schema

The six fields below are required. CSV must have exactly those column names, in any order. JSON property names are case-sensitive. Missing, null, empty, or whitespace-only values produce a field-specific missing code. Unknown JSON properties produce `EXTRA_FIELDS`.

| Field | Contract | Transformation |
| --- | --- | --- |
| `order_id` | `ORD-` plus 1–24 ASCII letters or digits | Trim, uppercase, deduplicate within batch |
| `order_date` | Real calendar date in `YYYY-MM-DD` | Trim and emit ISO date |
| `currency` | INR, USD, EUR | Trim and uppercase |
| `status` | PAID, PENDING, CANCELLED | Trim and uppercase |
| `quantity` | Integer 1–10,000, or a string of up to five digits | Emit integer |
| `unit_price` | Zero to 1,000,000, with up to two fractional places. Text values use plain decimal digits and an optional decimal point. JSON numeric values are interpreted by the decimal decoder. | Emit amount with two decimal places |
| `line_total` | Computed as quantity × unit price | Multiply integer minor units and emit amount with two decimal places |

CSV uses comma separators, double-quote escaping, and UTF-8 with optional BOM. A header-only CSV and an empty JSON array are valid empty sources. A blank physical CSV line outside a quoted field is a rejected record. A JSON array element of the wrong type produces `RECORD_TYPE`. A CSV row of the wrong width produces `CSV_WIDTH`. A bad header, parser-reported syntax error, duplicate JSON property, decoding failure, unreadable input, or exceeded cap aborts the batch.

## Architecture

```text
CLI and environment settings
  -> source preflight and bounded reads with SHA-256
  -> CSV or JSON parsing with source references
  -> shared validation and integer-money transformation
  -> batch duplicate detection and quality gate
  -> complete report bundle published under a unique run ID
```

- `config.py` validates environment values and defines the expected operator error type.
- `ingest.py` identifies sources, bounds input bytes, fingerprints the exact bytes consumed, and supplies parsed records with references.
- `validation.py` implements the schema, normalized data model, stable issue codes, and exact money conversions.
- `pipeline.py` writes accepted and rejected dispositions, tracks counters, applies the release gate, and publishes the staged bundle using a same-filesystem directory rename. It also verifies bundle hashes.
- `__main__.py` exposes the CLI, configures logging, and translates expected failures and quality decisions into exit codes.

## Research and decision log

| Increment | Decision and rationale | Review evidence |
| --- | --- | --- |
| 1 · Contract | Specify a six-field order-line schema, role ownership, and a measurable release gate before implementation. | [Requirements](requirements.md) |
| 2 · Runtime | Use built-in `csv`, `json`, `pathlib`, `logging`, and `unittest`. The workflow processes one row at a time after parsing and needs no DataFrame operations. The environment had Python and lacked pytest, so built-in tests keep the project directly runnable. | [CSV documentation](https://docs.python.org/3.14/library/csv.html), [JSON documentation](https://docs.python.org/3.14/library/json.html), [unittest documentation](https://docs.python.org/3.14/library/unittest.html) |
| 3 · Accounting | Decode JSON decimals exactly, convert prices into integer minor units, and aggregate by currency and status. Source priority is explicit. Claiming an ID only after validation lets a later valid row supersede an earlier invalid submission. | [Decimal documentation](https://docs.python.org/3.14/library/decimal.html), [Automated tests](../tests/test_toolkit.py) |
| 4 · Publication | Stage each run beneath the output root and publish the populated directory once reports and hashes exist. Unique run IDs allow independent retries and concurrent jobs. | [Rename documentation](https://docs.python.org/3.14/library/os.html#os.rename), [Automated tests](../tests/test_toolkit.py) |
| 5 · Measurement | Run dirty and corrected fixtures against the same gate. Automate repeatable evidence collection and measure two synthetic batch sizes with three trials each. | [Validation review](validation.md) |

## Data handling

Rejected values, input filenames, and absolute input paths are excluded from reports and normal logs. The reports use generated source IDs and fixed messages. Accepted text columns are restricted to a safe schema, so a formula-like order ID is rejected before it can reach an export. Accepted order IDs can still be confidential. Use an access-controlled output directory and apply the organization's retention policy to both inputs and outputs. The included examples use synthetic records.

The versioned manifest connects input bytes to report digests. Verification detects later changes to the report files when the manifest is trusted. The manifest is unsigned. Each run records UTC for ordering across machines. Preserve the numbered input list outside the toolkit to maintain provenance without publishing paths.

## Limitations and roadmap

| Current boundary | Next improvement for operational use |
| --- | --- |
| CSV is iterated from a bounded decoded snapshot. JSON arrays are parsed in memory. The duplicate index grows with accepted IDs. | Profile peak memory on representative files. For larger feeds, support streaming input and use a transactional index such as SQLite if memory becomes the bottleneck. |
| Deduplication covers one invocation. A retry creates another distinct run. | Introduce a batch identity at the import boundary, with a persistent registry and transactional publication to downstream systems. |
| First valid occurrence wins even if later valid values differ. Currency and status choices are built into the contract. | Require source data contracts and add explicit conflicting-payload review before expanding to more vendors. |
| Reports are local artifacts. Abrupt termination may leave a hidden staging directory. Publication has no power-loss durability guarantee. | Add scheduled-job monitoring, retention and stale-stage cleanup, durable storage, and a recovery exercise before production rollout. |
| Synthetic fixtures characterize correctness and local runtime. | Pilot with de-identified real exports, baseline analyst review time and correction turnaround, and set thresholds from measured false positives and downstream impact. |
