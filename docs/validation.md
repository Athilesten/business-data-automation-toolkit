# Validation review

Evidence collected November 14, 2026 with Python 3.14.6 on Windows x64. Generate a fresh copy with `python scripts/reproduce.py runs/mentor-review`. [Raw timings and bundle paths](../evidence/2026-11-14/measurements.json)

## Acceptance checklist

| ID | Result | Evidence |
| --- | --- | --- |
| AC01 | Pass. One CLI run consumed CSV followed by JSON. | [Dirty run transcript](../evidence/2026-11-14/dirty-run.txt) |
| AC02 | Pass. All four seeded bad rows were quarantined, and all eight valid fixture rows were accepted. | [Mixed fixture assertions](../tests/test_toolkit.py), [dirty bundle location](../evidence/2026-11-14/measurements.json) |
| AC03 | Pass. Row dispositions reconcile. The dirty batch produced INR 419.00 in paid line value and USD 10.45 in paid line value. Tests check every currency and status group. | [Mixed fixture assertions](../tests/test_toolkit.py) |
| AC04 | Pass. Tests check exact and inclusive thresholds, empty and all-rejected batches, malformed files, configuration failures, and CLI exit statuses. | [Test transcript](../evidence/2026-11-14/tests.txt) |
| AC05 | Pass. The reproduction command created and verified two bundles in a fresh directory using only built-in modules. | [Dirty verification](../evidence/2026-11-14/dirty-verify.txt), [corrected verification](../evidence/2026-11-14/corrected-verify.txt) |
| AC06 | Pass for tested cases. Formula-like IDs are rejected, rejected values are omitted, tampering is detected against the original manifest, and partial failures preserve earlier bundles. | [Safety and recovery tests](../tests/test_toolkit.py) |
| AC07 | Pass. Before and after quality metrics and both synthetic workloads were captured. | [Measurement results](../evidence/2026-11-14/measurements.json) |

## Expected exception review

| Reference | Seeded condition | Result |
| --- | --- | --- |
| S01 line 4 | February 30 | `ORDER_DATE` |
| S01 line 7 | Zero quantity and excessive price precision | `QUANTITY\|UNIT_PRICE` |
| S02 item 1 | Duplicate of S01 line 3 after normalization | `DUPLICATE_ID` |
| S02 item 3 | Formula-like order ID | `ORDER_ID` |

Four rejected records produced five issue occurrences. The corrected fixture fixes three rows and removes one repeated export. The rejection rate fell from 33.33% to 0%, and the batch moved from HOLD to PASS at the same 5% gate. These are synthetic outcomes. The toolkit records the disposition and leaves source correction to the upstream owner.

## Workload measurements

| CSV rows | Seeded bad rows | Median CLI wall time | Median reported processing time |
| ---: | ---: | ---: | ---: |
| 1,000 | 10 | 0.384 s | 0.032 s |
| 10,000 | 100 | 0.620 s | 0.259 s |

Each median uses three fresh CLI launches. Wall time includes starting Python and publishing the artifacts. Processing time covers classification and report CSV writes inside the run. Both workloads stayed below the default rejection gate. This is a local CSV measurement with synthetic data. Peak memory, JSON throughput, production latency, and analyst time remain unmeasured.

## Review notes

The first test launch hit a restricted default temporary directory in the execution environment. The reproduction script directs subprocess temporary files into its writable evidence directory. The test fixture was also corrected to preserve CRLF bytes on Windows, and a test assumption about Python's JSON recursion limit was removed because parser behavior varies by version. The retained transcript records the final successful run of all 20 tests.
