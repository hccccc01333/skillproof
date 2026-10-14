---
name: expense-period-report
description: Build a period expense report (report.json) for a requested calendar month from the ExpenseDesk web application - open Reports, set the Period, export the period CSV, filter out non-approved claims and all Meals & Entertainment lines, aggregate by cost center, and save the JSON summary. Use whenever the task asks for a monthly/period expense report, reimbursement summary, or spend-by-cost-center file from ExpenseDesk.
---

# Period expense report from ExpenseDesk

Produce a JSON summary of the reimbursable expenses in one requested calendar
month and save it as `report.json` in the workspace. All data comes from the
ExpenseDesk web UI and its period CSV export; do not invent or look up data
anywhere else.

## Inputs

- The requested period, given as a month in the task (for example "May 2026").
  Convert it to the application's period value `YYYY-MM` (May 2026 -> `2026-05`).
- The application URL from the task (the ExpenseDesk app).

## Procedure

1. Open the ExpenseDesk URL in the browser and wait for the claims list to load.
2. In the top navigation (the `Sections` nav, next to `Claims`), activate the
   **Reports** button. The `Expense reports` page opens.
3. Set the **Period** combobox (the `select` labelled `Period` in the report
   toolbar) to the requested month in `YYYY-MM` form. If the wanted value is not
   in the list, pick the listed option for the requested month; do not fall back
   to a different month.
4. Confirm the **IN THIS PERIOD** table below reloaded and now lists claims whose
   titles belong to the requested month, with their `Status`, `Category`,
   `Cost center` and `Lines` columns. Use this table as the on-screen reference
   for the period.
5. Activate the **Download CSV** link in the report toolbar and wait for the file
   to land in the workspace. The link exports the rows for the currently selected
   period (its target encodes the period, e.g. `?period=YYYY-MM`). Note the tiny
   print under the page title: the export is ungrouped and contains drafts,
   unapproved claims and every category, so the filtering below is required.
6. Filter the exported claim-line rows. Keep a row only if **all** of these hold:
   - `status` is exactly `approved` - nothing counts until it is approved, so
     drop `pending_approval`, `draft`, and any other status value;
   - `category` is **not** `Meals & Entertainment` - every meals/food line is
     excluded from the period report regardless of its approval status or
     amount, because meals are handled by a separate process outside this report;
   - the row's `period` equals the requested `YYYY-MM` - the export is normally
     already scoped to the period, but drop any stray row from another month
     (for example an April claim lingering in the claims list).
7. Compute the summary from the kept rows:
   - `claim_ids`: the distinct `claim_id` values of the kept rows, in the order
     they appear in the export. Count a multi-line claim once.
   - `claim_count`: the number of distinct kept claims (equal to the length of
     `claim_ids`), not the number of exported lines.
   - `by_cost_center`: one entry per cost-center code appearing in the kept rows
     (key = the code exactly as printed, e.g. `CC-4471`); its value is the sum of
     the kept line amounts for that cost center.
   - `grand_total`: the sum of all kept line amounts, equal to the sum of the
     `by_cost_center` values.
   - Parse the `amount` column as a decimal number (strip any currency symbol or
     thousands separator), keep cent precision, and emit JSON numbers, so
     `42.10` is written as `42.1`.
8. Write `report.json` in the workspace with exactly these top-level keys:
   `period` (the `YYYY-MM` string), `claim_ids` (array of strings),
   `claim_count` (integer), `by_cost_center` (object of code -> number),
   `grand_total` (number).
9. Verify before declaring completion:
   - Re-read `report.json` and check `claim_count` equals the length of
     `claim_ids`, and `grand_total` equals the sum of the `by_cost_center`
     values.
   - Cross-check the kept claims against the **IN THIS PERIOD** table: the number
     of table rows whose status is `approved` and whose category is not
     `Meals & Entertainment` must equal `claim_count`, and their cost-center
     amounts must match `by_cost_center`.
   - Confirm no status other than `approved` and no `Meals & Entertainment`
     amount contributed to the totals.

## Rules that commonly get missed

- Approval alone is not enough, and being approved does not make a claim
  reportable: the meals category is dropped even when approved.
- Excluding an unapproved claim means excluding all of its lines and its whole
  amount; never pro-rate or partially include a claim.
- Multiple lines can belong to one claim; `claim_count` counts claims, while all
  sums are computed over lines.
- Only the requested period belongs in the file; claims from other months appear
  in the app's claims list and must not be swept in.

## Recovery

- If the IN THIS PERIOD table or the export still reflects a previously selected
  period, re-select the **Period** value and activate **Download CSV** again;
  the export always follows the currently selected period.
- If the download does not start, activate **Download CSV** again and wait for
  the file to appear before reading it.
- If the on-page approved, non-meals claim count does not match your filtered
  count, discard the file you read, re-download for the selected period, and
  re-apply the filter rules above.
- If the period contains no rows that survive filtering, still write
  `report.json` with `claim_ids: []`, `claim_count: 0`, `by_cost_center: {}` and
  `grand_total: 0`.
- Do not approve, edit, or create claims to make the report work: this task only
  reads the Reports page, downloads its export, and writes the JSON file.
