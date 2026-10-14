"""ExpenseDesk: a deterministic, resettable mock web application.

This is the target application for show2skill recordings. It exists so that
demonstrations, induced skills, and changed-page perturbations all run against
a byte-identical starting state, which is what makes Week-3 comparisons fair.

Run:  python bench/site/server.py [--port 8765] [--variant default]
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"

# --------------------------------------------------------------------------
# Seed state. Everything the app exposes to a user lives here; the evaluator
# reads the same structure, so "task success" is a pure function of state.
# --------------------------------------------------------------------------

SEED = {
    "user": {
        "id": "u_1042",
        "name": "Dana Whitfield",
        "role": "employee",
        "department": "Field Operations",
        "cost_center": "CC-4471",
    },
    "categories": [
        "Travel - Domestic",
        "Travel - International",
        "Lodging",
        "Meals & Entertainment",
        "Office Supplies",
    ],
    "receipts": [
        {
            "id": "rcp_3310",
            "label": "Pacific Air SFO-KIX",
            "vendor": "Pacific Air",
            "amount": 412.80,
            "date": "2026-03-12",
            "available": True,
            "_bucket": "trip",
        },
        {
            "id": "rcp_3311",
            "label": "Kyoto Ryokan 3 nights",
            "vendor": "Kyoto Ryokan",
            "amount": 268.50,
            "date": "2026-03-13",
            "available": True,
            "_bucket": "trip",
        },
        {
            "id": "rcp_3312",
            "label": "Airport express rail",
            "vendor": "Haruka Rail",
            "amount": 31.20,
            "date": "2026-03-12",
            "available": True,
            "_bucket": "trip",
        },
        {
            "id": "rcp_3313",
            "label": "Team dinner",
            "vendor": "Nishiki Grill",
            "amount": 96.40,
            "date": "2026-03-14",
            "available": True,
            "_bucket": "non_trip",
        },
        {
            "id": "rcp_3314",
            "label": "Personal hotel upgrade",
            "vendor": "Kyoto Ryokan",
            "amount": 140.00,
            "date": "2026-03-13",
            "available": True,
            "_bucket": "non_trip",
        },
    ],
    "claims": [
        {
            "id": "clm_2001",
            "title": "March 2026 travel reimbursement",
            "status": "draft",
            "category": None,
            "cost_center": None,
            "lines": [],
            "receipts": [],
            "note": "",
            "submitted_at": None,
        }
    ],
}

# Rules the application enforces. They are surfaced through validation
# messages in the UI rather than stated in the task instruction, which is the
# whole point: an agent must discover them from the demonstration.
RULES = {
    "min_receipts": 1,
    "cost_center_threshold": 500.0,
    "required_category_prefix": "Travel",
}


# Page layouts. `default` is what the demonstration was recorded against;
# `relayout` is the same application after a UI revision -- sections reordered,
# controls relabelled, fields regrouped. The data is identical, so a difference
# between the two isolates *layout* from *values*, which are the two things the
# product demo claims an agent can survive ("换成新数据、调整页面布局").
#
# Labels stay semantically transparent on purpose. "Add to claim" for what was
# "Attach" is a rename a person reads correctly without thinking; the test is
# whether a method re-locates the control, not whether it can guess an
# arbitrary string.
LAYOUTS: dict[str, dict] = {
    "default": {
        "labels": {
            "attach": "Attach",
            "add_line": "Add line",
            "submit": "Submit for approval",
            "confirm": "Confirm submission",
        },
        "section_order": ["details", "lines", "receipts"],
        "field_order": ["category", "cost_center", "note"],
        "titles": {
            "details": "Claim details",
            "lines": "Expense lines",
            "receipts": "Receipt inbox",
        },
    },
    "relayout": {
        "labels": {
            "attach": "Add to claim",
            "add_line": "Add expense",
            "submit": "Send for approval",
            "confirm": "Confirm and send",
        },
        "section_order": ["receipts", "lines", "details"],
        "field_order": ["cost_center", "note", "category"],
        "titles": {
            "details": "Claim information",
            "lines": "Expense items",
            "receipts": "Available receipts",
        },
    },
}


def report_seed() -> dict:
    """Seed for the reporting task.

    A different shape of work from the claim task: instead of acting on one
    record, the agent must select which records count, aggregate them, and emit
    a file. The judgement is a *selection rule over a table* rather than a
    per-item decision, which is what makes it a test of whether induction
    learned judgement or learned one task's receipt rule.

    The traps, none of which the instruction states:

      * `clm_3005` is a draft and `clm_3008` is pending — neither has been
        approved, so neither belongs in a report of approved spend;
      * `clm_3007` is the right category but the wrong period;
      * every `Meals & Entertainment` claim is reimbursed through a separate
        system and must not be double-counted here. This is the load-bearing
        rule: it is the only one that requires knowing how the organisation
        works rather than reading a status field.
    """
    state = copy.deepcopy(SEED)
    state["user"]["cost_center"] = "CC-4471"
    state["claims"] = [
        _report_claim("clm_3001", "May 2026 travel reimbursement", "2026-05",
                      "approved", "Travel - International", "CC-4471",
                      [("Flight SFO-KIX", 620.00)]),
        _report_claim("clm_3002", "May 2026 hotel", "2026-05",
                      "approved", "Lodging", "CC-4471",
                      [("Kyoto Ryokan 3 nights", 340.00)]),
        _report_claim("clm_3003", "May 2026 client dinner", "2026-05",
                      "approved", "Meals & Entertainment", "CC-4471",
                      [("Client dinner", 96.40)]),
        _report_claim("clm_3004", "May 2026 desk supplies", "2026-05",
                      "approved", "Office Supplies", "CC-5120",
                      [("USB-C cables", 42.10)]),
        _report_claim("clm_3005", "May 2026 local travel", "2026-05",
                      "draft", "Travel - Domestic", None, []),
        _report_claim("clm_3006", "May 2026 team coffee", "2026-05",
                      "approved", "Meals & Entertainment", "CC-4471",
                      [("Team coffee", 18.75)]),
        _report_claim("clm_3007", "April 2026 travel reimbursement", "2026-04",
                      "approved", "Travel - International", "CC-4471",
                      [("Flight SFO-NRT", 510.00)]),
        _report_claim("clm_3008", "May 2026 rail pass", "2026-05",
                      "pending_approval", "Travel - Domestic", "CC-5120",
                      [("Rail pass", 88.00)]),
    ]
    return state


def _report_claim(cid, title, period, status, category, cost_center, lines) -> dict:
    return {
        "id": cid,
        "title": title,
        "period": period,
        "status": status,
        "category": category,
        "cost_center": cost_center,
        "lines": [
            {"id": f"ln_{i:02d}", "description": d, "amount": a, "receipt_id": None}
            for i, (d, a) in enumerate(lines, start=1)
        ],
        "receipts": [],
        "note": "",
        "submitted_at": "2026-06-01T09:00:00Z" if status != "draft" else None,
    }


# Receipts for the reporting task are not needed; the CSV is generated from
# claim lines directly.
REPORT_PERIODS = ["2026-04", "2026-05"]


def report_hard_seed() -> dict:
    """The reporting task with a second rule that is not in the data.

    The `reports` variant has exactly one rule that cannot be read off a column:
    meals are reimbursed elsewhere. A real workflow has several, and the
    question that decides whether this is a product or a prototype is **how many
    questions the induction asks** when there is more than one thing it cannot
    work out.

    So this adds a claim that is approved, in period, and in a perfectly
    ordinary category, and is still excluded — because it was bought on a
    company card and never needed reimbursing. Nothing in the export says so.
    It is visible only as a third unexplained exclusion.

    If the induction asks about both rules, the mechanism scales. If it finds
    one pattern and stops, one question is all a user will ever get and the rest
    of the workflow stays unlearned.
    """
    state = report_seed()
    state["claims"].append(
        _report_claim("clm_3010", "May 2026 monitor", "2026-05",
                      "approved", "Equipment", "CC-5120",
                      [("External monitor", 249.00)])
    )
    return state


def variant_seed(variant: str) -> dict:
    """Return a perturbed seed. Used for the Week-3 'changed page' condition."""
    state = copy.deepcopy(SEED)
    if variant == "default":
        return state
    if variant == "reports":
        return report_seed()
    if variant == "reports-hard":
        return report_hard_seed()
    if variant in ("jitter", "jitter-nostid", "jitter-remap", "relayout", "relayout-nostid"):
        # Same application, changed entities / parameters / constraints.
        state["user"]["cost_center"] = "CC-5120"
        state["claims"][0]["title"] = "April 2026 travel reimbursement"
        state["categories"] = [
            "Travel - International",
            "Travel - Domestic",
            "Client Entertainment",
            "Lodging",
            "Equipment",
        ]
        by_id = {r["id"]: r for r in state["receipts"]}
        by_id["rcp_3310"]["amount"] = 538.20  # pushes total over the threshold
        by_id["rcp_3310"]["date"] = "2026-04-08"
        by_id["rcp_3311"]["date"] = "2026-04-09"
        by_id["rcp_3312"]["date"] = "2026-04-08"
        by_id["rcp_3313"]["date"] = "2026-04-10"
        if variant in ("jitter-nostid", "relayout-nostid"):
            # Drop the stable hooks the recorder relies on. A real third-party
            # site has no data-testid attributes at all; a recorded macro then
            # has to resolve targets by role and accessible name, and three
            # buttons all named "Attach" are genuinely ambiguous.
            state["expose_testids"] = False
        if variant in ("relayout", "relayout-nostid"):
            # Changed data AND a revised UI: sections reordered, controls
            # relabelled, fields regrouped. `relayout` keeps the test hooks so
            # a failure is attributable to layout alone; `relayout-nostid`
            # drops them too, which is what a third-party site revision
            # actually looks like and is the honest version of the product
            # demo's "调整页面布局".
            state["layout"] = "relayout"
        if variant == "jitter-remap":
            # Re-issue the receipt identifiers. The visible labels, vendors and
            # amounts are untouched, so the semantic signal an agent needs is
            # fully present -- but a macro replaying the recorded ids attaches
            # nothing, because those ids no longer exist.
            #
            # Without this, `jitter` silently flatters the macro: receipt
            # identity is stable there, so replaying the recorded ids satisfies
            # the receipt-selection criteria for free. That accounted for 35 of
            # the macro's 70 points.
            for i, r in enumerate(state["receipts"], start=1):
                r["id"] = f"rcpt-{i:04d}"
        return state
    raise SystemExit(f"unknown variant: {variant}")


class AppState:
    """Single in-memory state guarded by a lock."""

    def __init__(self, variant: str) -> None:
        self._lock = threading.Lock()
        self._variant = variant
        self._seed = variant_seed(variant)
        self._state = copy.deepcopy(self._seed)

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def reset(self) -> dict:
        with self._lock:
            self._state = copy.deepcopy(self._seed)
            return copy.deepcopy(self._state)

    def mutate(self, fn):
        """Apply fn(state) under the lock; return (result, new_state)."""
        with self._lock:
            result = fn(self._state)
            return result, copy.deepcopy(self._state)


def total_of(claim: dict) -> float:
    return round(sum(line["amount"] for line in claim["lines"]), 2)


def validate(claim: dict) -> list[str]:
    """Return a list of human-readable validation errors for a claim."""
    errors: list[str] = []
    if len(claim["receipts"]) < RULES["min_receipts"]:
        errors.append("Attach at least one receipt before submitting.")
    if not claim["category"]:
        errors.append("Select a category.")
    elif not claim["category"].startswith(RULES["required_category_prefix"]):
        errors.append(
            f"Category '{claim['category']}' is not allowed for this claim type."
        )
    total = total_of(claim)
    if total > RULES["cost_center_threshold"] and not claim["cost_center"]:
        errors.append(
            f"Claims over {RULES['cost_center_threshold']:.0f} require a cost center."
        )
    return errors


def find_claim(state: dict, claim_id: str) -> dict | None:
    return next((c for c in state["claims"] if c["id"] == claim_id), None)


class Handler(BaseHTTPRequestHandler):
    server_version = "ExpenseDesk/1.0"
    state: AppState  # injected by main()

    # ---- plumbing -------------------------------------------------------
    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send(self, code: int, payload, ctype="application/json") -> None:
        if ctype == "application/json":
            body = json.dumps(payload, indent=2).encode("utf-8")
        else:
            body = payload
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _public_state(self, state: dict) -> dict:
        """The state as the browser should see it.

        Drops private keys (leading underscore) -- `_bucket` classifies each
        receipt as trip / non-trip, which is the answer to the task's hardest
        question, and an agent that could read it would not be solving anything.
        """
        def strip(obj):
            if isinstance(obj, dict):
                return {k: strip(v) for k, v in obj.items() if not k.startswith("_")}
            if isinstance(obj, list):
                return [strip(v) for v in obj]
            return obj

        layout_name = state.get("layout", "default")
        return {
            "user": state["user"],
            "categories": state["categories"],
            "receipts": strip(state["receipts"]),
            "claims": state["claims"],
            "expose_testids": state.get("expose_testids", True),
            "layout": layout_name,
            # The rendered vocabulary of the app. An agent sees these strings on
            # screen regardless, so publishing them here leaks nothing that a
            # screenshot would not.
            "layout_spec": LAYOUTS[layout_name],
        }

    # ---- routing --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/") :])

        if path == "/api/state":
            state = self.state.snapshot()
            return self._send(200, self._public_state(state))

        if path == "/api/reports/export.csv":
            return self._export_csv()

        if path == "/api/claims":
            state = self.state.snapshot()
            return self._send(200, {"claims": state["claims"]})

        m = re.fullmatch(r"/api/claims/([\w-]+)", path)
        if m:
            state = self.state.snapshot()
            claim = find_claim(state, m.group(1))
            if claim is None:
                return self._send(404, {"error": "claim not found"})
            return self._send(200, claim)

        return self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._read_json()

        if path == "/api/reset":
            state = self.state.reset()
            return self._send(200, self._public_state(state))

        m = re.fullmatch(r"/api/claims/([\w-]+)/lines", path)
        if m:
            return self._add_line(m.group(1), body)

        m = re.fullmatch(r"/api/claims/([\w-]+)/receipts", path)
        if m:
            return self._attach_receipt(m.group(1), body)

        m = re.fullmatch(r"/api/claims/([\w-]+)/submit", path)
        if m:
            return self._submit(m.group(1), body)

        return self._send(404, {"error": "not found"})

    def do_PATCH(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._read_json()
        m = re.fullmatch(r"/api/claims/([\w-]+)", path)
        if m:
            return self._patch_claim(m.group(1), body)
        return self._send(404, {"error": "not found"})

    # ---- handlers -------------------------------------------------------
    def _patch_claim(self, claim_id: str, body: dict):
        def apply(state: dict):
            claim = find_claim(state, claim_id)
            if claim is None:
                return {"error": "claim not found"}
            if claim["status"] != "draft":
                return {"error": "submitted claims are read-only"}
            for field in ("title", "category", "cost_center", "note"):
                if field in body:
                    claim[field] = body[field]
            claim["validation_errors"] = validate(claim)
            return {"claim": claim}

        result, state = self.state.mutate(apply)
        if "error" in result:
            return self._send(400, result)
        return self._send(200, {**result, "state": self._public_state(state)})

    def _add_line(self, claim_id: str, body: dict):
        def apply(state: dict):
            claim = find_claim(state, claim_id)
            if claim is None:
                return {"error": "claim not found"}
            if claim["status"] != "draft":
                return {"error": "submitted claims are read-only"}
            try:
                amount = round(float(body["amount"]), 2)
            except (KeyError, TypeError, ValueError):
                return {"error": "amount must be a number"}
            if amount <= 0:
                return {"error": "amount must be positive"}
            line = {
                "id": f"ln_{len(claim['lines']) + 1:02d}",
                "description": str(body.get("description") or "").strip(),
                "amount": amount,
                "receipt_id": body.get("receipt_id"),
            }
            claim["lines"].append(line)
            claim["validation_errors"] = validate(claim)
            return {"claim": claim, "line": line}

        result, state = self.state.mutate(apply)
        if "error" in result:
            return self._send(400, result)
        return self._send(200, {**result, "state": self._public_state(state)})

    def _attach_receipt(self, claim_id: str, body: dict):
        def apply(state: dict):
            claim = find_claim(state, claim_id)
            if claim is None:
                return {"error": "claim not found"}
            if claim["status"] != "draft":
                return {"error": "submitted claims are read-only"}
            receipt_id = body.get("receipt_id")
            receipt = next(
                (r for r in state["receipts"] if r["id"] == receipt_id), None
            )
            if receipt is None:
                return {"error": "receipt not found"}
            if not receipt["available"]:
                return {"error": "receipt is no longer available"}
            if receipt_id in claim["receipts"]:
                return {"error": "receipt already attached"}
            claim["receipts"].append(receipt_id)
            claim["validation_errors"] = validate(claim)
            return {"claim": claim, "receipt": receipt}

        result, state = self.state.mutate(apply)
        if "error" in result:
            return self._send(400, result)
        return self._send(200, {**result, "state": self._public_state(state)})

    def _submit(self, claim_id: str, body: dict):
        def apply(state: dict):
            claim = find_claim(state, claim_id)
            if claim is None:
                return {"error": "claim not found", "status": 404}
            if claim["status"] != "draft":
                return {"error": "claim already submitted", "status": 400}
            if not body.get("confirmed"):
                return {"error": "confirmation required", "status": 400}
            errors = validate(claim)
            if errors:
                return {
                    "error": "claim cannot be submitted",
                    "validation_errors": errors,
                    "status": 422,
                }
            claim["status"] = "pending_approval"
            claim["submitted_at"] = "2026-03-31T17:04:00Z"
            claim["total"] = total_of(claim)
            claim["approver"] = "M. Okonkwo"
            claim["validation_errors"] = []
            return {"claim": claim}

        result, state = self.state.mutate(apply)
        if "error" in result:
            return self._send(result.pop("status", 400), result)
        return self._send(200, {**result, "state": self._public_state(state)})

    # ---- static ---------------------------------------------------------
    def _export_csv(self):
        """Download the period's claim lines as CSV.

        Deliberately unfiltered: every claim in the period is exported with its
        status, category and cost center, and deciding which rows belong in a
        report is the task. Pre-filtering here would remove the judgement.
        """
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        period = (params.get("period") or [""])[0]
        state = self.state.snapshot()

        rows = []
        for claim in state["claims"]:
            if period and claim.get("period") != period:
                continue
            for line in claim["lines"]:
                rows.append({
                    "claim_id": claim["id"],
                    "claim_title": claim["title"],
                    "period": claim.get("period") or "",
                    "status": claim["status"],
                    "category": claim.get("category") or "",
                    "cost_center": claim.get("cost_center") or "",
                    "line_description": line.get("description") or "",
                    "amount": f"{line['amount']:.2f}",
                })

        columns = ["claim_id", "claim_title", "period", "status", "category",
                   "cost_center", "line_description", "amount"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        filename = f"expense-lines-{period or 'all'}.csv"
        body = buf.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel: str) -> None:
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._send(404, {"error": "not found"})
        ctype = {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--variant", default="default")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    Handler.state = AppState(args.variant)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ExpenseDesk [{args.variant}] serving on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
