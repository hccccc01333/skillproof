---
name: expense-period-report
description: Build a JSON expense/reimbursement report for one reporting period in ExpenseDesk by downloading the period's expense-line export from the Reports section and aggregating only the claims that count (approved claims, excluding drafts and unapproved ones). Use when asked to prepare a period report (e.g. "prepare the <month> <year> expense report and save it as report.json") with fields period, claim_ids, claim_count, by_cost_center and grand_total.
---

# ExpenseDesk period report

Produce one JSON file in the workspace that reports, for a single requested period
(`YYYY-MM`), which claims were counted, how many, the total per cost center, and the
grand total to be reimbursed.

The task never states which claims count; that is the whole job. Decide it from the
export's `status` column (rule in step 4), never from guesswork.

## Inputs

- Reporting period, given as `YYYY-MM` (the demonstration used `2026-05`).
- Output path/filename for the JSON (the demonstration used `report.json` in the workspace).

## Workflow

### 1. Open the Reports section
ExpenseDesk opens on the **Claims** view. In the header section navigation, click
**Reports**. The view is identified by the heading **"Expense reports"**, an explanatory
line stating that the export is unprocessed and contains drafts, unapproved claims and
every category, a **Period** selector, a **Download CSV** control, and an
**"IN THIS PERIOD"** table listing each claim with its claim name, `STATUS`, `CATEGORY`,
`COST CENTER` and `LINES` count.

If the Reports view does not render, click **Reports** again rather than typing a URL.

### 2. Select the requested period
Set the **Period** combobox (`report-period`) to exactly the requested `YYYY-MM`. Only
periods that exist in the data are listed; if the requested period is absent, stop and
report that the period has no data instead of substituting another period.

After the selection settles, confirm the **"IN THIS PERIOD"** table below shows the rows
for that period (its claim list and line counts change with the selection).

### 3. Download the period's expense lines
Click **Download CSV** (the link immediately to the right of the **Period** selector; its
target is the period-scoped export, e.g. `/api/reports/export.csv?period=<YYYY-MM>`).
The download is saved as `expense-lines-<YYYY-MM>.csv`.

Recovery: if no file appears, click **Download CSV** once more and wait; confirm the
Period selector still shows the requested period before retrying, because the export
always follows the currently selected period. If a stale export for a different period is
present, download again after re-selecting the requested period rather than reusing it.

### 4. Decide which claims count
Read the downloaded CSV. Header:

`claim_id,claim_title,period,status,category,cost_center,line_description,amount`

One row per expense line; a claim can span several rows, and `amount` is the line amount.

Counting rule:

- A claim counts when its `status` is `approved`.
- Exclude every claim whose `status` is any non-approved value — `draft`,
  `pending_approval`, or anything else. This is what the Reports page means when it says
  the export is unprocessed and contains drafts and unapproved claims.
- Include every line of a counted claim, even lines with no attached receipt: a missing
  receipt does not remove a line from reimbursement.
- Keep only rows whose `period` equals the requested period, even though the export was
  requested for that period.
- A claim displayed with a **LINES** count of `0` contributes no rows and no amount.

Cross-check the counted set against the visible **"IN THIS PERIOD"** table: its `STATUS`
column shows the same statuses as the CSV re-check, and every claim you exclude should be
non-approved there. The number of counted claims must not exceed the number of rows in
that table.

### 5. Compute the totals
For the counted rows only:

- Claim amount = sum of that claim's counted line `amount` values.
- `by_cost_center` = for each `cost_center` appearing in the counted rows, the sum of the
  counted line amounts with that cost center.
- `grand_total` = sum of all counted line amounts; it must equal the sum of the
  `by_cost_center` values.
- Round money to 2 decimals and keep them as JSON numbers (not strings).

### 6. Write the JSON report
Write the file at the requested output path in the workspace. It is a single JSON object
with exactly these fields:

```json
{
  "period": "<YYYY-MM>",
  "claim_ids": ["<id>", "<id>"],
  "claim_count": 0,
  "by_cost_center": {"<COST-CENTER>": 0.0},
  "grand_total": 0.0
}
```

- `period` — the requested reporting period as `YYYY-MM`.
- `claim_ids` — the ids of the counted claims, one entry per counted claim (list them in
  ascending id order for a stable result).
- `claim_count` — the number of counted claims; it must equal `len(claim_ids)`.
- `by_cost_center` — one key per cost center present among the counted claims.
- `grand_total` — the total amount to be reimbursed.

Do not create, edit or resolve any claim in the application: this task only reads the
period's data and writes one workspace file.

### 7. Verify before finishing
Re-open the written file and confirm all of:

1. `period` equals the requested `YYYY-MM`.
2. Every id in `claim_ids` has status `approved` in the downloaded CSV and belongs to the
   requested period; no non-approved claim id appears.
3. `claim_count` equals the length of `claim_ids` and equals the number of approved claims
   you identified in the CSV.
4. The sum of all values in `by_cost_center` equals `grand_total`, and `grand_total` equals
   the sum of the counted line amounts.

If any check fails, recompute from the CSV and rewrite the file rather than adjusting the
numbers by hand.

Then run the bundled `verify.json` checks against the Reports page and the workspace file
before declaring the task complete. Its deliverable-content check is declared
`unverifiable` because the assertion language reads page text only, so treat check 1–4
above as the authoritative test of the written report.
