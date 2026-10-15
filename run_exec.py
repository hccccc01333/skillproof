"""Downstream execution for one condition.

Neutral naming on purpose: "no-skill" is the original agent, "skill" is the
same agent with induced guidance appended. The code path is identical, so a
difference between them is attributable to the guidance.

    .venv/Scripts/python.exe run_exec.py --condition no-skill  --variant default
    .venv/Scripts/python.exe run_exec.py --condition skill     --variant default
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "bench"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evaluator import evaluate_any, format_report  # noqa: E402
from llm import model_name as _llm_default  # noqa: E402
from verifier import Verifier  # noqa: E402
from executor.agent import execute  # noqa: E402
from run_sample import free_port, wait_for  # noqa: E402

from recorder.tasks import TASKS, instruction_for  # noqa: E402


def load_guidance(skill_root: Path) -> str:
    """Concatenate the final SKILL.md files, in the manifest's order.

    The manifest's `skills` list is used rather than a glob, so abandoned
    drafts that the finalizer flagged as orphans are excluded. Feeding those to
    the executor would smuggle unvalidated output into the treatment.
    """
    manifest_path = skill_root / "extraction-manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"no extraction manifest at {manifest_path}; run run_induct.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parts = []
    for entry in manifest["skills"]:
        text = (skill_root / entry["path"]).read_text(encoding="utf-8")
        parts.append(text.strip())
    return "\n\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True,
                    choices=["no-skill", "skill", "skill+verifier"])
    ap.add_argument("--variant", default=None,
                    choices=["default", "jitter", "jitter-nostid", "jitter-remap", "relayout", "relayout-nostid"])
    ap.add_argument("--task", default="expense-submit")
    ap.add_argument("--skill-root", default=str(ROOT / "induced/run3/expense-submit-default--concise"))
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--workspace", default=None,
                    help="scratch directory the agent may download into and write to")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--rep", type=int, default=1,
                    help="repetition index; a single run per cell is not a result")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.variant is None:
        args.variant = {"expense-report": "reports",
                        "expense-report-hard": "reports-hard"}.get(args.task, "default")
    task = TASKS[args.task]
    instruction = instruction_for(args.task, args.variant)
    uses_skill = args.condition in ("skill", "skill+verifier")
    workspace = Path(args.workspace) if args.workspace else None
    if workspace is not None:
        import shutil as _sh
        _sh.rmtree(workspace, ignore_errors=True)
        workspace.mkdir(parents=True, exist_ok=True)

    guidance = load_guidance(Path(args.skill_root)) if uses_skill else None
    verifier = None
    if args.condition == "skill+verifier":
        verifier = Verifier.find(Path(args.skill_root))
        if verifier is None:
            raise SystemExit(
                f"--condition skill+verifier needs a verify.json under {args.skill_root}; "
                f"re-run run_induct.py with the current authoring policy")
        bad = verifier.problems()
        if bad:
            raise SystemExit("the generated verifier is malformed: " + "; ".join(bad))

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "bench" / "site" / "server.py"),
         "--port", str(port), "--variant", args.variant],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    wait_for(f"http://127.0.0.1:{port}/api/state")
    print(f"[serve] variant={args.variant} on {base_url}")
    print(f"[exec]  condition={args.condition} "
          f"model={os.environ.get('S2S_INDUCT_MODEL') or _llm_default()}")
    try:
        run = execute(
            base_url=base_url,
            variant=args.variant,
            instruction=instruction,
            condition=args.condition,
            guidance_text=guidance,
            verifier=verifier,
            workspace=workspace,
            max_steps=args.max_steps,
            headed=args.headed,
            verbose=args.verbose,
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    rubric = evaluate_any(args.task, args.variant, run.final_state or {}, workspace)

    record = {
        "condition": args.condition,
        "variant": args.variant,
        "task": args.task,
        "instruction": instruction,
        "workspace": str(workspace) if workspace else None,
        "rep": args.rep,
        "skill_root": str(args.skill_root) if uses_skill else None,
        "verifier_assertions": [a.to_dict() for a in verifier.assertions] if verifier else None,
        "score": rubric["score"],
        "sr": rubric["sr"],
        "passed": rubric.get("passed", False),
        "rubric_items": [
            {"id": i.id, "weight": i.weight, "requirement": i.requirement,
             "satisfied": i.satisfied, "detail": i.detail}
            for i in rubric.get("items", [])
        ],
        "run": run.to_dict(),
    }

    # The skill under test is part of the result's identity. Without it, two
    # runs differing only in which skill they used write to the same path and
    # the slower one silently wins -- which happened twice here, once hiding a
    # run that had used a verifier known to be broken.
    skill_tag = ""
    if uses_skill:
        skill_tag = "-" + Path(args.skill_root).parent.name.replace("--", "-")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exec-{args.condition}-{args.variant}-r{args.rep}{skill_tag}.json"
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"## {args.condition} · variant=`{args.variant}` · rep {args.rep}"
          + (f" · skill=`{Path(args.skill_root).parent.name}`" if uses_skill else ""))
    print()
    print(f"steps={len(run.steps)}  declared_done={run.finished}  wall={run.wall_ms} ms  "
          f"tokens={run.prompt_tokens + run.completion_tokens:,}")
    if run.verifier_present:
        print(f"verifier: runs={run.verifier_runs}  done_rejections={run.done_rejections}  "
              f"final={'PASS' if (run.verifier_at_finish or {}).get('passed') else 'FAIL'}")
    if run.finish_note:
        print(f'finish note: "{run.finish_note[:200]}"')
    if run.errors:
        print(f"errors: {run.errors}")
    print()
    print(format_report(rubric))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
