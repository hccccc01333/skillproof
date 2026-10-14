---
name: expense-period-report
description: Build the ExpenseDesk expense report for one reporting period (a month such as May 2026) from that period's exported expense lines and save it as report.json in the workspace. Use when asked to prepare a period expense report, to download the period's expense lines from the Reports section, or to compute the reimbursable claims, per-cost-center totals, and grand total for a period.
---

# ExpenseDesk period expense report

Prepare a single-period reimbursement report from the expense lines that
ExpenseDesk exports for that period, then write `report.json` in the workspace.

Work only through the visible application: use the Reports section, its Period
control, and its Download CSV control. Do not call the export endpoint, an API,
or a script to obtain the data, and do not edit claim records in the application
— the report is a read-only summary of the period.

## 1. Export the period's expense lines

1. Open the **Reports** section from the header navigation (the section button
   labelled `Reports`, alongside `Claims`).
2. Set the **Period** combobox to the requested reporting period (`YYYY-MM`).
3. Confirm the period took effect before downloading: the **IN THIS PERIOD**
   table must list the claims of that period, and the Period control must show
   the requested value.
4. Activate the **Download CSV** link to download the period's expense lines
   into your workspace. The saved file name carries the period, e.g.
   `expense-lines-<YYYY-MM>.csv`.
5. Open the downloaded CSV and read it as one row per expense line, with the
   columns `claim_id, claim_title, period, status, category, cost_center,
   line_description, amount`.

Guard against a stale download: every row's `period` value must equal the
requested period. If rows carry another period, are empty, or the file is
missing, re-select the Period combobox, activate **Download CSV** again, wait
for the download to finish, and re-read the file before continuing.

The Reports page states that the export is ungrouped and contains drafts,
unapproved claims, and every category, so the exported lines are *not* yet the
reimbursable set — the rules below decide that. A claim with zero lines (shown
as `—` in the IN THIS PERIOD table) contributes no rows at all.

## 2. Decide which claims to count

Include a claim only if it passes **all** of these rules:

1. **Approved status.** Its `status` must be `approved`. Exclude any other
   status (`draft`, `pending_approval`, and any similar value) — those are not
   reimbursable yet.
2. **Reimbursable category.** Claims in category `Meals & Entertainment` are
   never reimbursable and must be left out of the report entirely; they are
   handled by a separate process. Exclude them even when their status is
   `approved`. All other categories seen in the export (`Travel -
   International`, `Travel - Domestic`, `Lodging`, `Office Supplies`,
   `Equipment`, and comparable ones) are counted when rule 1 passes.
3. **Not already paid.** A claim that was already settled outside this
   reimbursement run — for example one purchased on a company card — must be
   excluded, even when its status is `approved`.

**Limitation for rule 3.** No visible field identifies an already-paid claim:
neither the CSV columns listed above nor the Reports view records payment
method or reimbursement state. Confirm already-paid claims out of band before
finalising the report, and state in your result that this check was made
out of band. Do not infer the exclusion from the amount, the category, or the
cost center.

Apply the rules to lines, not just to claims: a claim is counted only when it
qualifies on all three rules, and all of its qualifying lines are then counted
together.

## 3. Aggregate

Work from the qualifying lines only.

- **Per claim:** group the qualifying rows by `claim_id` (a claim may occupy
  several rows, one per line) and sum the `amount` of its lines. The claim is
  counted once, no matter how many lines it has.
- **Per cost center:** for each `cost_center` value appearing on the qualifying
  lines, add up the `amount` values of those lines. Include only cost centers
  that still have at least one counted claim. If a counted claim has no cost
  center (`—` or empty), stop and flag it instead of inventing a bucket or
  dropping the claim silently.
- Keep amounts as decimal numbers with two-decimal precision; do not carry
  currency symbols or thousands separators.

## 4. Write `report.json`

Write a single JSON object to `report.json` in the workspace root (not to any
download or sub-directory) with exactly these fields:

- `period` — the reporting period as a string in `YYYY-MM`, matching the period
  used for the export.
- `claim_ids` — the ids of the counted claims, as a list of strings, in the
  order the claims first appear in the export.
- `claim_count` — how many claims were counted, as an integer. It must equal the
  length of `claim_ids`.
- `by_cost_center` — an object mapping each counted cost center to its summed
  total, e.g. `{"CC-4471": 960.0, "CC-5120": 42.1}`.
- `grand_total` — the total amount to be reimbursed, as a number: the sum of the
  per-claim amounts, which must equal the sum of the `by_cost_center` values.

Amounts are JSON numbers (`960.0`, `42.1`), not strings.

## 5. Verify before reporting success

1. Read `report.json` back from disk and confirm it parses.
2. Confirm `period` equals the requested period and that `claim_count` equals
   the length of `claim_ids`.
3. Recompute the per-cost-center totals and the grand total from the qualifying
   lines and confirm they agree with the file; confirm `grand_total` equals the
   sum of the `by_cost_center` values.
4. Confirm no excluded claim id appears in `claim_ids`, and that every counted
   id came from a line whose `status` is `approved` and whose category is not
   `Meals & Entertainment`.
5. Confirm the already-paid exclusion (rule 3) was established out of band; if
   it was not, say so instead of presenting the total as final.

Run the bundled `verify.json` assertions against the written file before
declaring completion, and treat any failing assertion as unfinished work.
