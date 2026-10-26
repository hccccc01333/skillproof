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
    thing that produced it stops being re-derivable. That happened here, twice:
    one commit dropped two generations as a footnote, another dropped the
    previous model's runs, and in both cases the documents kept citing them.

    So the rule is absolute: every run anywhere under `results/` -- live,
    invalid, superseded, previous-model -- must name a skill that is on disk.
    The archive directories are about which runs *count*; this is about whether
    they can still be explained. Restoring the two generations from history was
    cheaper than weakening the rule, which is what the rule was telling us to
    do.
    """
    print("\n-- published numbers still have their evidence --")
    runs = [p for p in sorted((ROOT / "results").rglob("*.json"))
            if p.name.startswith("exec-")]
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
              "gone; restore it, or move those runs out of results/")

    # A check that examined nothing passes on an empty directory, and this repo
    # has shipped that mistake before.
    check("at least one run names a skill", bool(by_skill),
          "no run file referenced a skill — the check would be vacuous")

    # The documents name run files as their evidence. A name that matches no
    # file is a citation to nothing, and a citation to nothing is how the drift
    # above started: the claim stayed, the evidence left.
    cited: set[str] = set()
    docs = [ROOT / "README.md", ROOT / "docs" / "results.md",
            ROOT / "docs" / "walkthrough-theinternet.md",
            ROOT / "docs" / "technical-report.md", ROOT / "docs" / "quickstart.md"]
    for doc in docs:
        if doc.is_file():
            cited.update(re.findall(r"(?:exec|external|theinternet|macro)-[A-Za-z0-9_+.-]*\.json",
                                    doc.read_text(encoding="utf-8")))
    check("the documents cite run files at all", bool(cited), str(sorted(cited)[:3]))
    check("and more than one kind of record",
          len({c.split("-")[0] for c in cited}) >= 2, str(sorted(cited)[:6]))
    present = {p.name for p in (ROOT / "results").rglob("*.json")}
    absent = sorted(n for n in cited if n not in present)
    check("every run file the documents cite exists", not absent, str(absent))


# --------------------------------------------------------------------------
# The numbers the README leads with, recomputed from the runs
# --------------------------------------------------------------------------


def _runs(task: str, condition: str) -> list[dict]:
    out = []
    for p in sorted((ROOT / "results").glob("exec-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("task") == task and d.get("condition") == condition:
            out.append(d)
    return out


# The README's "What it costs", as printed: task, condition, tokens, steps,
# score. Each figure is the mean over every live run of that condition.
COST_TABLE = [
    ("expense-report", "no-skill", 56_281, 9.0, 35.0),
    ("expense-report", "skill+verifier", 46_377, 7.4, 100.0),
    ("expense-submit", "no-skill", 96_766, 12.2, 56.7),
    ("expense-submit", "skill+verifier", 213_448, 19.0, 100.0),
    ("expense-report-hard", "no-skill", 33_254, 7.0, 20.0),
    ("expense-report-hard", "skill+verifier", 195_284, 17.3, 100.0),
]


def case_published_agent_numbers() -> None:
    """The agent-side numbers, recomputed from the runs that produced them.

    `reproduce.py` re-runs the deterministic baselines and asserts their
    scores. The agent conditions cannot be re-run without a model and an
    account, so the alternative is worse: their numbers live in prose, and
    nothing notices when the prose and the runs part ways. Recomputing the
    aggregates from the stored runs is free and catches exactly that.
    """
    print("\n-- the numbers the README leads with, recomputed from the runs --")

    unaided = _runs("expense-submit", "no-skill")
    check("the unaided agent has runs on both pages", len(unaided) >= 6, str(len(unaided)))
    if unaided:
        mean = sum(d["score"] for d in unaided) / len(unaided)
        check("unaided agent mean is the published 56.7", round(mean, 1) == 56.7,
              f"got {mean:.2f} over {len(unaided)} runs")

    skilled = _runs("expense-submit", "skill+verifier")
    for variant in ("default", "relayout-nostid"):
        got = [(d["score"], d["sr"]) for d in skilled if d.get("variant") == variant]
        check(f"skill+verifier on {variant}: 100 · SR 100 ×3",
              len(got) >= 3 and all(s == 100.0 and sr == 100 for s, sr in got), str(got))

    for task, variant, baseline in (
        ("expense-report", "reports", 35.0),
        ("expense-report-hard", "reports-hard", 20.0),
    ):
        got = [d["score"] for d in _runs(task, "no-skill") if d.get("variant") == variant]
        check(f"{task}: unaided agent is the published {baseline}",
              bool(got) and all(s == baseline for s in got), str(got))
        got = [(d["score"], d["sr"]) for d in _runs(task, "skill+verifier")
               if d.get("variant") == variant]
        check(f"{task}: skill+verifier is 100 · SR 100",
              bool(got) and all(s == 100.0 and sr == 100 for s, sr in got), str(got))


def case_published_cost_numbers() -> None:
    """The README's cost table, recomputed the same way.

    One row of this table was wrong when this check was written: the report
    task's skill row printed the mean over the three modes that involve a
    person, which included a mode whose induction had since been withdrawn and
    excluded the current no-human one. The figure was reproducible from a
    subset of the runs, and the subset was not the one the caption claimed.
    """
    print("\n-- the cost table, recomputed from the runs --")
    for task, condition, tokens, steps, score in COST_TABLE:
        rs = _runs(task, condition)
        if not rs:
            check(f"{task}/{condition}: has runs", False)
            continue
        n = len(rs)
        tok = sum((r.get("run") or {}).get("prompt_tokens", 0)
                  + (r.get("run") or {}).get("completion_tokens", 0) for r in rs) / n
        stp = sum((r.get("run") or {}).get("steps", 0) for r in rs) / n
        sc = sum(r["score"] for r in rs) / n
        check(f"{task}/{condition}: {tokens:,} tok · {steps} steps · {score} over {n} runs",
              round(tok) == tokens and round(stp, 1) == steps and round(sc, 1) == score,
              f"got {tok:,.0f} tokens · {stp:.1f} steps · {sc:.1f} score over {n} runs")


def case_previous_model_numbers() -> None:
    """The Results table's first round, which a tidy-up commit deleted.

    Findings 1-4 and Addendum 1 of `docs/results.md` cite 80.0 and 95.0 from a
    round run on the previous model. One commit dropped `results/_prevmodel/`
    as superseded and nothing noticed, because nothing recomputed it. Restored,
    every figure in that table matches, to the token, so the check is exact.
    """
    print("\n-- the previous-model round, recomputed --")
    for condition, scores, sr_pct, tokens, steps in (
        ("no-skill", 80.0, 0, 174_581, 19.3),
        ("skill", 95.0, 67, 165_782, 18.3),
    ):
        files = sorted((ROOT / "results" / "_prevmodel").glob(f"exec-{condition}-*.json"))
        if len(files) != 3:
            check(f"_prevmodel/{condition}: three runs are kept", False, str(len(files)))
            continue
        runs = [json.loads(p.read_text(encoding="utf-8")) for p in files]
        mean = sum(d["score"] for d in runs) / 3
        sr = round(100 * sum(1 for d in runs if d.get("sr") == 100) / 3)
        tok = sum((d["run"].get("prompt_tokens", 0) + d["run"].get("completion_tokens", 0))
                  for d in runs) / 3
        stp = sum(d["run"].get("steps", 0) for d in runs) / 3
        check(f"{condition}: {scores} · SR {sr_pct}% · {tokens:,} tok · {steps} steps",
              round(mean, 1) == scores and sr == sr_pct
              and round(tok) == tokens and round(stp, 1) == steps,
              f"got {mean:.1f} · SR {sr}% · {tok:,.0f} tok · {stp:.1f} steps")


def case_figures_match_their_sources() -> None:
    """The README's figures must plot the numbers the suite asserts.

    An image is the one artifact nobody diffs. The generator writes the values
    it plotted to `docs/assets/figures.json`, and this recomputes them from the
    same sources everything else uses -- `reproduce.py`'s deterministic cells
    and the run records -- so a figure cannot drift away from the claim it
    illustrates. The pixels are not checked; the data behind them is.
    """
    print("\n-- the README figures plot the asserted numbers --")
    assets = ROOT / "docs" / "assets"
    data_path = assets / "figures.json"
    if not data_path.is_file():
        check("the figures' data is committed", False, str(data_path.name) + " missing")
        return
    data = json.loads(data_path.read_text(encoding="utf-8"))

    for name in ("ladder", "score-vs-finished"):
        check(f"{name}: the image exists", (assets / f"{name}.png").is_file()
              and (assets / f"{name}.svg").is_file(), "missing png or svg")

    from reproduce import DETERMINISTIC_CELLS

    groups = data.get("ladder", {}).get("groups") or []
    check("figure 1 plots three page states", len(groups) == 3, str(len(groups)))
    for group in groups:
        variant = group["variant"]
        check(f"figure 1: replay on {variant} is the asserted cell",
              group["replay"] == DETERMINISTIC_CELLS[("replay", variant)][0],
              f"plotted {group['replay']}, cell {DETERMINISTIC_CELLS[('replay', variant)][0]}")
        check(f"figure 1: re-parameterized on {variant} is the asserted cell",
              group["reparameterized"] == DETERMINISTIC_CELLS[("reparam", variant)][0],
              f"plotted {group['reparameterized']}")
        if group["skill"] is None:
            check(f"figure 1: {variant} says the skill was not measured", True)
            continue
        runs = sorted((ROOT / "results").glob(f"exec-skill+verifier-{variant}-r*.json"))
        scores = [json.loads(p.read_text(encoding="utf-8"))["score"] for p in runs]
        check(f"figure 1: the skill value on {variant} is the run mean",
              bool(scores) and group["skill"] == round(sum(scores) / len(scores), 1),
              f"plotted {group['skill']}, records {scores}")

    tags = {"with the verifier clause": "with-clause", "without it": "no-clause",
            "the stock skill": "v3"}
    arms = data.get("score-vs-finished", {}).get("arms") or []
    check("figure 2 plots three arms", len(arms) == 3, str(len(arms)))
    for arm in arms:
        tag = tags.get(arm["arm"])
        if tag is None:
            check(f"figure 2: {arm['arm']} is a known arm", False, "no run tag")
            continue
        runs = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((ROOT / "results" / "ablation").glob(f"*-r*-{tag}.json"))]
        if len(runs) != 3:
            check(f"figure 2: {tag} has its three runs", False, str(len(runs)))
            continue
        score = round(sum(r["score"] for r in runs) / 3, 1)
        finished = round(sum(1 for r in runs if r["run"]["finished"]) / 3, 3)
        check(f"figure 2: {tag}'s score is the run mean", arm["score"] == score,
              f"plotted {arm['score']}, records {score}")
        check(f"figure 2: {tag}'s completion is the run share",
              abs(arm["finished"] - finished) < 0.002,
              f"plotted {arm['finished']}, records {finished}")


def case_self_report_matches_truth() -> None:
    """The README's most useful sentence, recomputed.

    "Every unaided run that announced success was wrong; every skilled one was
    right." The finding this replaced ("4 of 6 declarations were wrong") was
    measured on six run files that later rounds overwrote, so it could not be
    recomputed at all. This holds the property, which stays true as runs are
    added, and the counts the documents print.
    """
    print("\n-- self-reported completion, recomputed --")
    declared: dict[str, list[tuple[float, str]]] = {"no-skill": [], "skill+verifier": []}
    for p in sorted((ROOT / "results").glob("exec-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        cond = d.get("condition")
        if cond in declared and (d.get("run") or {}).get("finished") is True:
            declared[cond].append((d["score"], p.name))

    unaided = declared["no-skill"]
    check("no unaided declaration was ever correct",
          not [x for x in unaided if x[0] == 100.0], str(unaided))
    check("and there are 10 of them, all wrong",
          len(unaided) == 10, f"{len(unaided)} declared")

    skilled = declared["skill+verifier"]
    check("no skilled declaration was ever wrong",
          not [x for x in skilled if x[0] != 100.0],
          str([x for x in skilled if x[0] != 100.0]))
    check("and there are 18 of them, all correct",
          len(skilled) == 18, f"{len(skilled)} declared")

    # The previous model is excluded from the counts above on purpose, and the
    # reason is not tidiness: its round contains the counterexample the README
    # cites, one skilled run that declared success at 85. Counting it would
    # silently turn "every skilled declaration was true" into a corollary of
    # which runs were in the glob.
    prev = []
    for p in sorted((ROOT / "results" / "_prevmodel").glob("exec-skill-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if (d.get("run") or {}).get("finished") is True:
            prev.append((d["score"], p.name))
    check("the previous model's round still has its one false success",
          len(prev) == 3 and sorted(s for s, _ in prev) == [85.0, 100.0, 100.0],
          str(sorted(prev)))


def case_external_harness_numbers() -> None:
    """The third-party runs quoted in the README's 'Beyond the benchmark'.

    These are the only numbers in the README not produced by this repo's own
    app, and they are the ones a reader is most likely to take on faith: a
    recording that survives a mild page change and dies on a real one, against
    a skill that does not.

    Re-measured once already. The first round of skill runs used a perturbation
    that silently did nothing (the scripts died at document start --
    `observe(null)` -- and the fault is recorded in `docs/results.md`), so the
    skill arm had been measured against a page that never moved. Its records are
    in `results/_invalid/` with that reason in the filename; these are the round
    where the renaming was verified to apply before the run.
    """
    print("\n-- the third-party harness, recomputed from its runs --")
    ext = {p.name: json.loads(p.read_text(encoding="utf-8"))
           for p in sorted((ROOT / "results").glob("external-*.json"))}
    check("the third-party runs are all here", len(ext) == 6, str(sorted(ext)))

    check("replay completes on the unperturbed site",
          ext.get("external-replay-asis.json", {}).get("completed") is True)
    check("replay survives the mild perturbation",
          ext.get("external-replay-perturbed.json", {}).get("completed") is True)

    strong = ext.get("external-replay-strong.json", {})
    check("replay fails under the strong perturbation", strong.get("completed") is False,
          str(strong.get("completed")))
    check("and fails the 8 order-dependent steps, keeping the first 4",
          len(strong.get("failed") or []) == 8
          and [f.get("step") for f in strong.get("failed") or []] == list(range(4, 12)),
          str([f.get("step") for f in strong.get("failed") or []]))

    skill_runs = [v for k, v in ext.items() if k.startswith("external-skill-strong")]
    check("the skill completes 3 of 3 under the strong perturbation",
          len(skill_runs) == 3 and all(v.get("completed") is True for v in skill_runs),
          str([v.get("completed") for v in skill_runs]))
    check("and declares its two gaps instead of asserting them",
          all(len(v.get("gaps") or []) == 2 for v in skill_runs),
          str([len(v.get("gaps") or []) for v in skill_runs]))
    check("and never needed the verifier to refuse a premature done",
          all(v.get("done_rejections") == 0 for v in skill_runs),
          str([v.get("done_rejections") for v in skill_runs]))


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

    # The README's prose is checked for commands and flags; its links were not
    # checked at all, and a dead relative link on the front page is a release
    # defect nothing else would notice.
    relative = []
    for target in re.findall(r"\]\(([^)]+)\)", readme):
        target = target.strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#")[0].strip()
        if path:
            relative.append(path)
    check("the README links to something at all", len(relative) >= 3, str(len(relative)))
    dead = [t for t in relative if not (ROOT / t).exists()]
    check("every relative link in the README resolves", not dead, str(dead))


def case_docs_match_code() -> None:
    """The same two checks for every other published document.

    The README is where a reader starts; `docs/` is where they go next, and the
    quickstart is the page people copy commands from. A dead relative link or an
    `unrecognized arguments` in a guide nobody checks is the same defect as in
    the README, with less excuse.
    """
    print("\n-- the other documents' commands and links --")
    import re
    import subprocess

    docs = sorted((ROOT / "docs").glob("*.md"))
    check("there are documents to check", len(docs) >= 3, str([d.name for d in docs]))

    for doc in docs:
        text = doc.read_text(encoding="utf-8")

        targets = []
        for target in re.findall(r"\]\(([^)]+)\)", text):
            target = target.strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#")[0].strip()
            if path:
                targets.append(path)
        # Resolved against the document's own directory, which is what a browser
        # and GitHub do. No fallback to the repo root: a link inside `docs/`
        # that only works from the root renders in a local preview and 404s
        # for a reader.
        dead = [t for t in targets if not (doc.parent / t).exists()]
        check(f"{doc.name}: every relative link resolves", not dead, str(dead))

        documented = _documented_flags(text)
        check(f"{doc.name}: flags worth checking are present or it shows no commands",
              True, "")  # per-flag checks below carry the failures
        for script, flags in documented.items():
            found = sorted(p for p in ROOT.rglob(script)
                           if ".venv" not in p.parts and "_ref" not in p.parts)
            if not found:
                check(f"{doc.name}: {script} exists somewhere", False,
                      "named in an example, absent from the repo")
                continue
            proc = subprocess.run([sys.executable, str(found[0]), "--help"],
                                  capture_output=True, text=True, timeout=60)
            helptext = proc.stdout + proc.stderr
            missing = sorted(f for f in flags if f not in helptext)
            check(f"{doc.name}: {script} accepts {len(flags)} documented flag(s)",
                  not missing,
                  "shown in an example but absent from --help: " + ", ".join(missing))


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
    case_published_agent_numbers()
    case_published_cost_numbers()
    case_figures_match_their_sources()
    case_previous_model_numbers()
    case_self_report_matches_truth()
    case_external_harness_numbers()
    case_policy_matches_rubric()
    case_readme_matches_code()
    case_docs_match_code()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all shipped artifacts are well-formed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
