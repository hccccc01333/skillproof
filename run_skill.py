"""Run an induced skill against a page. Any page.

    python run_skill.py --skill induced/my-run/my-skill \
        --url https://your-intranet/reports \
        --instruction "Prepare the monthly expense report and save it as report.json"

This is the step that was missing. `record_session.py` produces an episode and
`run_induct.py` turns it into a skill, but until now there was no way to *use*
one against anything except this repo's own benchmark app -- `run_exec.py` needs
a registered task id and scores against that task's rubric.

Here the target is a URL you supply and the judge is the skill's own verifier.
There is no rubric, because there is no benchmark: you look at what it did and
decide whether it is right. That is the honest arrangement for someone running
their own workflow, and it is why this file has no scoring in it.

The skill's `verify.json` is run at the end if it ships one, and its declared
gaps are printed alongside its checks. A gap is not a failure -- it is the part
of the task the skill is telling you it could not confirm.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from executor.agent import execute  # noqa: E402
from verifier import Verifier  # noqa: E402


def load_skill(skill_dir: Path) -> tuple[str, Path | None]:
    """Return the guidance text and the directory the verifier lives in.

    `skill_dir` may be the skill folder itself (`.../my-skill`) or the run
    directory above it (`.../my-episode--concise`), because people reasonably
    point at either.
    """
    skill_dir = Path(skill_dir).resolve()
    if (skill_dir / "SKILL.md").is_file():
        return (skill_dir / "SKILL.md").read_text(encoding="utf-8"), skill_dir
    manifests = sorted(skill_dir.glob("*/extraction-manifest.json"))
    if manifests:
        import json

        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        for entry in manifest.get("skills", []):
            folder = skill_dir / Path(entry["path"]).parent
            if (folder / "SKILL.md").is_file():
                return (folder / "SKILL.md").read_text(encoding="utf-8"), folder
    found = sorted(skill_dir.rglob("SKILL.md"))
    if len(found) == 1:
        return found[0].read_text(encoding="utf-8"), found[0].parent
    raise SystemExit(
        f"could not find one skill under {skill_dir}. Pass the folder containing "
        f"SKILL.md, or a run directory holding exactly one."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True, help="skill folder, or a run directory containing one")
    ap.add_argument("--url", required=True, help="page to run against")
    ap.add_argument("--instruction", required=True,
                    help="the goal, phrased as a request. The skill supplies the procedure; "
                         "this supplies the target and the values.")
    ap.add_argument("--workspace", default=None,
                    help="directory for downloads and deliverables. Defaults to a temp dir.")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--headed", action="store_true", help="watch it run")
    ap.add_argument("--perturb", default=None, metavar="JS",
                    help="JavaScript applied on every page load, to simulate the site "
                         "changing under a skill. Same idea as the benchmark's relayout "
                         "variant, for a site whose source you do not have.")
    ap.add_argument("--quiet", action="store_true", help="only print the outcome")
    args = ap.parse_args()

    guidance, verifier_dir = load_skill(Path(args.skill))
    verifier = Verifier.find(verifier_dir) if verifier_dir else None

    if args.workspace:
        workspace = Path(args.workspace)
    else:
        import tempfile

        workspace = Path(tempfile.mkdtemp(prefix="skillproof-run-"))
    workspace.mkdir(parents=True, exist_ok=True)

    print(f"skill     : {Path(args.skill).resolve()}")
    print(f"verifier  : {'yes' if verifier else 'none shipped'}"
          + (f" ({len(verifier.assertions)} assertions)" if verifier else ""))
    print(f"target    : {args.url}")
    print(f"workspace : {workspace}")
    print()

    run = execute(
        base_url=args.url,
        variant="external",
        instruction=args.instruction,
        condition="skill",
        guidance_text=guidance,
        verifier=verifier,
        workspace=workspace,
        max_steps=args.max_steps,
        reset=False,          # an arbitrary page has no reset endpoint
        capture_state=False,  # and no state endpoint to read
        perturb_js=(Path(args.perturb).read_text(encoding="utf-8") if args.perturb else None),
        headed=args.headed,
        verbose=not args.quiet,
    )

    print()
    print(f"steps {len(run.steps)}  wall {run.wall_ms / 1000:.0f}s  "
          f"tokens {run.prompt_tokens + run.completion_tokens:,}")
    print(f"declared done: {run.finished}")
    if run.finish_note:
        print(f"  \"{run.finish_note[:300]}\"")

    if run.verifier_present:
        report = run.verifier_at_finish or {}
        print(f"verifier: {'PASSED' if report.get('passed') else 'NOT PASSED'} "
              f"({run.verifier_runs} run(s), {run.done_rejections} completion attempt(s) refused)")
        # Checks and gaps are different things and must not both be printed as
        # results. A declared gap returns ok=True -- it is not a failure -- so
        # printing every result and then the gaps again showed each gap twice,
        # once as PASS. That reads as "this was verified", which is the opposite
        # of what a gap means.
        for r in report.get("results", []):
            if r.get("type") == "unverifiable":
                continue
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"  [{mark}] {r['id']}: {r['description'][:80]}")
        gaps = report.get("gaps", [])
        if gaps:
            print()
            print(f"  {len(gaps)} thing(s) this skill cannot check:")
            for gap in gaps:
                print(f"    - {gap[:150]}")

    files = sorted(p for p in workspace.rglob("*") if p.is_file())
    if files:
        print(f"\nproduced in {workspace}:")
        for f in files:
            print(f"  {f.relative_to(workspace).as_posix()}  {f.stat().st_size:,} B")

    if run.errors:
        print("\nerrors:")
        for e in run.errors:
            print(f"  {e[:200]}")

    # No score. There is no rubric here and inventing one would be guessing at
    # what the user meant; the verifier and the trajectory are the evidence.
    return 0 if run.finished else 1


if __name__ == "__main__":
    raise SystemExit(main())
