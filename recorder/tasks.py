"""Task definitions and demonstrations.

A task here has two halves, and keeping them apart is the point of the whole
project:

  * the *instruction* the agent is given, which names the goal and nothing
    else; and
  * the *demonstration*, which carries the procedural knowledge the
    instruction leaves out -- which portal, which claim, which receipts,
    which fields, what to check before submitting.

The demonstration never sees the evaluator, and task.json is written without
any grading field (see schema.EpisodeWriter._write_task).
"""

from __future__ import annotations

import re

TASKS: dict[str, dict] = {
    "expense-submit": {
        "application": "ExpenseDesk",
        "instruction": (
            "Get my March 2026 travel reimbursement claim into the approval queue."
        ),
        # Instructions are per-variant, and this is not a convenience.
        #
        # The first version of the perturbation changed the page -- renaming the
        # claim to April 2026 -- but left the instruction asking for the March
        # claim. That made the task unsatisfiable on the perturbed page, and one
        # agent was quite right to give up after reporting that no March claim
        # existed. It scored the do-nothing floor for being correct.
        #
        # The paper's Jitter method revises task instructions alongside the
        # data ("All 64 task instructions are revised"); skipping that step
        # turns a perturbation into an impossibility.
        "instructions": {
            "default": (
                "Get my March 2026 travel reimbursement claim into the approval queue."
            ),
            "jitter": (
                "Get my April 2026 travel reimbursement claim into the approval queue."
            ),
            "jitter-nostid": (
                "Get my April 2026 travel reimbursement claim into the approval queue."
            ),
            "jitter-remap": (
                "Get my April 2026 travel reimbursement claim into the approval queue."
            ),
            "relayout": (
                "Get my April 2026 travel reimbursement claim into the approval queue."
            ),
            "relayout-nostid": (
                "Get my April 2026 travel reimbursement claim into the approval queue."
            ),
        },
        "task_inputs": {
            "claim_id": "clm_2001",
            "period": "2026-03",
        },
        "notes": (
            "The instruction states the goal only. It does not name the cost "
            "center, the receipts that belong on the claim, the category, or the "
            "confirmation step."
        ),
    },
    "expense-report": {
        "application": "ExpenseDesk",
        # The instruction fixes the *format* so the artifact is checkable. It
        # deliberately does not say which rows belong in the report -- that is
        # the judgement the demonstration carries.
        "instruction": (
                "Prepare the May 2026 expense report and save it as report.json in your \n"
                "workspace.\n"
                "\n"
                "Download the period's expense lines from the Reports section, then write a \n"
                "JSON object with these fields:\n"
                "  \"period\"          the reporting period as \"YYYY-MM\"\n"
                "  \"claim_ids\"       the ids of the claims counted, as a list\n"
                "  \"claim_count\"     how many claims were counted\n"
                "  \"by_cost_center\"  object mapping each cost center to its total\n"
                "  \"grand_total\"     the total amount to be reimbursed"
        ),
        "instructions": {
            "reports": (
                "Prepare the May 2026 expense report and save it as report.json in your \n"
                "workspace.\n"
                "\n"
                "Download the period's expense lines from the Reports section, then write a \n"
                "JSON object with these fields:\n"
                "  \"period\"          the reporting period as \"YYYY-MM\"\n"
                "  \"claim_ids\"       the ids of the claims counted, as a list\n"
                "  \"claim_count\"     how many claims were counted\n"
                "  \"by_cost_center\"  object mapping each cost center to its total\n"
                "  \"grand_total\"     the total amount to be reimbursed"
            ),
        },
        "task_inputs": {"period": "2026-05", "output": "report.json"},
        "notes": (
            "The instruction states the deliverable and its shape. It does not "
            "say which claims count, which is the whole task."
        ),
    },
}


# --------------------------------------------------------------------------
# Demonstration for expense-report
# --------------------------------------------------------------------------
#
# The demonstration names the claims it leaves out and does not say why. The
# reason is derivable from the exported CSV -- status, category and period are
# all columns -- so this is a rule the induction agent can find, and finding it
# is the difference between a skill that transfers and one that does not.
#
# Naming the exclusions without reasons is deliberate, and mirrors the receipt
# task, whose observation step recorded *which* receipts were left unattached
# and left the rule for the induction to state. The second induction of that
# task found the rule and scored 100 where the first scored 70.

REPORT_EXCLUDED = ["clm_3003", "clm_3005", "clm_3006", "clm_3007", "clm_3008"]


def demo_expense_report(page, rec, workspace=None):
    """Produce the May 2026 report the way someone who knows the process would."""
    import csv as _csv
    import io as _io
    import json as _json
    from pathlib import Path as _Path

    workspace = _Path(workspace) if workspace else _Path.cwd() / "_demo_workspace"

    # 1. Open the Reports section.
    rec.click("Open the Reports section", page.get_by_test_id("nav-reports"))

    # 2. Choose the period.
    rec.select("Select period 2026-05", page.get_by_test_id("report-period"), "2026-05")

    # 3. Download the period's lines.
    rec.download(
        "Download the May 2026 expense lines as CSV",
        page.get_by_test_id("download-csv"),
        workspace,
    )

    # 4. Work the file. The rows that count are decided here; the trace records
    #    the outcome and not the reasoning, so the rule has to be inferred.
    csv_files = sorted(workspace.glob("expense-lines-*.csv"))
    if not csv_files:
        raise AssertionError("the CSV download did not land in the workspace")
    rows = list(_csv.DictReader(_io.StringIO(csv_files[-1].read_text(encoding="utf-8"))))

    included = [r for r in rows if r["claim_id"] not in REPORT_EXCLUDED]
    included_ids = sorted({r["claim_id"] for r in included})
    by_cc: dict[str, float] = {}
    for r in included:
        cc = r["cost_center"]
        by_cc[cc] = round(by_cc.get(cc, 0.0) + float(r["amount"]), 2)
    grand = round(sum(by_cc.values()), 2)

    report = {
        "period": "2026-05",
        "claim_ids": included_ids,
        "claim_count": len(included_ids),
        "by_cost_center": {k: round(v, 2) for k, v in sorted(by_cc.items())},
        "grand_total": grand,
    }
    (workspace / "report.json").write_text(
        _json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    rec.mark(
        "Review the downloaded lines; excluding " + ", ".join(REPORT_EXCLUDED),
        kind="observe",
    )
    rec.mark(
        f"Write report.json: {len(included_ids)} claims, total {grand:.2f}",
        kind="write",
    )
    rec.mark("Verify report.json is written and the totals agree", kind="verify")


def instruction_for(task: str, variant: str) -> str:
    """The instruction a method is given for a given variant."""
    spec = TASKS[task]
    return spec.get("instructions", {}).get(variant, spec["instruction"])


# --------------------------------------------------------------------------
# Demonstration for expense-submit
# --------------------------------------------------------------------------

# Which receipts belong on a travel claim. The instruction names none of them;
# this is the procedural knowledge the demonstration exists to carry.
#   rcp_3313 (team dinner) is a meals expense, not travel;
#   rcp_3314 (personal hotel upgrade) is explicitly personal.
TRIP_RECEIPTS = ["rcp_3310", "rcp_3311", "rcp_3312"]
EXCLUDED_RECEIPTS = ["rcp_3313", "rcp_3314"]

# Receipt metadata as rendered: "Vendor · YYYY-MM-DD · $412.80"
_META_RE = re.compile(r"^(?P<vendor>.+?)\s*·\s*(?P<date>\d{4}-\d{2}-\d{2})\s*·\s*\$(?P<amount>[\d,]+\.\d{2})$")


def _read_receipt(page, receipt_id: str) -> dict:
    """Read a receipt row the way a person would: off the screen.

    The demonstration reads values from the page instead of hardcoding them,
    so the same demo works unchanged under a perturbed variant. If it did not,
    the 'changed page' condition would be demonstrating the wrong values and
    would prove nothing.
    """
    row = page.get_by_test_id(f"receipt-{receipt_id}")
    label = row.locator("div > div").first.inner_text().strip()
    meta = row.locator(".receipt-meta").inner_text().strip()
    m = _META_RE.match(meta)
    if not m:
        raise AssertionError(f"unparseable receipt meta for {receipt_id}: {meta!r}")
    return {
        "id": receipt_id,
        "label": label,
        "amount": m.group("amount"),
        "date": m.group("date"),
    }


def demo_expense_submit(page, rec, workspace=None):
    """Drive ExpenseDesk the way a person who knows the internal process would."""

    # 1. Open the existing draft rather than starting a new claim.
    rec.click(
        "Open the draft travel reimbursement claim",
        page.get_by_test_id("claim-link-clm_2001"),
    )

    # 2. Read the user's own cost center from the header, as a person would.
    cost_center = page.locator("#user-meta").inner_text().split("·")[-1].strip()

    # 3. Read the trip receipts off the screen before attaching them.
    trip = [_read_receipt(page, rid) for rid in TRIP_RECEIPTS]
    for r in trip:
        rec.click(
            f"Attach receipt {r['id']} ({r['label']}) to the claim",
            page.get_by_test_id(f"attach-{r['id']}"),
        )
    rec.mark(
        "Receipt inbox reviewed; non-travel receipts left unattached: "
        + ", ".join(EXCLUDED_RECEIPTS),
        kind="observe",
    )

    # 4. Enter the expense lines, using the amounts just read from the screen.
    for r in trip:
        description = r["label"]
        rec.fill(
            f'Type expense description "{description}"',
            page.get_by_test_id("line-description"),
            description,
        )
        rec.fill(
            f'Type amount "{r["amount"]}" for {description}',
            page.get_by_test_id("line-amount"),
            r["amount"],
        )
        rec.click(f"Add the {description} line", page.get_by_test_id("add-line"))

    # 5. Category must be an international travel category.
    rec.select(
        "Set category to Travel - International",
        page.get_by_test_id("field-category"),
        "Travel - International",
    )

    # 6. A first submission attempt is rejected because the total exceeds the
    #    cost-center threshold. This is the workflow rule the instruction never
    #    states, and it is exactly what the demonstration is here to teach.
    rec.click("Click Submit for approval", page.get_by_test_id("submit-claim"))
    rec.click("Confirm the submission", page.get_by_test_id("confirm-submit"))
    rec.mark("Submission rejected: cost center required above the threshold", kind="observe")

    # 7. Supplying the cost center clears the block.
    rec.fill(
        f"Enter cost center {cost_center}",
        page.get_by_test_id("field-cost-center"),
        cost_center,
    )

    # 8. Resubmit and confirm.
    rec.click("Click Submit for approval again", page.get_by_test_id("submit-claim"))
    rec.click("Confirm the submission", page.get_by_test_id("confirm-submit"))

    # 9. Verify the claim reached the approval queue and is now read-only.
    rec.mark("Verify the claim shows Pending approval", kind="verify")


DEMOS = {
    "expense-submit": demo_expense_submit,
    "expense-report": demo_expense_report,
}
