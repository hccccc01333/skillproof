---
name: expense-period-report
description: Prepare a period expense report (report.json) in ExpenseDesk by exporting a period's claim lines from the Reports section, deciding which claims are reimbursable, and summarizing them. Use when asked to prepare a monthly/period expense report, total reimbursable claims by cost center, or reconcile a period's expense export into a JSON summary.
---

# Period expense report from the ExpenseDesk Reports export

## Deliverable

Save `report.json` in the workspace root as a single JSON object with exactly these fields:

- `period` — the requested reporting period as `"YYYY-MM"` (e.g. May 2026 → `"2026-05"`).
- `claim_ids` — the ids of the claims counted, one entry per counted claim, in the order the claims appear in the export.
- `claim_count` — how many claims were counted; must equal the length of `claim_ids`.
- `by_cost_center` — object mapping each cost center to the total of its counted amounts.
- `grand_total` — the total amount to be reimbursed.

Amounts are JSON **numbers**, not strings, in currency units rounded to 2 decimals / cents (an amount of 1002.10 is written `1002.1`). Keep the exact cost-center codes from the export as `by_cost_center` keys.

## Procedure

1. Open the **Reports** section (`Reports` in the header navigation). The page shows a `Period` combobox, a `Download CSV` link, and an "in this period" table listing the period's claims with STATUS, CATEGORY, COST CENTER and LINES columns.
2. Set the `Period` combobox to the requested period. The export link is period-scoped (its href carries `?period=<YYYY-MM>`), so the selection determines what the download contains — always set the period before downloading.
3. Click `Download CSV` and wait for the export to land in the workspace (name derived from the period, e.g. `expense-lines-<YYYY-MM>.csv`).
4. Open the downloaded export and read its rows. The columns are `claim_id, claim_title, period, status, category, cost_center, line_description, amount`.
5. Apply the counting rules below to decide which rows count.
6. Compute the totals, then write `report.json` in the workspace.
7. Verify the persisted file and the arithmetic (see Verification).

## Which claims count

The page states that the export is unprocessed and deliberately contains drafts, unapproved claims and every category, so the export itself supplies no filtering — you must apply it. A claim counts only when **all** of these hold:

- Its `period` equals the requested period. Discard any row whose period differs, even if it appeared in the download.
- Its `status` is `approved`. Exclude `Draft`, `Pending approval`, and any other non-approved status.
- Its `category` is **not** `Meals & Entertainment`. Approved, in-period claims in this category are excluded even when they belong to a cost center whose other claims are counted.
- It appears in the export with at least one line. Claims with no lines (drafts) do not appear in the export at all, so they can never be counted; the page's LINES column shows `0` for them.

Status alone is not enough to reproduce the report: in the recorded period, two approved, in-period, in-cost-center claims were dropped solely because of their category, while an approved claim of another category at the same cost center was counted. Check the `category` column of every approved row before counting it.

## Computation

- Count each claim once: add its `claim_id` to `claim_ids` a single time even if the export holds several lines for it.
- A claim's amount is the sum of its counted exported line amounts.
- `by_cost_center`: for every counted line, add its `amount` to the entry keyed by that line's `cost_center`. Include only cost centers that appear on counted lines; a cost center present in the export but with no counted line is omitted.
- `grand_total`: the sum of all counted amounts. It must equal the sum of the `by_cost_center` values.
- Sum in currency units (cents precision); do not round intermediate per-line amounts, and do not convert, adjust or negate any amount.

## Verification before finishing

- After writing, re-read `report.json` from disk and confirm the persisted content — do not report a value you only held in memory.
- Confirm `claim_count` equals the number of entries in `claim_ids`.
- Confirm `grand_total` equals the sum of the `by_cost_center` values, and that each listed cost center's total equals the sum of the counted amounts for that cost center.
- Confirm no id in `claim_ids` belongs to a claim whose `status` is not `approved` or whose `category` is `Meals & Entertainment`.
- Re-open the Reports page and confirm the `Period` control still shows the requested period, so the export you summarized is the requested period's.

## Recovery

- If no export appears in the workspace, re-select the period and click `Download CSV` again; if a download prompt or notification appears, accept it and locate the saved file before reading it.
- If the export is empty or holds only a header row, the period control likely still held a different period — set the requested period and download again.
- If the export contains rows from other periods (for example a file downloaded before the period change took effect), discard those rows rather than editing the file's contents.
- Never add or drop claims to make totals "balance": only the rules above decide inclusion.
- A slow or stale page after switching sections is not an error state — re-open the Reports section and re-check the `Period` value before retrying the download.

## Limits and uncertainty

- The `Meals & Entertainment` exclusion is the only category rule the evidence supports: neither the task instruction, the Reports page note, nor any export column names reimbursable categories. If a period's export contains other categories for which no exclusion is demonstrated, count them (treat them as reimbursable) and state that assumption in your final message. Do not invent a meals cap, an amount threshold, or an allow-list of categories, and do not exclude a row for any reason other than the four conditions above.
- The treatment of a cost center that has only excluded claims (possible `0` entry versus omission) is not demonstrated; the shown report lists only cost centers with counted amounts, which is what this skill instructs.
