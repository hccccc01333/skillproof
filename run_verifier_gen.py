"""Generate a completion verifier for an already-induced skill.

Why this is a separate call rather than part of induction
--------------------------------------------------------
The authoring policy asks the induction agent to emit `verify.json` alongside
`SKILL.md`, and that is the cleaner design: one agent, one conversation, a
skill and its own completion checks written together.

In practice the induction call carries whole evidence frames as base64 and the
provider used here drops those connections often enough that the run cannot
reliably finish, and re-running a 230k-token induction to add a fifteen-line
JSON file is a poor trade. Verifier generation is therefore available as its
own step, with a text-only payload, which is also closer to how it would ship:
a skill can be re-verified without re-inducing it.

The output must still satisfy the same contract, and is validated against the
same rules the induction finalizer applies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import llm  # noqa: E402
from induction.tools import VERIFIER_KINDS  # noqa: E402
from verifier import Assertion, Verifier  # noqa: E402

SYSTEM = """You write completion verifiers for computer-use skills.

Given a task instruction and the skill that performs it, produce a set of
machine-checkable assertions that decide whether the task actually succeeded.

Return JSON only, of exactly this shape:

{
  "assertions": [
    {"id": "A1", "type": "text_present", "value": "...", "description": "..."}
  ]
}

There are TWO surfaces, and using the wrong one produces a verifier that can
never pass:

**The page** is the live browser screen. Assertions about it read the rendered
text and the interactive controls. Field names, JSON punctuation and file
contents are NOT on the page — they are not rendered anywhere.

**The workspace** is a directory of files the task asks the agent to produce.
Assertions about it read those files directly. A file's contents never appear
on the page, so never assert a file's contents with a page predicate.

Assertion types:

PAGE
- text_present          a string appears in the page's visible text
- text_absent           a string does not appear in the page's visible text
- text_count_at_least   a string appears at least `count` times
- element_present       an interactive control with a matching accessible name exists

WORKSPACE
- file_exists           a file with the given path exists. `value` is the path,
                        e.g. "report.json"
- json_field_equals     a JSON file has a top-level field equal to `expected`.
                        `value` is "<path>:<field>", e.g. "report.json:grand_total"

NEITHER
- unverifiable          declares something the task requires that these types cannot
                        check. Carries a `description` and NO `value`. Never fails.

Rules:
1. Decide which surface the deliverable lives on and assert there. If the task
   produces a file, verify the file with the file predicates.
2. Assert only what an agent can observe. Never reference application state,
   logs, databases, or anything a user could not see.
3. Assert completion conditions, not steps. "I clicked submit" is a step; "the
   claim shows Pending approval" is a condition.
4. Never hardcode values from the demonstration. Assertions must hold for the
   task as stated, not for the particular episode the skill came from — a
   verifier that checks for a specific month, id or total fails a correct run on
   different data.
5. Assert persistent state, never transient feedback. A confirmation toast that
   disappears after a few seconds is true only at the instant of the action and
   false forever after; gating on it makes the task unfinishable.
6. If a required condition cannot be expressed in these types, add an
   `unverifiable` assertion naming what cannot be checked. It must have no
   `value`: a gap written as a checkable assertion can never pass.
7. Do not pad. Prefer few, load-bearing assertions over many redundant ones."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-root", required=True,
                    help="directory containing the induced skill (and extraction-manifest.json)")
    ap.add_argument("--task-json", default=None,
                    help="task.json to verify against; defaults to the episode of the same name")
    ap.add_argument("--out", default=None, help="write verify.json here (default: beside the skill)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    skill_root = Path(args.skill_root).resolve()
    manifest_path = skill_root / "extraction-manifest.json"
    if not manifest_path.is_file():
        print(f"no extraction-manifest.json in {skill_root}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("skills"):
        print("manifest lists no skills", file=sys.stderr)
        return 2
    skill_dir = skill_root / Path(manifest["skills"][0]["path"]).parent
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    task_json = Path(args.task_json) if args.task_json else (ROOT / "episodes" / manifest["episode_id"] / "task.json")
    task = json.loads(task_json.read_text(encoding="utf-8"))

    user = (
        f"TASK INSTRUCTION\n{task.get('instruction','')}\n\n"
        f"TASK INPUTS\n{json.dumps(task.get('task_inputs', {}), indent=2)}\n\n"
        f"APPLICATION\n{task.get('application','')}\n\n"
        f"SKILL\n{skill_text}\n"
    )

    client = llm.make_client()
    print(f"[verifier] generating for {manifest['episode_id']} with {llm.model_name()}")

    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    assertions: list[Assertion] = []
    problems: list[str] = []

    # The validator is cheap and the generator is not perfectly compliant, so
    # feed failures back rather than shipping a verifier that cannot pass.
    for attempt in range(1, 4):
        resp = llm.chat(
            client,
            model=llm.model_name(),
            messages=messages,
            temperature=0,
            max_tokens=4000,
            verbose=args.verbose,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            raw = raw[4:] if raw.lower().startswith("json") else raw

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            problems = [f"not valid JSON: {exc}"]
            messages += [
                {"role": "assistant", "content": raw[:1500]},
                {"role": "user", "content": "That was not valid JSON. Return only the JSON object."},
            ]
            print(f"[verifier] attempt {attempt}: {problems[0]}")
            continue

        assertions = [Assertion.from_dict(a) for a in data.get("assertions", [])]
        problems = []
        if not assertions:
            problems.append("no assertions produced")
        seen: set[str] = set()
        for a in assertions:
            problems.extend(a.problems())
            if a.id in seen:
                problems.append(f"duplicate id {a.id!r}")
            seen.add(a.id)

        if not problems:
            break

        print(f"[verifier] attempt {attempt}: {len(problems)} problem(s)")
        for p in problems:
            print("   -", p)
        messages += [
            {"role": "assistant", "content": raw[:2000]},
            {"role": "user", "content":
                "Your JSON was rejected by the validator:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\n\nReturn a corrected JSON object. Remember: a declared gap must use "
                  "type 'unverifiable' with NO value field."},
        ]

    if problems:
        print("generated verifier is malformed after repair attempts:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else (skill_dir / "verify.json")
    out_path.write_text(json.dumps({"assertions": [a.to_dict() for a in assertions]},
                                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[verifier] wrote {out_path} ({len(assertions)} assertions)")
    for a in assertions:
        flag = "UNVERIFIED" if a.description.startswith("UNVERIFIED") else a.kind
        print(f"  {a.id:<4} {flag:<12} {a.description[:76]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
