"""Rubric evaluation for ExpenseDesk tasks.

Two design rules, both borrowed from the paper's setup:

1. **Task success is a pure function of server state.** No screenshots, no
   human judgement, no regex over page text. That is why the target app keeps
   its state server-side and exposes ``/api/state``.

2. **The evaluator is never visible to the method under test.** ``task.json``
   has no grading field (enforced in ``recorder.schema``), and this module is
   not importable from anywhere the induction agent can reach.

Expected values are derived from the *variant seed* rather than hardcoded, so
the evaluator and the application cannot drift apart. ``bench/site/server.py``
is the single source of truth for what a correct final state looks like.

Scoring follows the paper's Appendix E.3 aggregations:

    Score = (100 / |D|) * sum(weight_i * satisfied_i)
    SR    = 100 if every condition is satisfied, else 0
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

_SITE = Path(__file__).resolve().parent / "site"
if str(_SITE) not in sys.path:
    sys.path.insert(0, str(_SITE))

from server import RULES, report_seed, variant_seed  # noqa: E402

# Receipts are classified by role in the task, not by identifier. The
# identifiers are an implementation detail of one particular page state and are
# deliberately not stable across variants -- a rubric keyed on `rcp_3310` would
# be grading whether the method replayed a recorded constant, not whether it
# understood which expenses belong on a travel claim.
TRIP_BUCKET = "trip"
NON_TRIP_BUCKET = "non_trip"

CLAIM_ID = "clm_2001"


@dataclass
class RubricItem:
    id: str
    weight: int
    requirement: str
    satisfied: bool
    detail: str = ""


def _expected(variant: str) -> dict:
    seed = variant_seed(variant)
    receipts = {r["id"]: r for r in seed["receipts"]}
    trip_ids = [r["id"] for r in seed["receipts"] if r.get("_bucket") == TRIP_BUCKET]
    non_trip_ids = [r["id"] for r in seed["receipts"] if r.get("_bucket") == NON_TRIP_BUCKET]
    return {
        "cost_center": seed["user"]["cost_center"],
        "trip_ids": tuple(trip_ids),
        "non_trip_ids": tuple(non_trip_ids),
        "trip_amounts": {rid: receipts[rid]["amount"] for rid in trip_ids},
        "trip_total": round(sum(receipts[rid]["amount"] for rid in trip_ids), 2),
        "threshold": RULES["cost_center_threshold"],
    }


def evaluate(variant: str, state: dict) -> dict:
    """Score `state` against the rubric for `variant`.

    Returns {"score": float, "sr": int, "items": [RubricItem], "passed": bool}.
    """
    exp = _expected(variant)
    claim = next((c for c in state.get("claims", []) if c["id"] == CLAIM_ID), None)

    if claim is None:
        return {
            "score": 0.0,
            "sr": 0,
            "passed": False,
            "items": [],
            "error": f"claim {CLAIM_ID} not found in final state",
        }

    attached = set(claim.get("receipts", []))
    line_total = round(sum(l["amount"] for l in claim.get("lines", [])), 2)

    def all_trip_attached() -> bool:
        return all(r in attached for r in exp["trip_ids"])

    items = [
        RubricItem(
            "R1", 15, "Claim reached the approval queue",
            claim.get("status") == "pending_approval",
            f"status={claim.get('status')!r}",
        ),
        RubricItem(
            "R2", 10, "Category is a travel category",
            bool(claim.get("category")) and claim["category"].startswith(RULES["required_category_prefix"]),
            f"category={claim.get('category')!r}",
        ),
        RubricItem(
            "R3", 15, "Cost center matches the user's own cost center",
            claim.get("cost_center") == exp["cost_center"],
            f"got {claim.get('cost_center')!r}, expected {exp['cost_center']!r}",
        ),
        RubricItem(
            "R4", 20, "All three trip receipts attached",
            all_trip_attached(),
            f"attached={sorted(attached)}",
        ),
        RubricItem(
            "R5", 15, "No non-trip receipt attached",
            not (set(exp["non_trip_ids"]) & attached),
            f"offending={sorted(set(exp['non_trip_ids']) & attached)}",
        ),
        RubricItem(
            "R6", 15, "Line total equals the sum of the trip receipts",
            abs(line_total - exp["trip_total"]) < 0.01,
            f"got {line_total:.2f}, expected {exp['trip_total']:.2f}",
        ),
        RubricItem(
            "R7", 10, "Claim total exceeds the cost-center threshold",
            line_total > exp["threshold"],
            f"total {line_total:.2f} vs threshold {exp['threshold']:.2f}",
        ),
    ]

    total_weight = sum(i.weight for i in items)
    earned = sum(i.weight for i in items if i.satisfied)
    score = round(100.0 * earned / total_weight, 2)
    passed = all(i.satisfied for i in items)

    return {
        "score": score,
        "sr": 100 if passed else 0,
        "passed": passed,
        "items": items,
        "line_total": line_total,
        "expected_total": exp["trip_total"],
    }


# --------------------------------------------------------------------------
# Task 2: the reporting pipeline
# --------------------------------------------------------------------------
#
# A different shape of judgement from the claim task. There, the decision was
# per-item ("does this receipt belong"); here it is a selection rule over a
# table plus an aggregation, and the load-bearing rule -- that meals are
# reimbursed elsewhere -- is organisational knowledge that no status field
# encodes.
#
# The instruction fixes the output *format* so the result is checkable. It does
# not state which rows count; that is what the demonstration carries.

REPORT_TASK_ID = "expense-report"
REPORT_HARD_TASK_ID = "expense-report-hard"
REPORT_PERIOD = "2026-05"
REPORT_PATH = "report.json"

# Approved, in-period, non-meals claims -- the correct answer.
_REPORT_INCLUDED = ("clm_3001", "clm_3002", "clm_3004")
# Approved and in-period but meals: reimbursed through a separate system.
_REPORT_MEALS = ("clm_3003", "clm_3006")
# Excluded for other reasons: unapproved, or the wrong period.
_REPORT_UNAPPROVED = ("clm_3005", "clm_3008")
_REPORT_WRONG_PERIOD = ("clm_3007",)

# The `reports-hard` variant adds a claim that is approved, in period and in an
# ordinary category, and is still excluded because it was already paid. That is
# a second rule nowhere in the data, so the expected answer is unchanged -- the
# claim was never counted -- while the set of exclusions grows. A method that
# finds the meals rule and stops produces exactly the same wrong answer as one
# that finds neither, which is the point of measuring it.
_REPORT_ALREADY_PAID = ("clm_3010",)


def _report_exclusions(variant: str) -> tuple[str, ...]:
    base = _REPORT_MEALS + _REPORT_UNAPPROVED + _REPORT_WRONG_PERIOD
    return base + _REPORT_ALREADY_PAID if variant == "reports-hard" else base


def evaluate_report(variant: str, state: dict, workspace: Path | None) -> dict:
    """Score the produced report file against the rubric.

    `state` is accepted for signature parity with the claim evaluator and lets
    a caller cross-check the file against the server, but the rubric scores the
    *artifact*: a report that is right is right regardless of how it was built.
    """
    workspace = Path(workspace) if workspace else None
    path = (workspace / REPORT_PATH) if workspace else None

    report = None
    parse_error = None
    if path is None or not path.is_file():
        parse_error = f"{REPORT_PATH} was not produced"
    else:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            parse_error = f"{REPORT_PATH} is not valid JSON: {exc}"
        except OSError as exc:
            parse_error = f"{REPORT_PATH} could not be read: {exc}"

    claims = {c["id"]: c for c in report_seed()["claims"]}

    def claim_total(cid: str) -> float:
        return round(sum(l["amount"] for l in claims[cid]["lines"]), 2)

    expected_ids = list(_REPORT_INCLUDED)
    expected_total = round(sum(claim_total(c) for c in expected_ids), 2)
    expected_by_cc: dict[str, float] = {}
    for cid in expected_ids:
        cc = claims[cid]["cost_center"]
        expected_by_cc[cc] = round(expected_by_cc.get(cc, 0.0) + claim_total(cid), 2)

    def get(key):
        return report.get(key) if isinstance(report, dict) else None

    got_ids = get("claim_ids")
    got_ids = [str(x) for x in got_ids] if isinstance(got_ids, list) else None
    got_cc = get("by_cost_center")
    got_cc_norm = (
        {str(k): round(float(v), 2) for k, v in got_cc.items()}
        if isinstance(got_cc, dict) else None
    )
    got_total = get("grand_total")
    got_total = round(float(got_total), 2) if isinstance(got_total, (int, float)) else None

    items = [
        RubricItem("R1", 10, f"{REPORT_PATH} exists and parses as JSON",
                   report is not None, parse_error or "parsed"),
        RubricItem("R2", 10, "Report names the requested period",
                   get("period") == REPORT_PERIOD,
                   f"got {get('period')!r}, expected {REPORT_PERIOD!r}"),
        RubricItem("R3", 25, "Grand total matches the included claims",
                   got_total is not None and abs(got_total - expected_total) < 0.01,
                   f"got {got_total}, expected {expected_total:.2f}"),
        RubricItem("R4", 20, "Per-cost-center breakdown is correct",
                   got_cc_norm == expected_by_cc,
                   f"got {got_cc_norm}, expected {expected_by_cc}"),
        RubricItem("R5", 20, "Meals claims excluded (reimbursed separately)",
                   got_ids is not None and not (set(_REPORT_MEALS) & set(got_ids)),
                   f"meal claims present: {sorted(set(_REPORT_MEALS) & set(got_ids or []))}"),
        RubricItem("R6", 15, "Unapproved, out-of-period and already-paid claims excluded",
                   got_ids is not None
                   and not (set(_report_exclusions(variant)) & set(got_ids)),
                   "excluded claims present: "
                   f"{sorted(set(_report_exclusions(variant)) & set(got_ids or []))}"),
    ]

    total_weight = sum(i.weight for i in items)
    earned = sum(i.weight for i in items if i.satisfied)
    return {
        "score": round(100.0 * earned / total_weight, 2),
        "sr": 100 if all(i.satisfied for i in items) else 0,
        "passed": all(i.satisfied for i in items),
        "items": items,
        "expected_total": expected_total,
        "expected_by_cost_center": expected_by_cc,
    }


def evaluate_any(task: str, variant: str, state: dict, workspace: Path | None = None) -> dict:
    """Dispatch to the rubric for `task`."""
    if task in (REPORT_TASK_ID, REPORT_HARD_TASK_ID):
        return evaluate_report(variant, state, workspace)
    return evaluate(variant, state)


def format_report(result: dict, *, title: str = "") -> str:
    lines = []
    if title:
        lines += [f"## {title}", ""]
    if "error" in result:
        lines.append(f"ERROR: {result['error']}")
        return "\n".join(lines)

    lines.append("| item | wt | requirement | result | detail |")
    lines.append("|---|---|---|---|---|")
    for i in result["items"]:
        lines.append(
            f"| {i.id} | {i.weight} | {i.requirement} | "
            f"{'PASS' if i.satisfied else 'FAIL'} | {i.detail} |"
        )
    lines += [
        "",
        f"**Score {result['score']:.2f}/100**  ·  "
        f"**SR {'100' if result['sr'] else '0'}**  ·  "
        f"{'all conditions satisfied' if result['passed'] else 'incomplete'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import json

    from server import AppState

    for variant in ("default", "jitter"):
        st = AppState(variant).snapshot()
        print(format_report(evaluate(variant, st), title=f"untouched seed · {variant}"))
        print()
