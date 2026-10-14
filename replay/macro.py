"""Macro replay: the fixed-action-sequence baseline.

This is the baseline the Work2Skill paper does *not* test. Its three
comparison methods (No Skill, ShowUI-Aloha, Demo2Tutorial) all produce *text
guidance* that a model then interprets. None of them asks the obvious cheaper
question: if we simply replay the recorded action sequence verbatim, how far
does it get?

Why this baseline decides the project
-------------------------------------
If a fixed macro matches an induced skill on the demonstrated task, induction
is not earning its cost. If the macro holds on the demonstrated task but
breaks when the page changes, that gap *is* the case for induction -- and it
is evidence the paper does not provide.

Mechanics
---------
Replay issues each recorded action against the live application using the
values recorded at demonstration time, with no adaptation of any kind. Target
resolution walks a fallback ladder and records which rung it used, because the
rung is the diagnosis: a macro that still resolves by `data-testid` is fine,
one that has fallen through to positional CSS is already fragile.

Actions are re-issued verbatim. If the demonstration entered `412.80`, replay
enters `412.80`, even when the receipt on screen now says `538.20`. That is the
whole point -- a macro cannot re-read the page.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from playwright.sync_api import Locator, Page, TimeoutError as PWTimeout


@dataclass
class ReplayStep:
    sequence_index: int
    action_id: str
    kind: str
    caption: str
    resolved_by: str  # "testid" | "role+name" | "css" | "skipped" | "failed"
    ok: bool
    error: str | None = None
    duration_ms: int = 0
    value_source: str | None = None  # "page" | "recorded", reparam mode only
    value_used: str | None = None


@dataclass
class ReplayResult:
    episode_id: str
    variant: str
    reparam: bool = False
    steps: list[ReplayStep] = field(default_factory=list)
    final_state: dict | None = None
    wall_ms: int = 0

    @property
    def failed(self) -> list[ReplayStep]:
        return [s for s in self.steps if not s.ok]

    def resolution_histogram(self) -> dict[str, int]:
        hist: dict[str, int] = {}
        for s in self.steps:
            hist[s.resolved_by] = hist.get(s.resolved_by, 0) + 1
        return hist

    def reparam_histogram(self) -> dict[str, int]:
        hist: dict[str, int] = {}
        for s in self.steps:
            if s.value_source:
                hist[s.value_source] = hist.get(s.value_source, 0) + 1
        return hist

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resolution_histogram"] = self.resolution_histogram()
        d["reparam_histogram"] = self.reparam_histogram()
        d["failed_count"] = len(self.failed)
        return d


# --------------------------------------------------------------------------
# Target resolution ladder
# --------------------------------------------------------------------------


def _by_testid(page: Page, testid: str) -> Locator | None:
    loc = page.get_by_test_id(testid)
    return loc.first if loc.count() > 0 else None


def _by_role_name(page: Page, role: str, name: str) -> Locator | None:
    """Exact-name role lookup. Returns None on ambiguity rather than guessing:
    a macro that silently picks the first of three buttons named 'Attach' is
    not resolving, it is gambling."""
    try:
        loc = page.get_by_role(role, name=name, exact=True)
    except Exception:
        return None
    n = loc.count()
    if n == 1:
        return loc.first
    return None


def _by_css(page: Page, css: str) -> Locator | None:
    if not css:
        return None
    try:
        loc = page.locator(css)
    except Exception:
        return None
    return loc.first if loc.count() > 0 else None


def resolve_target(page: Page, target: dict | None, reparam: bool = False) -> tuple[Locator | None, str]:
    """Walk the ladder. Returns (locator, rung).

    In reparam mode the `data-testid` rung is skipped on purpose: hooking onto
    a test id is the thing that does not survive contact with a site you do not
    control, so a re-parameterizing approach has to resolve the way a person
    would, by role and visible label.
    """
    if not target:
        return None, "failed"

    testid = target.get("testid")
    if testid and not reparam:
        loc = _by_testid(page, testid)
        if loc is not None:
            return loc, "testid"

    role, name = target.get("role"), target.get("name")
    if role and name:
        loc = _by_role_name(page, role, name)
        if loc is not None:
            return loc, "role+name"

    loc = _by_css(page, target.get("css_path") or "")
    if loc is not None:
        return loc, "css"

    return None, "failed"


# --------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------


def load_actions(episode_dir: Path) -> list[dict]:
    path = Path(episode_dir) / "trace" / "actions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------
# Re-parameterization
# --------------------------------------------------------------------------
#
# A verbatim macro fails a changed page for two quite different reasons, and
# telling them apart is what decides whether skill induction is worth building:
#
#   1. it writes values that were correct during recording and are stale now
#      ("CC-4471" when the page says "CC-5120"); and
#   2. it has no idea which receipts belong on a travel claim, so it cannot
#      choose targets at all.
#
# (1) is mechanical -- re-read the value from the page instead of replaying the
# literal. (2) requires understanding the task. This mode implements (1) and
# deliberately not (2), so that the gap it leaves is a measurement of how much
# of the problem is irreducible.
#
# The readers below are hand-written per field. That is the honest limitation
# of this baseline: someone had to look at the page and decide that the "Cost
# center" field should be read from the header readout and that an expense line
# takes its amount from the receipt it names. Hand-writing these is precisely
# what does not scale, and is the strongest argument for induction there is --
# but it has to be *measured* rather than asserted, which is what this does.
#
# A reader is looked up by the target's accessible name and returns the current
# value, or None to fall back to the recorded literal.

REPARAM_READERS: dict[str, str] = {
    # Cost center: the page shows the signed-in user's own cost center in the
    # header, as "<department> · <cost center>".
    "cost center": """
        () => {
            const el = document.querySelector('#user-meta');
            if (!el) return null;
            const m = el.innerText.match(/[A-Z]{2}-\\d{4}/);
            return m ? m[0] : null;
        }
    """,
    # Expense line amount: read the amount of the receipt most recently named
    # as a line description. Falls back to the label match if the exact
    # description is not found.
    "amount": """
        (hint) => {
            const rows = [...document.querySelectorAll('[data-testid^="receipt-"]')];
            const pick = rows.find(r => hint && r.innerText.includes(hint)) || null;
            if (!pick) return null;
            const m = pick.innerText.match(/\\$([\\d,]+\\.\\d{2})/);
            return m ? m[1].replace(/,/g, '') : null;
        }
    """,
}


def _reader_for(target: dict | None) -> str | None:
    name = ((target or {}).get("name") or "").strip().lower()
    if not name:
        return None
    if "cost center" in name:
        return REPARAM_READERS["cost center"]
    if "amount" in name:
        return REPARAM_READERS["amount"]
    return None


def resolve_value(page: Page, action: dict, hint: str | None) -> tuple[str | None, str]:
    """Return (value, source) where source is 'page' or 'recorded'."""
    recorded = action.get("value") or ""
    js = _reader_for(action.get("target"))
    if not js:
        return recorded, "recorded"
    try:
        if "(hint)" in js:
            fresh = page.evaluate(js, hint)
        else:
            fresh = page.evaluate(js)
    except Exception:  # noqa: BLE001
        return recorded, "recorded"
    if fresh and str(fresh).strip():
        return str(fresh).strip(), "page"
    return recorded, "recorded"


def _perform(page: Page, action: dict, loc: Locator, value: str | None = None) -> None:
    kind = action["kind"]
    v = action.get("value") if value is None else value
    if kind == "click":
        loc.click(timeout=5000)
    elif kind == "type":
        loc.fill(v or "", timeout=5000)
    elif kind == "select":
        loc.select_option(v or "", timeout=5000)
    else:
        raise ValueError(f"macro replay does not handle kind={kind!r}")


def replay_episode(
    *,
    episode_dir: Path,
    base_url: str,
    variant: str,
    reparam: bool = False,
    step_timeout_ms: int = 6000,
    settle_ms: int = 150,
) -> ReplayResult:
    """Replay a recorded episode against a live app and return the final state.

    With `reparam=True`, targets resolve by semantic role and accessible name
    rather than by test hook, and field values are re-read from the live page
    where a reader exists. Target *selection* is still taken from the recording
    -- only values are re-derived -- so the receipts this attaches are exactly
    the ones the demonstration attached, whatever the live page looks like.
    """
    from playwright.sync_api import sync_playwright

    episode_dir = Path(episode_dir)
    actions = load_actions(episode_dir)
    result = ReplayResult(episode_id=episode_dir.name, variant=variant)
    result.reparam = reparam

    t0 = time.monotonic()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 860})
        page = context.new_page()

        page.goto(base_url, wait_until="networkidle")
        page.request.post(f"{base_url}/api/reset")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(200)

        last_description: str | None = None

        for action in actions:
            kind = action["kind"]

            if kind in ("observe", "verify"):
                result.steps.append(
                    ReplayStep(action["sequence_index"], action["action_id"], kind,
                               action["caption"], "skipped", True)
                )
                continue

            step_t0 = time.monotonic()
            loc, rung = resolve_target(page, action.get("target"), reparam=reparam)
            if loc is None:
                result.steps.append(
                    ReplayStep(action["sequence_index"], action["action_id"], kind,
                               action["caption"], "failed", False,
                               "target could not be resolved on the current page")
                )
                # Keep going: a macro has no recovery policy, and stopping here
                # would just move the failure. Later steps will fail too, which
                # is itself the finding.
                continue

            value = action.get("value")
            value_source = "recorded"
            if reparam and kind in ("type", "select"):
                value, value_source = resolve_value(page, action, last_description)

            try:
                _perform(page, action, loc, value=value)
                page.wait_for_timeout(settle_ms)
                err = None
            except (PWTimeout, Exception) as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"

            if reparam and kind == "type" and value and _reader_for(action.get("target")) is None:
                # A free-text field that is not re-derived is a description;
                # remember it so a following amount can be tied to it.
                last_description = value

            result.steps.append(
                ReplayStep(action["sequence_index"], action["action_id"], kind,
                           action["caption"], rung, err is None, err,
                           int((time.monotonic() - step_t0) * 1000),
                           value_source=value_source if reparam else None,
                           value_used=str(value) if reparam else None)
            )

        page.wait_for_timeout(300)
        result.final_state = page.request.get(f"{base_url}/api/state").json()
        context.close()
        browser.close()

    result.wall_ms = int((time.monotonic() - t0) * 1000)
    return result


def format_report(result: ReplayResult, rubric: dict) -> str:
    from evaluator import format_report as rubric_report

    hist = ", ".join(f"{k}={v}" for k, v in sorted(result.resolution_histogram().items()))
    lines = [
        f"## Macro replay · {result.episode_id} · variant=`{result.variant}`",
        "",
        f"Replayed {len(result.steps)} actions in {result.wall_ms} ms.",
        f"Resolved by: {hist}",
        f"Failed steps: {len(result.failed)}",
    ]
    if result.failed:
        lines += ["", "Failures:", ""]
        for s in result.failed:
            lines.append(f"- step {s.sequence_index} `{s.caption}` — {s.error}")
    lines += ["", rubric_report(rubric), ""]
    return "\n".join(lines)
