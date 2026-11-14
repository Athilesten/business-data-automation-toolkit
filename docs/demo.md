# Mentor demo

**Five-minute live walkthrough** · retail order reconciliation · Arrowstack Python Development project

## 1. State the decision · 45 seconds

Three sales channels can deliver inconsistent exports. The operations lead needs to decide whether a batch can go to reconciliation. The analyst needs exact order values and a way to route exceptions back to source owners. A passing batch has an accepted row and at most 5% rejected records under the sample policy.

## 2. Run the mixed batch · 90 seconds

Run this command from the project root with default settings.

```text
python -m business_toolkit run examples/web.csv examples/marketplace_dirty.json
```

Expect `HOLD`, exit status 3, and a report directory. Open `quality.json` and point to 12 input rows, eight accepted rows and four rejected rows. Open `exceptions.csv` and follow the duplicate from JSON item 1 to CSV line 3. The exception report preserves the position required to locate the row in the source system.

## 3. Show correction and release · 60 seconds

```text
python -m business_toolkit run examples/web_corrected.csv examples/marketplace_corrected.json
python -m business_toolkit verify "PATH_TO_RUN"
```

Use the printed directory in the verification command. Expect `PASS` with 11 accepted lines and zero rejected lines. The corrected files represent upstream fixes and the removal of the repeated export. Show the currency and status groups in `quality.json` and point out the separate cancelled subtotal.

## 4. Discuss the controls · 90 seconds

Open the [test transcript](../evidence/2026-11-14/tests.txt) and [validation review](validation.md). Show that a file syntax failure leaves earlier published bundles intact. Explain how the normalized ID drives deterministic duplicate detection and integer minor units preserve exact money. The 10,000-row synthetic workload took about 0.62 seconds median end to end on the test machine.

## 5. Close with the next milestone · 35 seconds

A pilot would verify the schema against representative exports and measure analyst review time and source correction turnaround. At 10× volume, profile peak memory and JSON ingestion first. Use streaming plus a persistent duplicate index if those measurements justify the additional infrastructure.

## Viva prompts

- **What drove the largest design decision?** File-level failures stop publication when records cannot be enumerated reliably. Row-level errors yield actionable references and a measurable quality gate.
- **How did you validate accuracy?** The dirty fixture independently specifies every expected exception and all six currency/status totals. Regression tests cover exact money, rate boundaries, malformed inputs, concurrent runs, and report integrity.
- **What required the most problem-solving?** Duplicate IDs must be assigned only after validation. Otherwise an invalid record can block its corrected equivalent. The test places an invalid row before two rows with the same ID and checks that the second row wins.
- **How would you explain the result to a nontechnical stakeholder?** The tool checks each order line, sends questionable entries back with a location and reason, and tells operations whether the batch meets its release policy.

**Portfolio summary.** Built a Python order-export quality gate with CSV and JSON ingestion, exact currency-separated reconciliation, and auditable exception reporting. Quarantined all four seeded defects and verified the workflow with 20 automated tests.
