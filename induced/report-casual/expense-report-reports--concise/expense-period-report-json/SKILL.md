---
name: expense-period-report-json
description: Build a period expense report in ExpenseDesk by downloading the period's expense lines from the Reports section and writing report.json with the counted claim ids, count, per-cost-center totals and grand total. Use for any "prepare the <month> expense report" request in ExpenseDesk, where deciding which claims count is the task.
---

# Prepare a period expense report (ExpenseDesk)

## Deliverable

Write `report.json` in the workspace as a single JSON object with exactly these
top-level fields:

| Field | Meaning |
| --- | --- |
| `period` | the reporting period as `"YYYY-MM"` |
| `claim_ids` | ids of the claims counted, as a list |
| `claim_count` | how many claims were counted |
| `by_cost_center` | object mapping each contributing cost center to its total |
| `grand_total` | the total amount to be reimbursed |

The instruction names the deliverable and its shape but never says which claims
count. Choosing the counted set correctly is the whole task: apply **all three**
inclusion rules below.

## Step 1 — Download the period's expense lines from the Reports section

1. Open the **Reports** section (the `Reports` navigation button in the header).
   The page shows an **Expense reports** panel with a **Period** combobox and a
   **Download CSV** link, plus an "IN THIS PERIOD" claim table.
2. Set the **Period** combobox to the requested period (format `YYYY-MM`, e.g.
   the option matching the month named in the instruction).
3. Click the **Download CSV** link and confirm a file was saved, named for the
   period (e.g. `expense-lines-<YYYY-MM>.csv`).
4. Treat the downloaded CSV as the authoritative source. It is **unprocessed**:
   it carries the period's line rows across every status and every category, and
   it contains only claims that have at least one expense line. The on-page
   "IN THIS PERIOD" table is a convenience view of the same claims and is only
   evidence for status/cost center, not for amounts.

Do not build the report by requesting the export URL directly or by reading any
hidden state: the download must come from the Reports section's own control.

## Step 2 — Decide which claims count (apply every rule, keep only rows passing all of them)

Work per claim (a claim's rows share `claim_id`, `status`, `category`,
`cost_center` and `period`), and keep a claim only when it passes all three
filters:

1. **Period** — the row's `period` equals the requested period. A claim whose
   month differs belongs to its own month's report and must not be counted in
   this one.
2. **Status** — the claim's `status` must be `approved`. Nothing counts until it
   is actually approved, so `pending_approval`, `Draft`, and any other
   not-yet-approved status are excluded even when the month matches.
3. **Category** — claims in the `Meals & Entertainment` category are never
   included in the period report, whatever their status; they are handled
   separately outside this report. An *approved* meals claim is therefore still
   excluded.

All three filters are required. Filtering on `status` alone (the most obvious
column) still keeps approved meals claims in and inflates `claim_count`,
`by_cost_center` and `grand_total`. Filtering on `status` and `category` alone
still pulls in another month's claims if the export carries them.

A claim with zero expense lines (for example a `Draft` claim shown on the page
with 0 lines) does not appear in the export at all; it cannot be counted and is
not a candidate for `claim_ids`.

## Step 3 — Compute the fields

- `period`: the requested period as `"YYYY-MM"`.
- `claim_ids`: the ids of the counted claims, as a JSON list ordered ascending
  by id.
- `claim_count`: the number of ids in `claim_ids`.
- `by_cost_center`: for each `cost_center` that has at least one counted claim,
  the sum of the counted line `amount` values belonging to that cost center.
  Include no cost center that has no counted claim, and omit nothing that does.
- `grand_total`: the sum of the counted line `amount` values, i.e. the total to
  be reimbursed. It must equal the sum of all `by_cost_center` values.

Amounts are cent-precise decimal values from the CSV. Emit them as JSON
*numbers* with the value the arithmetic gives — no currency symbol, no thousands
separator, no rounding to whole units - and keep whole-number results as numbers
(one decimal such as `960.0` or `42.1` is fine; the numeric value is what
matters). Write `claim_count` as a JSON number, not a string.

## Step 4 — Write report.json

Create the JSON object in the workspace under the name the instruction gives
(`report.json`) and make sure it parses as JSON.

## Step 5 — Verify before finishing

Read the written `report.json` back and check, against the downloaded CSV:

- every id in `claim_ids` is `approved`, matches the requested `period`, and is
  not `Meals & Entertainment`;
- no claim in the export that passes all three filters is missing from
  `claim_ids`;
- `claim_count` equals the length of `claim_ids`;
- `grand_total` equals the sum of the counted line amounts and the sum of the
  `by_cost_center` values;
- each `by_cost_center` entry equals the sum of the counted lines for that cost
  center.

Only then report the report as prepared.

## Recovery and limits

- **Requested period missing from the Period combobox**: the period cannot be
  exported. Stop and report that rather than substituting the nearest period.
- **Download produced no file, or an empty/partial file**: re-select the Period
  value and click **Download CSV** again; if it still fails, stop and report.
- **A counted claim shows an empty or `—` cost center**: state that in the
  result instead of inventing a bucket or silently dropping the claim's amount
  from `by_cost_center`; every cost-centre figure must remain reconcilable with
  `grand_total`.
- **Export missing the `status`, `category` or `period` column**: the inclusion
  rules cannot be applied. Stop and report the schema mismatch rather than
  guessing which claims were approved or non-meals.
