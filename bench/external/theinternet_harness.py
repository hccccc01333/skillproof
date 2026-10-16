"""Run the induced the-internet skill and record what happened, in JSON.

The saucedemo harness (`harness.py`) does this for a shopping flow. This does it
for the login flow, and exists for the same reason: the benchmark's records are
produced by `run_exec.py` against an app this project owns, and a claim about
third-party pages needs records produced against a third-party page.

Three cases, which are the three questions the walkthrough asks:

    positive   the credentials the demonstration used -- does the skill work at
               all on the page it was recorded from?
    untaught   credentials the demonstration never showed (a wrong password).
               The task is then impossible, and the interesting output is not
               the score but whether the agent says it succeeded anyway.
    moved      the page's controls are renamed on load (`perturb-theinternet.js`)
               -- does the skill re-locate them by meaning? Add `--strong` to
               regenerate the ids too, which is what a framework update does and
               what a recording cannot survive.

Records land in `results/theinternet-<case>.json`.

    python bench/external/theinternet_harness.py --case positive
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SITE = "https://the-internet.herokuapp.com/login"
PERTURB = Path(__file__).resolve().parent / "perturb-theinternet.js"
SKILL_ROOT = ROOT / "induced" / "theinternet" / "theinternet--concise"

USER = "tomsmith"
GOOD = "SuperSecretPassword!"
BAD = "SuperSecretPassword"       # one character short, so the app rejects it


def instruction(user: str, password: str) -> str:
    return (
        f"Log in to the-internet with the username '{user}' and the password "
        f"'{password}', then confirm the secure area is displayed."
    )


CASES = {
    "positive": instruction(USER, GOOD),
    "untaught": instruction(USER, BAD),
    "moved": instruction(USER, GOOD),
}


def run(case: str, *, perturb_js: str | None) -> dict:
    from executor.agent import execute
    from verifier import Verifier

    skill_dir = next(SKILL_ROOT.rglob("SKILL.md")).parent
    guidance = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    verifier = Verifier.find(skill_dir)

    run_ = execute(
        base_url=SITE,
        variant=f"external-theinternet-{case}",
        instruction=CASES[case],
        condition="skill",
        guidance_text=guidance,
        verifier=verifier,
        workspace=Path(tempfile.mkdtemp(prefix=f"theinternet-{case}-")),
        max_steps=30,
        reset=False,
        capture_state=False,
        perturb_js=perturb_js,
    )
    report = run_.verifier_at_finish or {}
    checks = [r for r in report.get("results", []) if r.get("type") != "unverifiable"]
    return {
        "case": case,
        "site": SITE,
        "perturbed": bool(perturb_js),
        "instruction": CASES[case],
        # The rubric-free verdict: the agent's own claim, and what the page said.
        "declared_done": run_.finished,
        "verifier_passed": bool(report.get("passed")),
        "verifier_checks": [{"id": r["id"], "ok": r["ok"], "detail": r["detail"]}
                            for r in checks],
        "gaps": report.get("gaps", []),
        "verifier_runs": run_.verifier_runs,
        "done_rejections": run_.done_rejections,
        "steps": len(run_.steps),
        "trajectory": [{"step": s.step, "tool": s.tool, "args": s.args,
                        "result": str(s.result)[:200], "url": s.url}
                       for s in run_.steps],
        "wall_ms": run_.wall_ms,
        "prompt_tokens": run_.prompt_tokens,
        "completion_tokens": run_.completion_tokens,
        "finish_note": run_.finish_note,
        "final_url": run_.final_url if hasattr(run_, "final_url") else None,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, choices=sorted(CASES))
    ap.add_argument("--strong", action="store_true",
                    help="with the `moved` case, also regenerate the ids")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    if args.strong and args.case != "moved":
        raise SystemExit("--strong only applies to --case moved")

    perturb_js = None
    if args.case == "moved":
        perturb_js = PERTURB.read_text(encoding="utf-8")
        if args.strong:
            perturb_js = "window.__S2S_PERTURB_STRONG = true;\n" + perturb_js

    print(f"case      : {args.case}")
    print(f"agent     : {SITE}")
    if perturb_js:
        print(f"perturb   : {PERTURB.name}{' (strong)' if args.strong else ''}")
    t0 = time.time()
    result = run(args.case, perturb_js=perturb_js)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"theinternet-{args.case}{'-strong' if args.strong else ''}.json"
    (out / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"declared done    : {result['declared_done']}")
    print(f"verifier passed  : {result['verifier_passed']}  "
          f"({result['verifier_runs']} run(s), {result['done_rejections']} refusal(s))")
    for c in result["verifier_checks"]:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['id']}: {str(c['detail'])[:96]}")
    for gap in result["gaps"]:
        print(f"  [GAP ] {str(gap)[:96]}")
    print(f"steps {result['steps']}  wall {result['wall_ms'] / 1000:.0f}s  "
          f"tokens {result['prompt_tokens'] + result['completion_tokens']:,}")
    print(f"claimed: \"{str(result['finish_note'])[:220]}\"")
    print(f"-> {out / name}  (total {(time.time() - t0):.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
