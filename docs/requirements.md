# Requirements and acceptance criteria

## Business problem

A retail operation receives daily order exports from a web store, a marketplace, and point-of-sale systems. Reviewers need a reliable batch before reconciling order values. Manual checks for duplicate exports, malformed rows, and inconsistent money formats make it difficult to tell whether a file is ready.

The **order operations lead** owns the release decision. A **reconciliation analyst** reviews totals by currency and status and uses row references to request corrections from source owners. The workflow covers one batch on one machine. Scope includes order lines with one unique ID per line, validation, normalization, batch duplicate detection, and local reports. Upstream record editing, currency conversion, tax, refunds, accounting recognition, and cross-batch deduplication require separate controls.

## Input and output contract

- The operator passes one to 32 CSV or JSON file paths in a declared priority order. Use UTF-8 with optional BOM, comma-delimited CSV with a header, or a JSON array of objects. Identical resolved file paths fail preflight. Total bytes and records are bounded by environment configuration.
- The accepted dataset contains normalized inputs plus computed line value and source position. Rejections contain source positions and stable issue codes with fixed messages. Run metrics include an exact rate gate, issue counts, and currency/status totals. A manifest connects source content hashes to output hashes.
- Unrecoverable file errors fail the batch before publication. Recoverable record errors are isolated and counted. Each input record has exactly one disposition. A record can have several issues. The first valid occurrence of an ID wins in input order. Empty batches require review.
- A batch at or below the configured rejection-rate limit passes when it contains an accepted row. A batch above the limit or with no accepted rows is held. Held reports are published for diagnosis. Downstream consumers use the exit status and the decision in `quality.json` before import.

## Success measures

| ID | Acceptance check | Target |
| --- | --- | --- |
| AC01 | Both formats enter through the same CLI and validation rules | One mixed-format run, independently checked |
| AC02 | Seeded invalid and duplicate records are quarantined with row references | 100% detection and zero false rejects on the supplied fixture |
| AC03 | Row dispositions and monetary aggregates reconcile | Counts balance and exact totals match fixture expectations |
| AC04 | Health status correctly handles rate boundaries, empty data, and hard failures | Pass, hold, and failure exit behavior covered by automated tests |
| AC05 | Operators can reproduce the result and verify artifact integrity | Fresh-folder walkthrough on Python with built-in tests, checksums, and saved evidence |
| AC06 | Privacy and integrity controls limit exposure during normal operation | Report schema omits raw rejected values, safe output fields, and no partial published batch on handled failure |
| AC07 | Monitoring exposes the quality change and test workload | Measured dirty and corrected fixture runs plus 1,000 and 10,000 record synthetic runs |

The performance runs characterize local behavior. A time-savings claim would require measuring the analyst's existing workflow and this workflow with real operators. The business benefit demonstrated here is the number of seeded bad records prevented from reaching the release candidate.
