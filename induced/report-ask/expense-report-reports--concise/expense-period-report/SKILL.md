---
name: expense-period-report
description: Build a period expense report in ExpenseDesk by downloading the period's expense lines from the Reports section, deciding which claims count under the reimbursement policy, and writing the aggregated report.json. Use when asked to prepare a report for a given reporting period (e.g. "May 2026"), total the amounts to be reimbursed, or produce claim_ids / claim_count / by_cost_center / grand_total for a period.
---

# Prepare a period expense report in ExpenseDesk

The task supplies a reporting period (format `YYYY-MM`, e.g. `2026-05`) and asks for a
JSON file named `report.json` in the workspace. The Reports section gives you the raw
period export; that export is explicitly **unprocessed**, so the whole task is deciding
which exported lines are spend that belongs in the report.

## 1. Open the period export

1. In the ExpenseDesk header navigation, click the **Reports** button (the header nav
   holds **Claims** and **Reports**). The page titled **Expense reports** opens.
2. Read the page: it carries a **Period** combobox and a **Download CSV** link, plus a
   table titled **IN THIS PERIOD** with columns `CLAIM`, `STATUS`, `CATEGORY`,
   `COST CENTER`, `LINES`.
3. The page states that the export "contains drafts, unapproved claims and every
   category". Treat that as a warning: the download is not the answer, it is the input
   you must filter.
4. Set the **Period** combobox to the requested period — pick the option equal to the
   requested period exactly. If the requested period is not among the options, stop and
   report that the period is unavailable rather than substituting a nearby period.
5. Click **Download CSV**. The export lands in the workspace as
   `expense-lines-<period>.csv` (e.g. `expense-lines-2026-05.csv`). Confirm the file
   exists and that its filename period matches the requested period before reading it.

The left sidebar **MY CLAIMS** list also shows claims, including claims from *other*
periods. It is a navigation aid only — never build the report from the sidebar, and
never change a claim's status or content to make it countable.

## 2. Read the exported lines

The CSV has one row per **expense line** with the columns:

`claim_id, claim_title, period, status, category, cost_center, line_description, amount`

A claim may have one or more lines. `LINES` in the page's table is that claim's line
count; a claim with zero lines (typically a draft) has no exported row at all.

## 3. Decide which claims count (the core rule)

Count a row only when **all three** conditions hold:

1. **Period matches** — the row's `period` equals the requested period. Exclude rows for
   any other period even when they are approved and even when their title names the
   requested month.
2. **Approved status** — the row's `status` is `approved`. Exclude anything not yet
   approved, such as `draft` or `pending_approval`; unapproved work is not yet spend.
3. **Reimbursable category** — the row's `category` is not `Meals & Entertainment`.
   Meals and entertainment are reimbursed through a separate system and never appear in
   a period expense report, so exclude them even though they are approved and in period.

Each distinct `claim_id` that passes all three rules is counted **once**, no matter how
many lines it has. Extra lines change the amount, never the claim count.

Do not look for a single column that decides everything. `status` is the most legible
field, but it is not sufficient: approved meals claims are still excluded, and period
must be applied on top of it. When you exclude a row, be able to name which of the three
rules excluded it.

## 4. Compute the report fields

Aggregate over exactly the rows that passed step 3:

- `period` — the requested period as `YYYY-MM`.
- `claim_ids` — the distinct `claim_id` values that passed, listed in the order those
  claims first appear in the downloaded CSV.
- `claim_count` — the number of entries in `claim_ids` (distinct claims, not rows).
- `by_cost_center` — object mapping each counted row's `cost_center` to the sum of that
  cost center's counted `amount` values. Include every cost center that appears among the
  counted rows; omit cost centers that appear only on excluded rows.
- `grand_total` — the sum of all counted `amount` values, i.e. the total to be
  reimbursed. It must equal the sum of the `by_cost_center` values.

Sum the raw amounts exactly as given and round monetary results to two decimals. Emit
JSON numbers for amounts and `claim_count`, and strings for `period` and each id — not
formatted currency strings.

## 5. Write and verify

Write the JSON object to `report.json` in the workspace using the task's output filename.
Then run the bundled verifier `verify.json` against the visible content of the written
file (open `report.json` and evaluate each assertion against what it shows), and confirm
before declaring completion:

- all five fields are present, with the types above and `period` equal to the requested
  period;
- `claim_count` equals both the length of `claim_ids` and the number of distinct counted
  claims;
- every id in `claim_ids` has an exported row whose `period`, `status`, and `category`
  satisfy all three rules of step 3;
- `by_cost_center` re-adds to `grand_total`, and each per-cost-center value equals the
  sum of that cost center's counted lines;
- no excluded claim leaked in, and you can state the rule that excluded each of the
  remaining exported rows.

## Recovery

- **Period list does not contain the requested period**: recheck the combobox; if it is
  genuinely absent, report the limitation instead of guessing.
- **Download missing or stale**: re-select the requested value in the **Period** combobox
  and click **Download CSV** again; confirm the workspace filename is
  `expense-lines-<period>.csv` for the requested period before reading it.
- **Exported rows disagree with the page's IN THIS PERIOD table**: use the page table to
  identify which claims exist in the period (including zero-line claims with no exported
  row) and the CSV for amounts. Never invent amounts for a claim that has no exported
  lines.
- **A row's meaning is unclear** (an unexpected `status` or `category`): apply the three
  rules literally — anything not `approved` stays out, and anything in
  `Meals & Entertainment` stays out. If that still cannot explain the row, report the
  ambiguity rather than including or excluding it silently.
