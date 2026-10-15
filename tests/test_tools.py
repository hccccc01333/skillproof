"""Contract tests for the induction tool surface.

Run offline, before spending model time:

    .venv/Scripts/python.exe tests/test_tools.py

Every case here corresponds to a way the harness has actually failed or could
silently produce a meaningless result. The read-back cases exist because the
first two induction runs burned their entire iteration budget against a
finalizer that could never pass: write_file keyed path identity one way and
read_file another, so "read the skill back after writing it" was unsatisfiable.
"""

from __future__ import annotations

import json
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from induction.tools import EvidenceTools, ToolError  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def make_episode(root: Path) -> Path:
    """A minimal but structurally real episode."""
    ep = root / "episodes" / "ep-test"
    (ep / "trace").mkdir(parents=True)
    (ep / "evidence").mkdir(parents=True)
    (ep / "task.json").write_text(
        json.dumps({"task_id": "ep-test", "instruction": "Do the thing."}), encoding="utf-8"
    )
    (ep / "trace" / "actions.jsonl").write_text(
        json.dumps({"sequence_index": 0, "action_id": "act_0", "kind": "click",
                    "media_time_ms": 0, "caption": "Click"}) + "\n",
        encoding="utf-8",
    )
    (ep / "evidence" / "000001.png").write_bytes(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                      "0000000a49444154789c6300010000050001"
                      "0d0a2db40000000049454e44ae426082")
    )
    return ep


GOOD_VERIFIER = """{
  "assertions": [
    {"id": "A1", "type": "text_present", "value": "Pending approval",
     "description": "the claim reached the approval queue"},
    {"id": "A2", "type": "unverifiable",
     "description": "cannot bind the status to a specific claim row"}
  ]
}
"""

GOOD_SKILL = """---
name: do-the-thing
description: Perform the thing when the user asks for it.
---

# Do the thing

1. Open the claim.
2. Attach the receipts.
3. Submit.
"""


def write_skill(t: EvidenceTools, name: str = "do-the-thing", *, verifier: str | None = GOOD_VERIFIER,
                body: str | None = None) -> None:
    """Write a skill, and by default the verifier that must accompany it."""
    t.write_file(f"{name}/SKILL.md", body if body is not None else GOOD_SKILL.replace("do-the-thing", name))
    if verifier is not None:
        t.write_file(f"{name}/verify.json", verifier)


def case_write_read_finalize(ep: Path, out: Path) -> None:
    print("\n-- write, read back, finalize --")
    t = EvidenceTools(ep, out)
    t.read_file("task.json")
    write_skill(t)

    r = t.finalize_extraction()
    check("finalize fails before read-back", not r["ok"],
          "should require the skill to be read back first")

    # The regression: the agent may address a generated file either way.
    for spelling in ("output/do-the-thing/SKILL.md", "do-the-thing/SKILL.md"):
        t = EvidenceTools(ep, out)
        t.read_file("task.json")
        write_skill(t)
        t.read_file(spelling)
        t.read_file("output/do-the-thing/verify.json")
        r = t.finalize_extraction()
        check(f"finalize passes when read back as {spelling!r}", r["ok"],
              str(r.get("problems")))


def case_bad_frontmatter(ep: Path, out: Path) -> None:
    print("\n-- structural validation --")
    cases = {
        "missing frontmatter": "Just prose, no frontmatter at all.",
        "name/folder mismatch": "---\nname: other-name\ndescription: d\n---\n\nbody\n",
        "empty description": "---\nname: do-the-thing\ndescription:\n---\n\nbody\n",
        "non-hyphen-case name": "---\nname: Do_The_Thing\ndescription: d\n---\n\nbody\n",
        "empty body": "---\nname: do-the-thing\ndescription: d\n---\n\n",
    }
    for label, content in cases.items():
        t = EvidenceTools(ep, out)
        t.read_file("task.json")
        t.write_file("do-the-thing/SKILL.md", content)
        t.write_file("do-the-thing/verify.json", GOOD_VERIFIER)
        t.read_file("output/do-the-thing/SKILL.md")
        t.read_file("output/do-the-thing/verify.json")
        r = t.finalize_extraction()
        check(f"rejects {label}", not r["ok"])


def case_orphan_is_warning(ep: Path, out: Path) -> None:
    print("\n-- abandoned drafts --")
    t = EvidenceTools(ep, out)
    t.read_file("task.json")
    t.write_file("draft-a/SKILL.md", GOOD_SKILL.replace("do-the-thing", "draft-a"))
    t.write_file("draft-a/verify.json", GOOD_VERIFIER)
    write_skill(t)
    t.read_file("output/do-the-thing/SKILL.md")
    t.read_file("output/do-the-thing/verify.json")
    r = t.finalize_extraction()
    check("orphan does not block finalize", r["ok"], str(r.get("problems")))
    if r["ok"]:
        check("orphan is reported, not hidden",
              "draft-a/SKILL.md" in r["manifest"]["orphaned_skill_files"])
        check("orphan is also warned about", any("draft-a" in w for w in r["manifest"]["warnings"]))


def case_verifier_contract(ep: Path, out: Path) -> None:
    print("\n-- completion verifier contract --")

    # 1. A skill with no verifier is rejected: without one, an execution agent
    #    has no way to tell a finished task from a finished-looking one.
    t = EvidenceTools(ep, out)
    t.read_file("task.json")
    write_skill(t, verifier=None)
    t.read_file("output/do-the-thing/SKILL.md")
    r = t.finalize_extraction()
    check("rejects a skill with no verifier", not r["ok"], str(r.get("problems")))
    if not r["ok"]:
        check("...and names the missing file",
              any("verify.json" in p for p in r["problems"]))

    # 2. A gap expressed as a checkable assertion can never pass, so the agent
    #    could never finish. This is the malformation the first generated
    #    verifier actually shipped with.
    # Reproduces the malformation the first generated verifier actually shipped
    # with: the gap marker in both fields, dressed as a normal text check.
    bad = '''{
  "assertions": [
    {"id": "A1", "type": "text_present", "value": "Pending approval",
     "description": "the claim reached the approval queue"},
    {"id": "A2", "type": "text_present",
     "value": "UNVERIFIED: status belongs to the intended claim row",
     "description": "UNVERIFIED: cannot bind the status to a claim row"}
  ]
}'''
    t = EvidenceTools(ep, out)
    t.read_file("task.json")
    write_skill(t, verifier=bad)
    t.read_file("output/do-the-thing/SKILL.md")
    t.read_file("output/do-the-thing/verify.json")
    r = t.finalize_extraction()
    check("rejects a gap written as a check", not r["ok"], str(r.get("problems")))

    # 3. Unknown types are rejected rather than silently ignored.
    t = EvidenceTools(ep, out)
    t.read_file("task.json")
    write_skill(t, verifier='{"assertions":[{"id":"A1","type":"regex_on_state","value":"x","description":"d"}]}')
    t.read_file("output/do-the-thing/SKILL.md")
    t.read_file("output/do-the-thing/verify.json")
    r = t.finalize_extraction()
    check("rejects an unknown assertion type", not r["ok"])


def case_boundaries(ep: Path, out: Path) -> None:
    print("\n-- boundaries --")
    t = EvidenceTools(ep, out)

    for bad in ("../../../etc/passwd", "..\\..\\secret.txt", "output/../../escape.txt"):
        try:
            t.read_file(bad)
            check(f"blocks read of {bad!r}", False, "no error raised")
        except ToolError:
            check(f"blocks read of {bad!r}", True)

    try:
        t.write_file("extraction-manifest.json", "{}")
        check("blocks writing runtime-owned manifest", False, "no error raised")
    except ToolError:
        check("blocks writing runtime-owned manifest", True)

    try:
        t.read_file("evidence/000001.png")
        check("directs images to read_visual_evidence", False, "no error raised")
    except ToolError:
        check("directs images to read_visual_evidence", True)


def _have(tool: str) -> bool:
    from shutil import which

    return which(tool) is not None


def case_video_ordering(ep: Path, out: Path) -> None:
    print("\n-- video ordering --")
    # ffmpeg is a hard requirement for video, and building a sample needs it.
    # Report that plainly rather than dying with a traceback: a missing tool is
    # not a failing contract, and this crashed CI on every push for four runs
    # before anyone read the log.
    if not _have("ffmpeg"):
        print("  [skip] ffmpeg is not on PATH; the video tools are untested here")
        return

    # A real (tiny) video, so the ordering guard and the sampling path are both
    # exercised end to end rather than only the guard.
    video = ep / "video.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc=size=320x240:rate=10:duration=3",
         "-pix_fmt", "yuv420p", str(video)],
        capture_output=True, check=False,
    )

    t = EvidenceTools(ep, out)
    try:
        t.watch_video("video.mp4", max_frames=2)
        check("blocks sampling before metadata", False, "no error raised")
    except ToolError as exc:
        check("blocks sampling before metadata", "get_video_metadata" in str(exc))

    t = EvidenceTools(ep, out)
    t.get_video_metadata("video.mp4")
    try:
        blocks = t.watch_video("video.mp4", interval_ms=1000, max_frames=3)
        images = [b for b in blocks if b.get("type") == "image_url"]
        check("samples frames once metadata was read", len(images) == 3, f"got {len(images)}")
        check("frames carry timestamp labels",
              any("@ " in b.get("text", "") for b in blocks if b.get("type") == "text"))
    except ToolError as exc:
        check("samples frames once metadata was read", False, str(exc))


def case_task_must_be_read(ep: Path, out: Path) -> None:
    print("\n-- task-first requirement --")
    t = EvidenceTools(ep, out)
    write_skill(t)
    t.read_file("output/do-the-thing/SKILL.md")
    t.read_file("output/do-the-thing/verify.json")
    r = t.finalize_extraction()
    check("finalize fails when task.json was never read", not r["ok"], str(r.get("problems")))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="s2s-tools-"))
    try:
        for i, case in enumerate(
            [case_write_read_finalize, case_bad_frontmatter, case_orphan_is_warning,
             case_verifier_contract, case_boundaries, case_video_ordering,
             case_task_must_be_read]
        ):
            ep = make_episode(tmp / f"case{i}")
            out = tmp / f"case{i}" / "out"
            out.mkdir(parents=True, exist_ok=True)
            case(ep, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all tool-surface contracts hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
