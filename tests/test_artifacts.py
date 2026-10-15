"""Contract tests for the artifacts this repo ships.

`tests/test_tools.py` tests the induction tool surface. This tests the *data*:
the recorded episodes and the induced skills that are checked in, the run
evidence behind every published number, and the published policy document that
the rubrics claim to implement.

They exist because shipped artifacts rot silently. A hand-edited episode, a
skill whose frontmatter drifted from its folder name, a verifier that stopped
parsing, a rubric item that no longer maps to a stated rule, or a number whose
run file was deleted in a tidy-up -- none of those break any code path, and all
of them make the repo's claims unverifiable.

    python tests/test_artifacts.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "bench"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from induction.tools import VERIFIER_KINDS  # noqa: E402
from verifier import Assertion  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


# --------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------


def case_episodes() -> None:
    print("\n-- recorded episodes --")
    episodes = sorted(p for p in (ROOT / "episodes").iterdir() if p.is_dir() and p.name != "_work")
    check("at least one episode is checked in", bool(episodes))

    for ep in episodes:
        name = ep.name

        task_path = ep / "task.json"
        if not task_path.is_file():
            check(f"{name}: task.json present", False)
            continue

        task = json.loads(task_path.read_text(encoding="utf-8"))
        # The induction agent must not be able to see how it will be scored.
        leaked = [k for k in task if k.lower() in {"grading", "rubric", "grader", "answer"}]
        check(f"{name}: task.json carries no grading field", not leaked, str(leaked))
        check(f"{name}: task.json states an instruction", bool(task.get("instruction")))

        manifest = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
        check(f"{name}: manifest parses", manifest.get("episode_id") == name)

        # Counts must match what is on disk, or the manifest is lying.
        actions = (ep / "trace" / "actions.jsonl").read_text(encoding="utf-8").splitlines()
        actions = [a for a in actions if a.strip()]
        check(f"{name}: action count matches the trace",
              manifest["counts"]["actions"] == len(actions),
              f"manifest {manifest['counts']['actions']} vs file {len(actions)}")

        images = sorted((ep / "evidence").glob("*.png"))
        check(f"{name}: image count matches the evidence directory",
              manifest["counts"]["images"] == len(images),
              f"manifest {manifest['counts']['images']} vs disk {len(images)}")

        # Every listed file must exist; a manifest pointing at nothing is worse
        # than no manifest.
        missing = [f for f in manifest.get("files", []) if not (ep / f).exists()]
        check(f"{name}: every file the manifest lists exists", not missing, str(missing))

        # And every action must be valid JSON with the paper's core fields.
        bad = []
        for i, line in enumerate(actions):
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                bad.append(f"line {i} is not JSON")
                continue
            for field in ("sequence_index", "action_id", "kind", "media_time_ms", "caption"):
                if field not in a:
                    bad.append(f"action {i} has no {field}")
        check(f"{name}: every action record is well-formed", not bad, str(bad[:3]))


# --------------------------------------------------------------------------
# Induced skills
# --------------------------------------------------------------------------


def case_induced() -> None:
    print("\n-- induced skills --")
    manifests = sorted((ROOT / "induced").rglob("extraction-manifest.json"))
    check("at least one induction is checked in", bool(manifests))

    for mpath in manifests:
        run_dir = mpath.parent
        label = run_dir.parent.name
        manifest = json.loads(mpath.read_text(encoding="utf-8"))

        for entry in manifest.get("skills", []):
            skill_dir = run_dir / Path(entry["path"]).parent
            rel = f"{label}/{skill_dir.name}"

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                check(f"{rel}: SKILL.md exists", False)
                continue

            text = skill_md.read_text(encoding="utf-8")
            m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.+)$", text, re.DOTALL)
            check(f"{rel}: has frontmatter and a body", bool(m))
            if not m:
                continue

            front = m.group(1)
            name_m = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
            name = (name_m.group(1).strip() if name_m else "")
            check(f"{rel}: name matches its folder", name == skill_dir.name,
                  f"frontmatter {name!r} vs folder {skill_dir.name!r}")
            check(f"{rel}: name is lowercase hyphen-case",
                  bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name)))

            # Every shipped skill must carry a completion verifier, and every
            # assertion in it must be one the runtime can actually evaluate.
            vpath = skill_dir / "verify.json"
            if not vpath.is_file():
                check(f"{rel}: ships a completion verifier", False)
                continue
            data = json.loads(vpath.read_text(encoding="utf-8"))
            assertions = [Assertion.from_dict(a) for a in data.get("assertions", [])]
            problems: list[str] = []
            for a in assertions:
                problems.extend(a.problems())
            check(f"{rel}: verifier assertions are well-formed", not problems, str(problems[:2]))

            unknown = [a.kind for a in assertions if a.kind not in VERIFIER_KINDS]
            check(f"{rel}: every assertion type is implemented", not unknown, str(unknown))

            # A gap declared as a check can never pass, so the shipped verifier
            # would be unsatisfiable. That exact mistake was made once here.
            unfinishable = [
                a.id for a in assertions
                if a.kind != "unverifiable"
                and any(m in f"{a.description or ''} {a.value or ''}".upper()
                        for m in ("UNVERIFIED", "NOT VERIFIABLE", "CANNOT BE VERIFIED"))
            ]
            check(f"{rel}: no gap is written as a checkable assertion",
                  not unfinishable, str(unfinishable))

        # The manifest's own claim about the run must hold.
        check(f"{label}: run finalized", manifest.get("skills"),
              "manifest lists no skills")


# --------------------------------------------------------------------------
# Every published number still has its evidence
# --------------------------------------------------------------------------


def case_results_have_their_evidence() -> None:
    """A run file is the evidence behind a published number.

    `docs/results.md` is built from the runs in `results/`, and each run names
    the induced skill that produced it. Delete that skill later -- tidying up
    superseded drafts, say -- and the number stays in the document while the
    thing that produced it stops being re-derivable. That happened here: one
    commit dropped two superseded generations as a footnote and seven run files
    kept pointing at the empty paths.

    So every run in `results/` that names a skill must name one still on disk.
    A withdrawn referent goes to `results/_invalid/` (the run is not evidence,
    with the reason in its filename) or `results/_superseded/` (the finding was
    overturned), which is what keeps the exclusion auditable.
    """
    print("\n-- published numbers still have their evidence --")
    runs = sorted((ROOT / "results").glob("*.json"))
    check("there are run files to check", bool(runs))

    by_skill: dict[Path, list[str]] = {}
    for path in runs:
        data = json.loads(path.read_text(encoding="utf-8"))
        run = data.get("run") or {}
        skill_root = data.get("skill_root") or run.get("skill_root")
        if not skill_root:
            continue
        # Runs record absolute paths from the machine that produced them. Keep
        # the part from `induced` on, so the check means the same thing here as
        # it does on a fresh clone.
        parts = Path(str(skill_root).replace("\\", "/")).parts
        rel = Path(*parts[parts.index("induced"):]) if "induced" in parts else Path(skill_root)
        by_skill.setdefault(rel, []).append(path.name)

    for rel, files in sorted(by_skill.items()):
        check(f"{rel} — cited by {len(files)} run(s)", (ROOT / rel).is_dir(),
              "gone; move those runs to _invalid/ or _superseded/")

    # A check that examined nothing passes on an empty directory, and this repo
    # has shipped that mistake before.
    check("at least one run names a skill", bool(by_skill),
          "no run file referenced a skill — the check would be vacuous")

    # The documents name run files as their evidence. A name that matches no
    # file is a citation to nothing, and a citation to nothing is how the drift
    # above started: the claim stayed, the evidence left.
    cited: set[str] = set()
    for doc in (ROOT / "README.md", ROOT / "docs" / "results.md"):
        cited.update(re.findall(r"exec-[A-Za-z0-9_+.-]*\.json", doc.read_text(encoding="utf-8")))
    check("the documents cite run files at all", bool(cited), str(sorted(cited)[:3]))
    present = {p.name for p in (ROOT / "results").rglob("*.json")}
    absent = sorted(n for n in cited if n not in present)
    check("every run file the documents cite exists", not absent, str(absent))


# --------------------------------------------------------------------------
# The published policy and the rubrics must agree
# --------------------------------------------------------------------------


def case_policy_matches_rubric() -> None:
    print("\n-- policy document matches the rubrics --")
    policy = ROOT / "docs" / "policies" / "expense-policy.md"
    if not policy.is_file():
        check("policy document is published", False)
        return
    text = policy.read_text(encoding="utf-8")

    from evaluator import REPORT_TASK_ID, evaluate, evaluate_report
    from server import AppState

    # A real state, not an empty dict: evaluate() returns early when the claim
    # is missing, and the weight check then has nothing to sum.
    def submit_rubric():
        return evaluate("default", AppState("default").snapshot())

    # The policy claims a mapping from every rubric item to a stated rule. If a
    # rubric item is added and the document is not updated, the mapping table
    # stops being true and the claim "you can check the scoring" is hollow.
    for task, rubric in (("expense-submit", submit_rubric()),
                         (REPORT_TASK_ID, evaluate_report("reports", {}, None))):
        ids = [i.id for i in rubric.get("items", [])]
        for item_id in ids:
            # Each rubric id must appear in the policy's mapping table.
            pattern = rf"\|\s*`?{task}`?\s*\|\s*{item_id}\b|\|\s*{item_id}\s*\|"
            if not re.search(rf"\b{item_id}\b", text):
                check(f"policy mentions {task}/{item_id}", False,
                      "rubric item has no rule in the policy document")
        if ids:
            check(f"policy covers every {task} rubric item",
                  all(re.search(rf"\b{i}\b", text) for i in ids),
                  "some rubric ids are absent from the document")

    # And the weights must add up, or "score 100" means nothing.
    for task, rubric in (("expense-submit", submit_rubric()),
                         (REPORT_TASK_ID, evaluate_report("reports", {}, None))):
        total = sum(i.weight for i in rubric.get("items", []))
        check(f"{task}: rubric weights sum to 100", total == 100, f"got {total}")


# --------------------------------------------------------------------------
# The documentation and the code must agree
# --------------------------------------------------------------------------


def case_readme_matches_code() -> None:
    """Every command the README shows must be a command that exists.

    A reader who copies an example and gets `unrecognized arguments` does not
    file an issue, they leave. Nothing checked this, and it is the same class as
    the policy-versus-rubric mismatch above: two artifacts describing one thing,
    drifting apart silently.
    """
    print("\n-- the README's commands exist --")
    import re
    import subprocess

    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    # Entry points, from the table that exists to list them.
    block = re.search(r"## Entry points(.*?)^## ", readme, re.M | re.S)
    check("the README has an entry-points table", bool(block))
    if block:
        names = sorted(set(re.findall(r"`([a-z_]+[.](?:py|sh|ps1))`", block.group(1))))
        check("it names more than one", len(names) > 1, str(names))
        for name in names:
            path = ROOT / name
            if not path.is_file():
                check(f"{name} exists", False, "named in the README, absent from the repo")
                continue
            if not name.endswith(".py"):
                check(f"{name} exists", True)
                continue
            proc = subprocess.run(
                [sys.executable, str(path), "--help"],
                capture_output=True, text=True, timeout=60,
            )
            check(f"{name} runs --help", proc.returncode == 0 and
                  "usage" in (proc.stdout + proc.stderr).lower())

        # And every flag the README's examples pass must be a flag that script
        # has. The examples are what a reader copies.
        documented = _documented_flags(readme)
        # A check that examined nothing must say so. This one did not, once.
        check("the examples contain flags worth checking",
              sum(len(f) for f in documented.values()) > 0,
              "no flags were parsed; the check is not checking anything")

        for script, flags in documented.items():
            # Not every documented script sits at the root -- bench/external
            # does too -- and looking only there skips the rest in silence,
            # which is the same failure this check was written to stop making.
            found = sorted(
                p for p in ROOT.rglob(script)
                if ".venv" not in p.parts and "_ref" not in p.parts
            )
            if not found:
                check(f"{script} exists somewhere", False,
                      "named in a README example, absent from the repo")
                continue
            path = found[0]
            proc = subprocess.run(
                [sys.executable, str(path), "--help"],
                capture_output=True, text=True, timeout=60,
            )
            helptext = proc.stdout + proc.stderr
            for flag in sorted(flags):
                check(f"{script} accepts {flag}", flag in helptext,
                      "shown in a README example but absent from its --help")


def _documented_flags(readme: str) -> dict[str, set[str]]:
    """Flags passed to a script inside the README's bash examples.

    Continuation lines are joined first, and the join has to tolerate either
    line ending: this checkout is CRLF on Windows and LF elsewhere, and a
    `replace` that assumes one matches nothing on the other.

    That is not hypothetical. The first version of this scanned line by line, so
    it found the script name on one line and the flags on the next and paired
    neither, and the second version's join assumed LF and matched nothing on
    CRLF. Both returned an empty dict and both made the caller pass -- a check
    for vacuous checks that was itself vacuous, twice.
    """
    joined = re.sub(r"\\\r?\n", " ", readme)
    script_re = re.compile(r"([a-z_]+[.]py)")
    flag_re = re.compile(r"(?<![\w-])(--[a-z][a-z-]+)")

    out: dict[str, set[str]] = {}
    for line in joined.splitlines():
        m = script_re.search(line)
        if not m:
            continue
        flags = set(flag_re.findall(line))
        if flags:
            out.setdefault(m.group(1), set()).update(flags)
    return out


def main() -> int:
    case_episodes()
    case_induced()
    case_results_have_their_evidence()
    case_policy_matches_rubric()
    case_readme_matches_code()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all shipped artifacts are well-formed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
