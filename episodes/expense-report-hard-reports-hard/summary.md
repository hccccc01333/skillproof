# Demonstration summary: expense-report-hard-reports-hard

**Task instruction.** Prepare the May 2026 expense report and save it as report.json in 
your workspace.

Download the period's expense lines from the Reports section, then 
write a JSON object with these fields:
  "period"          the reporting period as "YYYY-MM"
  "claim_ids"       the ids of the claims counted, as a list
  "claim_count"     how many claims were counted
  "by_cost_center"  object mapping each cost center to its total
  "grand_total"     the total amount to be reimbursed

**Recorded actions.** 7
**Evidence images.** 8
**Raw input events.** 8

## Action sequence

1. [0:00:02] Open the Reports section
2. [0:00:03] Select period 2026-05 `2026-05`
3. [0:00:03] Download the May 2026 expense lines as CSV `expense-lines-2026-05.csv`
4. [0:00:04] Review the downloaded lines; excluding clm_3003, clm_3005, clm_3006, clm_3007, clm_3008, clm_3010
5. [0:00:04] Write report.json: 3 claims, total 1002.10
6. [0:00:05] Verify report.json is written and the totals agree
7. [0:00:05] end of demonstration

_Summary is derived evidence, not ground truth; reconcile it against the action trace and frames._
