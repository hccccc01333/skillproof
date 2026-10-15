"""Compare a recording against an induced skill on a site this project does not own.

The benchmark can compare them because it owns the app: it resets server state
between conditions and reads the result back. A third-party site offers neither,
so this harness does the two things that are still possible:

  * **outcome from the page.** Success is the order confirmation appearing. No
    server state, no rubric -- a person can see whether it worked.
  * **perturbation by rewriting what the browser sees.** The site cannot be
    revised, but the accessible names the agent learned can be renamed on load,
    which is the same change from the agent's side.

That makes the project's central claim testable where it matters: on someone
else's page, after it changes.

    # record and induce first
    python bench/external/saucedemo.py
    python run_induct.py --episode saucedemo

    # the recording, on the page as it was
    python bench/external/harness.py --mode replay
    # the recording, after the controls are renamed
    python bench/external/harness.py --mode replay --perturb
    # the skill, after the controls are renamed
    python bench/external/harness.py --mode skill --perturb
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (ROOT, ROOT / "bench", ROOT / "replay"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from playwright.sync_api import sync_playwright  # noqa: E402

from replay.macro import _perform, load_actions, resolve_target  # noqa: E402

SITE = "https://www.saucedemo.com"
EPISODE = ROOT / "episodes" / "saucedemo"
PERTURB = Path(__file__).parent / "perturb-saucedemo.js"
INSTRUCTION = (
    "Log in, add the cheapest item to the cart, and complete checkout with the "
    "name 'Dana Whitfield' and postal code '18503'."
)

# What "it worked" means on a page that exposes nothing. Deliberately read from
# the rendered confirmation rather than from the cart, because the cart is gone
# by the time anyone looks.
SUCCESS_TEXT = "Thank you for your order!"


def order_completed(page) -> bool:
    try:
        return SUCCESS_TEXT.lower() in page.inner_text("body").lower()
    except Exception:  # noqa: BLE001
        return False


def run_replay(page, *, perturb_js: str | None) -> dict:
    """Replay the recorded actions verbatim, resolving targets by name."""
    actions = load_actions(EPISODE)
    steps = []
    page.goto(SITE, wait_until="networkidle")
    if perturb_js:
        page.add_script_tag(content=perturb_js)
        page.wait_for_timeout(250)

    for a in actions:
        if a["kind"] in ("observe", "verify"):
            steps.append({"step": a["sequence_index"], "kind": a["kind"],
                          "resolved_by": "skipped", "ok": True})
            continue
        loc, rung = resolve_target(page, a.get("target"))
        if loc is None:
            steps.append({"step": a["sequence_index"], "kind": a["kind"],
                          "caption": a["caption"], "resolved_by": "failed", "ok": False,
                          "error": "target not found on the current page"})
            continue
        try:
            _perform(page, a, loc)
            page.wait_for_timeout(300)
            steps.append({"step": a["sequence_index"], "kind": a["kind"],
                          "caption": a["caption"], "resolved_by": rung, "ok": True})
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": a["sequence_index"], "kind": a["kind"],
                          "caption": a["caption"], "resolved_by": rung, "ok": False,
                          "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
        if perturb_js:
            # The site re-renders on navigation, so the rename has to be
            # reapplied to whatever the new page contains.
            page.add_script_tag(content=perturb_js)
            page.wait_for_timeout(150)

    return {"steps": steps, "failed": [s for s in steps if not s["ok"]]}


def run_skill(*, perturb_js: str | None, workspace: Path) -> dict:
    """Run the induced skill through the same executor the benchmark uses."""
    from executor.agent import execute
    from verifier import Verifier

    skill_dir = next((ROOT / "induced" / "saucedemo").rglob("SKILL.md")).parent
    guidance = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    verifier = Verifier.find(skill_dir)

    run = execute(
        base_url=SITE,
        variant="external",
        instruction=INSTRUCTION,
        condition="skill",
        guidance_text=guidance,
        verifier=verifier,
        workspace=workspace,
        max_steps=30,
        reset=False,
        capture_state=False,
        perturb_js=perturb_js,
    )
    report = run.verifier_at_finish or {}
    return {
        "completed": run.finished and bool(report.get("passed")),
        "steps": [{"step": s.step, "kind": s.tool, "ok": True} for s in run.steps],
        "failed": [],
        "declared_done": run.finished,
        "verifier_passed": bool(report.get("passed")),
        "verifier_runs": run.verifier_runs,
        "done_rejections": run.done_rejections,
        "gaps": report.get("gaps", []),
        "finish_note": run.finish_note,
        "tokens": run.prompt_tokens + run.completion_tokens,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="replay", choices=["replay", "skill"])
    ap.add_argument("--perturb", action="store_true",
                    help="rename the site's controls on every page load")
    ap.add_argument("--strong", action="store_true",
                    help="with --perturb, also rewrite ids and test hooks, the way a "
                         "framework update regenerates them. Comparable to the "
                         "benchmark's relayout-nostid.")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    if not EPISODE.is_dir():
        print(f"missing episode {EPISODE}. Run: python bench/external/saucedemo.py",
              file=sys.stderr)
        return 2

    perturb_js = PERTURB.read_text(encoding="utf-8") if args.perturb else None
    if args.strong:
        # Read before the site's own scripts run, so the flag is set by the time
        # the init script evaluates.
        perturb_js = ("window.__S2S_PERTURB_STRONG = true;\n" + (perturb_js or ""))
        if not args.perturb:
            raise SystemExit("--strong needs --perturb")
    if args.mode == "skill":
        import tempfile

        t0 = time.time()
        result = run_skill(perturb_js=perturb_js,
                           workspace=Path(tempfile.mkdtemp(prefix="external-")))
        result |= {"mode": "skill", "site": SITE, "perturbed": bool(args.perturb),
                   "wall_ms": int((time.time() - t0) * 1000),
                   "at": datetime.now(timezone.utc).isoformat()}
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        name = f"external-skill-{'perturbed' if args.perturb else 'asis'}.json"
        (out / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"mode      : skill{' (controls renamed)' if args.perturb else ''}")
        print(f"site      : {SITE}")
        print(f"order completed: {result['completed']}")
        print(f"declared done: {result['declared_done']}  verifier passed: {result['verifier_passed']}")
        print(f"steps     : {len(result['steps'])}, completion refused {result['done_rejections']}x")
        for g in result.get("gaps", []):
            print(f"  [GAP] {g[:100]}")
        print(f"\nwrote {out / name}")
        return 0

    t0 = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 860})
        page = context.new_page()
        result = run_replay(page, perturb_js=perturb_js)
        result["completed"] = order_completed(page)
        result["final_url"] = page.url
        context.close()
        browser.close()

    result |= {
        "mode": "replay",
        "site": SITE,
        "perturbed": bool(args.perturb),
        "strong": bool(args.strong),
        "wall_ms": int((time.time() - t0) * 1000),
        "at": datetime.now(timezone.utc).isoformat(),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    label = "strong" if args.strong else ("perturbed" if args.perturb else "asis")
    name = f"external-replay-{label}.json"
    (out / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"mode      : replay{' (controls renamed)' if args.perturb else ''}")
    print(f"site      : {SITE}")
    print(f"order completed: {result['completed']}")
    print(f"steps     : {len(result['steps'])}, failed {len(result['failed'])}")
    for s in result["failed"][:6]:
        print(f"  step {s['step']:>2} {s.get('caption','')[:44]:<46} {s.get('error','')[:60]}")
    print(f"\nwrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
