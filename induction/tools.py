"""The evidence-exploration tool surface (paper Appendix C).

The induction agent's only window onto a demonstration is through these
tools, and the boundary is enforced here in code, not requested in a prompt:

  * the input root is the episode directory, exposed as ``.``;
  * the output root is a separate directory, exposed as ``output/``;
  * writes cannot escape the output root, and cannot touch runtime-owned
    manifests or logs;
  * ``finalize_extraction`` refuses to complete unless the agent actually did
    the things the method requires -- read the authoritative ``task.json``,
    wrote each skill, read it back after the last write, and inspected video
    metadata before sampling that video.

That last point is where this file diverges from a naive tool wrapper. A
prompt that says "read the task first" is a request. A finalizer that fails
until it happens is a guarantee. The paper draws the same line: "Structural
validation and recorded call ordering are enforced by code; the authoring
policy's requirements for evidence grounding, workflow completeness, and
appropriate generalization remain instructions to the model."

What is NOT enforced, deliberately: whether the skill is any good. The
finalizer checks output structure and required tool use. It cannot check
correctness, and pretending otherwise would be the single easiest way to make
these results meaningless.
"""

from __future__ import annotations

import base64
import fnmatch
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Files the runtime owns. The agent must never create or edit these.
RUNTIME_OWNED = {
    "extraction-manifest.json",
    "run-events.jsonl",
    "run-metadata.json",
    "run-summary.json",
}

# Assertion types a generated completion verifier may use. Must stay in step
# with verifier/checks.py, which is what evaluates them.
VERIFIER_KINDS = {
    "text_present",
    "text_absent",
    "text_count_at_least",
    "element_present",
    # A declared blind spot, not a check. It never blocks completion, and it
    # must not carry a value -- see verifier/checks.py for why.
    "unverifiable",
    # File predicates, for tasks whose deliverable is an artifact rather than a
    # screen state. Without these a file-deliverable task can only be verified
    # by asserting page text that will never be there, which is a verifier that
    # cannot pass -- the fourth such failure mode found in this project.
    "file_exists",
    "json_field_equals",
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv"}

# Evidence is downscaled before it reaches the model. The paper's tools take an
# `image_max_size` for exactly this; the first implementation here accepted the
# parameter and ignored it, and induction then could not finish on a provider
# that dropped the image-heavy requests.
#
# Vision cost scales with pixel area, not file size: a 1280x860 frame is about
# 1,400 vision tokens and the same frame at 768 wide is about 505, so a batch of
# twenty goes from ~28k tokens to ~10k. That is the difference between a request
# that completes and one that times out.
#
# PNG is kept rather than JPEG. Counter-intuitively it is *smaller* for these
# screenshots -- 15 KB against 58 KB, because flat UI panels compress well --
# and it is lossless, which matters when the whole point of the evidence is
# reading small text off a form.
DEFAULT_IMAGE_MAX_SIZE = 768

MAX_READ_CHARS = 20_000
MAX_IMAGES_PER_CALL = 20
MAX_FRAMES_PER_CALL = 20


class ToolError(Exception):
    """Raised for a recoverable tool misuse. The message goes back to the model."""


class EvidenceTools:
    """Tools bound to one episode (input) and one output directory."""

    def __init__(self, episode_dir: Path, output_dir: Path, ask=None) -> None:
        self.input_root = Path(episode_dir).resolve()
        self.output_root = Path(output_dir).resolve()
        # A callable (question) -> answer, or None when no person is attached.
        # The tool exists either way, so the agent learns the affordance and
        # has to cope with its absence, which is what a shipped plugin needs.
        self.ask = ask
        self.questions: list[dict] = []
        self.output_root.mkdir(parents=True, exist_ok=True)

        # Recorded call ordering, used by finalize_extraction.
        self.read_task_json = False
        self.written: set[str] = set()
        self.read_after_last_write: set[str] = set()
        self.video_metadata_seen: set[str] = set()
        self.video_sampled: set[str] = set()
        self.events: list[dict] = []
        self.temp_frames = self.output_root / ".frames"
        self._last_write: dict[str, int] = {}

    # ---------------------------------------------------------------- paths

    def _resolve(self, path: str, *, for_write: bool) -> Path:
        """Resolve within the appropriate root, refusing traversal.

        Reads may address a generated file either as `output/x` or as bare `x`.
        Both spellings have to work, because a model that has just written
        `do-the-thing/SKILL.md` will naturally read back that same string, and
        a harness that only accepts the prefixed form turns a reasonable action
        into an error the agent cannot diagnose.
        """
        raw = (path or ".").replace("\\", "/").lstrip("/")

        if raw == "output" or raw.startswith("output/"):
            root, rel = self.output_root, raw[len("output/") :].lstrip("/")
        elif for_write:
            root, rel = self.output_root, raw
        else:
            # Reads: input root wins if the file is actually there, otherwise
            # the path is taken to refer to a generated file.
            candidate = (self.input_root / raw).resolve()
            if str(candidate).startswith(str(self.input_root)) and candidate.exists():
                return candidate
            root, rel = self.output_root, raw

        target = (root / rel).resolve()
        if target != root and not str(target).startswith(str(root) + "\\") and not str(target).startswith(str(root) + "/"):
            raise ToolError(f"path escapes the exposed roots: {path!r}")
        return target

    def _check_not_runtime_owned(self, path: Path) -> None:
        if path.name in RUNTIME_OWNED:
            raise ToolError(
                f"{path.name} is owned by the runtime and must not be created or edited"
            )

    def _output_key(self, path: Path) -> str | None:
        """Canonical key for an output file, or None if it is not under the root.

        Every tool that records "the agent wrote/read X" must use this key.
        Recording the raw argument instead is what broke the first two runs:
        write_file keyed on `submit-claim/SKILL.md` while read_file keyed on the
        literal string the model passed, `output/submit-claim/SKILL.md`, so the
        read-back check could never be satisfied no matter what the agent did.
        """
        try:
            return str(path.resolve().relative_to(self.output_root)).replace("\\", "/")
        except ValueError:
            return None

    # ------------------------------------------------------------ recording

    def _log(self, tool: str, args: dict, result: Any) -> None:
        """Record the call *and its outcome*.

        `ok` here means the tool reported success, not merely that it failed to
        raise. Conflating the two cost a full debugging cycle: the first two
        induction runs logged every finalize_extraction as ok=True while the
        agent was in fact failing to finalize 28 times in a row.
        """
        if isinstance(result, ToolError):
            ok, detail = False, str(result)
        elif isinstance(result, dict) and "ok" in result:
            ok, detail = bool(result["ok"]), result.get("problems") or result.get("warnings")
        else:
            ok, detail = True, None
        entry: dict[str, Any] = {"tool": tool, "args": args, "ok": ok}
        if detail:
            entry["detail"] = detail
        self.events.append(entry)

    # ---------------------------------------------------------------- tools

    def list_directory(self, dir_path: str = ".", *, max_entries: int = 400) -> str:
        target = self._resolve(dir_path, for_write=False)
        if not target.is_dir():
            raise ToolError(f"not a directory: {dir_path}")
        lines = []
        for p in sorted(target.rglob("*")):
            rel = p.relative_to(target)
            if any(part in {".frames", "_video"} for part in rel.parts):
                continue
            marker = "/" if p.is_dir() else ""
            size = "" if p.is_dir() else f"  {p.stat().st_size:,} B"
            lines.append(f"{rel}{marker}{size}")
            if len(lines) >= max_entries:
                lines.append(f"... truncated at {max_entries} entries")
                break
        return "\n".join(lines) or "(empty directory)"

    def glob(self, pattern: str, dir_path: str = ".") -> str:
        target = self._resolve(dir_path, for_write=False)
        hits = [
            str(p.relative_to(target)).replace("\\", "/")
            for p in sorted(target.rglob("*"))
            if fnmatch.fnmatch(p.name, pattern)
        ]
        return "\n".join(hits) or f"(no files matching {pattern!r})"

    def read_file(self, file_path: str, line_offset: int = 0, line_limit: int = 0) -> str:
        target = self._resolve(file_path, for_write=False)
        if not target.is_file():
            raise ToolError(f"not a file: {file_path}")
        if target.suffix.lower() in IMAGE_SUFFIXES:
            raise ToolError(
                f"{file_path} is an image; read it with read_visual_evidence instead"
            )
        if target.suffix.lower() in VIDEO_SUFFIXES:
            raise ToolError(
                f"{file_path} is a video; use get_video_metadata, watch_video, "
                f"or extract_video_frames instead"
            )

        text = target.read_text(encoding="utf-8", errors="replace")
        numbered = text.splitlines()
        if line_limit:
            numbered = numbered[line_offset : line_offset + line_limit]
        else:
            numbered = numbered[line_offset:]

        out, used = [], 0
        for i, line in enumerate(numbered, start=line_offset + 1):
            rendered = f"{i}\t{line[:2000]}" + (" [line truncated]" if len(line) > 2000 else "")
            used += len(rendered) + 1
            if used > MAX_READ_CHARS:
                out.append(f"... truncated: response limit {MAX_READ_CHARS:,} characters reached")
                break
            out.append(rendered)

        if target.name == "task.json":
            self.read_task_json = True
        key = self._output_key(target)
        if key is not None and key in self.written:
            self.read_after_last_write.add(key)
        return "\n".join(out) or "(empty file)"

    def read_visual_evidence(
        self, file_paths: list[str], image_max_size: int = DEFAULT_IMAGE_MAX_SIZE
    ) -> list[dict]:
        if not isinstance(file_paths, list) or not file_paths:
            raise ToolError("file_paths must be a non-empty list")
        if len(file_paths) > MAX_IMAGES_PER_CALL:
            raise ToolError(f"at most {MAX_IMAGES_PER_CALL} images per call, got {len(file_paths)}")

        blocks: list[dict] = []
        for path in file_paths:
            target = self._resolve(path, for_write=False)
            if not target.is_file():
                raise ToolError(f"not a file: {path}")
            if target.suffix.lower() not in IMAGE_SUFFIXES:
                raise ToolError(f"not an image: {path}")
            data, mime, size = _encode_image(target, image_max_size)
            # Source-path label so the model can keep observations tied to the
            # artifact they came from, plus the resolution actually sent, so a
            # reader can tell what the model was looking at.
            blocks.append(
                {"type": "text", "text": f"[image: {path} ({size[0]}x{size[1]})]"}
            )
            blocks.append(
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{data}"}}
            )
        return blocks

    def _label(self, path: str) -> str:
        """A stable label for a path the agent named, for bookkeeping.

        Deliberately computed from the requested path rather than from a
        resolved file, because the video-ordering rule is about the path the
        agent names: "call get_video_metadata for that exact path" has to hold
        even when the named file turns out not to exist, otherwise the guard is
        trivially bypassable by naming a path that does not resolve.
        """
        raw = (path or "").replace("\\", "/").lstrip("/")
        for prefix in ("output/",):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
        return raw

    def get_video_metadata(self, file_path: str) -> str:
        target = self._resolve(file_path, for_write=False)
        if not target.is_file():
            raise ToolError(f"not a file: {file_path}")
        rel = self._label(file_path)
        self.video_metadata_seen.add(rel)
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(target)],
            capture_output=True,
        )
        if proc.returncode != 0:
            raise ToolError(f"ffprobe failed: {proc.stderr.decode(errors='replace')[:200]}")
        info = json.loads(proc.stdout.decode())
        fmt = info.get("format", {})
        stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        return json.dumps(
            {
                "path": rel,
                "duration_s": float(fmt.get("duration", 0) or 0),
                "size_bytes": int(fmt.get("size", 0) or 0),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "frame_rate": stream.get("r_frame_rate"),
                "codec": stream.get("codec_name"),
            },
            indent=2,
        )

    def _require_metadata_first(self, rel: str) -> None:
        """The paper's ordering rule, enforced rather than requested."""
        if rel not in self.video_metadata_seen:
            raise ToolError(
                f"call get_video_metadata for {rel!r} before sampling it. "
                f"This ordering is irreversible within a run."
            )

    def watch_video(
        self,
        file_path: str,
        start_ms: int = 0,
        end_ms: int = 0,
        interval_ms: int = 5000,
        max_frames: int = 12,
        frame_width: int = DEFAULT_IMAGE_MAX_SIZE,
    ) -> list[dict]:
        rel = self._label(file_path)
        self._require_metadata_first(rel)
        target = self._resolve(file_path, for_write=False)
        if not target.is_file():
            raise ToolError(f"not a file: {file_path}")

        if interval_ms < 100:
            raise ToolError("interval_ms must be at least 100")
        if max_frames > MAX_FRAMES_PER_CALL:
            raise ToolError(f"at most {MAX_FRAMES_PER_CALL} frames per call")

        duration_ms = int(float(self._probe_duration(target)) * 1000)
        end_ms = end_ms or duration_ms
        stamps = list(range(start_ms, max(end_ms, start_ms + 1), interval_ms))[:max_frames]
        self.video_sampled.add(rel)
        return self._extract(target, rel, stamps, frame_width)

    def extract_video_frames(
        self, file_path: str, timestamps_ms: list[int], frame_width: int = DEFAULT_IMAGE_MAX_SIZE
    ) -> list[dict]:
        rel = self._label(file_path)
        self._require_metadata_first(rel)
        target = self._resolve(file_path, for_write=False)
        if not target.is_file():
            raise ToolError(f"not a file: {file_path}")
        if not isinstance(timestamps_ms, list) or not timestamps_ms:
            raise ToolError("timestamps_ms must be a non-empty list")
        if len(timestamps_ms) > MAX_FRAMES_PER_CALL:
            raise ToolError(f"at most {MAX_FRAMES_PER_CALL} timestamps per call")
        self.video_sampled.add(rel)
        return self._extract(target, rel, [int(t) for t in timestamps_ms], frame_width)

    def _probe_duration(self, target: Path) -> float:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(target)],
            capture_output=True,
        )
        try:
            return float(proc.stdout.decode().strip())
        except ValueError:
            return 0.0

    def _extract(
        self, target: Path, rel: str, stamps: list[int], width: int
    ) -> list[dict]:
        self.temp_frames.mkdir(parents=True, exist_ok=True)
        duration_ms = int(self._probe_duration(target) * 1000)
        blocks: list[dict] = []
        for ts in stamps:
            # Near the end of a video the exact timestamp may not decode; step
            # back and report the adjustment, as the paper's tools do.
            used = min(ts, max(0, duration_ms - 120))
            out = self.temp_frames / f"f_{used:09d}.png"
            if not out.exists():
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{used/1000:.3f}",
                     "-i", str(target), "-frames:v", "1",
                     "-vf", f"scale={width}:-1", str(out)],
                    capture_output=True,
                )
                if proc.returncode != 0 or not out.exists():
                    blocks.append({"type": "text", "text": f"[frame at {used} ms could not be decoded]"})
                    continue
            data = base64.b64encode(out.read_bytes()).decode()
            label = f"[frame: {rel} @ {used} ms" + (
                f" (adjusted from {ts} ms)" if used != ts else ""
            ) + "]"
            blocks.append({"type": "text", "text": label})
            blocks.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
            )
        return blocks

    def ask_human(self, question: str) -> str:
        """Put a question to the demonstrator, if one is attached."""
        question = (question or "").strip()
        if not question:
            raise ToolError("ask_human needs a question")
        if self.ask is None:
            self.questions.append({"question": question, "answer": None})
            return (
                "No person is attached to this run, so the question cannot be answered. "
                "Do not invent a rule to cover it: state an observable conditional check "
                "or declare the gap in the skill, per the authoring policy."
            )
        try:
            answer = str(self.ask(question))
        except Exception as exc:  # noqa: BLE001
            self.questions.append({"question": question, "answer": None, "error": str(exc)})
            raise ToolError(f"the attached person could not be reached: {exc}") from exc
        self.questions.append({"question": question, "answer": answer})
        return answer

    def write_file(self, file_path: str, content: str) -> str:
        target = self._resolve(file_path, for_write=True)
        self._check_not_runtime_owned(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        key = self._output_key(target)
        if key is not None:
            self.written.add(key)
            self.read_after_last_write.discard(key)
            self._last_write[key] = len(content)
        return f"wrote {file_path} ({len(content):,} characters)"

    # ----------------------------------------------------------- finalizer

    SKILL_NAME_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.+)$", re.DOTALL)

    def finalize_extraction(self) -> dict:
        """Validate structure and required tool use, then write the manifest.

        Checks performed (the paper's list):
          * at least one *final* skill exists
          * task.json was read
          * every final skill was read back after its last write
          * skill frontmatter is valid: lowercase hyphen-case name matching
            its folder, plus a non-empty description
          * skill body is non-empty
          * video metadata was inspected before sampling, where sampling occurred

        Deliberately NOT checked: whether the skill is correct.

        A skill counts as *final* when it was read back after its last write.
        SKILL.md files present on disk that were never read back are reported as
        orphans rather than errors, and this is not leniency -- there is no
        delete tool, so an abandoned draft cannot be removed by any means. Making
        orphans a hard failure would leave the agent in an unfixable state, which
        is exactly the trap the first run of this harness fell into: the model
        produced four near-identical skills, could not delete three of them, and
        burned its entire 100-iteration budget against a finalizer that could
        never pass. Orphans are surfaced in the manifest instead.
        """
        problems: list[str] = []
        warnings: list[str] = []

        on_disk = sorted(p for p in self.output_root.rglob("SKILL.md"))
        if not on_disk:
            problems.append("no SKILL.md was written under the output root")

        def rel_of(p: Path) -> str:
            return str(p.relative_to(self.output_root)).replace("\\", "/")

        final_paths = [p for p in on_disk if rel_of(p) in self.read_after_last_write]
        orphans = [p for p in on_disk if rel_of(p) not in self.read_after_last_write]

        if on_disk and not final_paths:
            problems.append(
                "no skill was read back after its last write; a final skill must be "
                "written and then read back before finalizing"
            )
        for p in orphans:
            warnings.append(
                f"{rel_of(p)} is present on disk but was never read back after its "
                f"last write; treating it as an abandoned draft, not a final skill"
            )

        if not self.read_task_json:
            problems.append("task.json was never read; the authoritative instruction must be read first")

        if self.video_sampled:
            for rel in self.video_sampled:
                if rel not in self.video_metadata_seen:
                    problems.append(f"video {rel!r} was sampled without get_video_metadata")

        parsed_skills = []
        for path in final_paths:
            rel = rel_of(path)
            text = path.read_text(encoding="utf-8")
            m = self.SKILL_NAME_RE.match(text)
            if not m:
                problems.append(f"{rel} has no valid YAML frontmatter block")
                continue
            front, body = m.group(1), m.group(2).strip()
            name_m = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
            desc_m = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
            name = (name_m.group(1).strip() if name_m else "")
            desc = (desc_m.group(1).strip() if desc_m else "")

            if not name:
                problems.append(f"{rel} frontmatter has no name")
            elif not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
                problems.append(f"{rel} name {name!r} is not lowercase hyphen-case")
            elif path.parent.name != name:
                problems.append(f"{rel} folder {path.parent.name!r} does not match name {name!r}")
            if not desc:
                problems.append(f"{rel} frontmatter has an empty description")
            if not body:
                problems.append(f"{rel} body is empty")

            # Heuristic hygiene warnings. These are warnings, not failures --
            # they cannot establish semantic correctness.
            if re.search(r"\b\d{2,4}\s*,\s*\d{2,4}\b", body):
                warnings.append(f"{rel}: body contains what looks like screen coordinates")
            if re.search(r"[A-Za-z]:\\\\|/home/|/Users/", body):
                warnings.append(f"{rel}: body contains a local machine path")
            if re.search(r"\bact_\w+\b|\b\d{4,}\s*ms\b", body):
                warnings.append(f"{rel}: body references action ids or raw timestamps")
            parsed_skills.append({"path": rel, "name": name, "bytes": len(text)})

        # Each final skill must ship a machine-checkable completion verifier.
        # Without one, an execution agent has no way to distinguish a finished
        # task from one that merely looks finished, which is how 67% of the
        # completed runs in this project declared success while scoring 70-85.
        verifiers = []
        for skill in parsed_skills:
            vpath = self.output_root / Path(skill["path"]).parent / "verify.json"
            vrel = str(vpath.relative_to(self.output_root)).replace("\\", "/")
            if not vpath.is_file():
                problems.append(f"{vrel} is missing: every skill must ship a completion verifier")
                continue
            if vrel not in self.read_after_last_write:
                problems.append(f"{vrel} was not read back after its last write")
            try:
                data = json.loads(vpath.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                problems.append(f"{vrel} is not valid JSON: {exc}")
                continue
            assertions = data.get("assertions") if isinstance(data, dict) else None
            if not isinstance(assertions, list) or not assertions:
                problems.append(f"{vrel} has no 'assertions' list")
                continue
            seen: set[str] = set()
            for a in assertions:
                if not isinstance(a, dict):
                    problems.append(f"{vrel}: every assertion must be an object")
                    continue
                aid = str(a.get("id") or "")
                kind = str(a.get("type") or "")
                if not aid:
                    problems.append(f"{vrel}: an assertion has no id")
                elif aid in seen:
                    problems.append(f"{vrel}: duplicate assertion id {aid!r}")
                seen.add(aid)
                if kind not in VERIFIER_KINDS:
                    problems.append(
                        f"{vrel}: assertion {aid!r} has unknown type {kind!r}; "
                        f"allowed: {sorted(VERIFIER_KINDS)}"
                    )
                if kind in ("text_present", "text_absent", "text_count_at_least",
                            "element_present", "file_exists", "json_field_equals") and not a.get("value"):
                    problems.append(f"{vrel}: assertion {aid!r} of type {kind} needs a value")
                if kind == "json_field_equals" and ":" not in (a.get("value") or ""):
                    problems.append(f"{vrel}: assertion {aid!r} of type json_field_equals needs "
                                    f"value '<path>:<field>'")
                if kind == "unverifiable" and a.get("value"):
                    problems.append(
                        f"{vrel}: assertion {aid!r} is marked unverifiable and must not carry "
                        f"a value; a gap written as a check can never pass"
                    )
                # Keep in step with verifier/checks.py. A gap marker written as
                # prose inside a normal check is the malformation that makes a
                # verifier impossible to satisfy, and the two validators
                # drifting apart is how it gets through.
                blob = f"{a.get('description') or ''} {a.get('value') or ''}".strip().upper()
                if kind != "unverifiable" and any(
                    m in blob for m in ("UNVERIFIED", "NOT VERIFIABLE", "CANNOT BE VERIFIED")
                ):
                    problems.append(
                        f"{vrel}: assertion {aid!r} describes an unverifiable gap but has "
                        f"type {kind!r}; use type 'unverifiable' with no value"
                    )
                if kind == "text_count_at_least":
                    c = a.get("count")
                    if not isinstance(c, int) or c < 1:
                        problems.append(f"{vrel}: assertion {aid!r} needs a positive integer count")
                if not a.get("description"):
                    problems.append(f"{vrel}: assertion {aid!r} has no description")
            verifiers.append({"path": vrel, "assertions": len(assertions)})

        if problems:
            return {"ok": False, "problems": problems, "warnings": warnings}

        manifest = {
            "episode_id": self.input_root.name,
            "output_root": str(self.output_root),
            "skills": parsed_skills,
            "skills_hashed": {
                s["path"]: _sha256(self.output_root / s["path"]) for s in parsed_skills
            },
            "orphaned_skill_files": [rel_of(p) for p in orphans],
            "verifiers": verifiers,
            "inspected": {
                "task_json_read": True,
                "video_metadata": sorted(self.video_metadata_seen),
                "video_sampled": sorted(self.video_sampled),
            },
            "tool_calls": len(self.events),
            "warnings": warnings,
            "note": (
                "Structural validation only. This manifest confirms the agent "
                "read the task, wrote skills, read them back, and respected video "
                "ordering. It does not assert that any skill is correct."
            ),
        }
        path = self.output_root / "extraction-manifest.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.rmtree(self.temp_frames, ignore_errors=True)
        return {"ok": True, "manifest": manifest, "warnings": warnings}


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _encode_image(path: Path, max_size: int) -> tuple[str, str, tuple[int, int]]:
    """Downscale an image to fit `max_size` and return (base64, mime, (w, h)).

    Never upscales, never crops: a small frame is passed through untouched, and
    a large one keeps its aspect ratio. If Pillow is unavailable the original
    bytes go through unchanged, because a missing optional dependency should
    degrade to the old behaviour rather than fail a run.
    """
    raw = path.read_bytes()
    if max_size and max_size > 0:
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(raw)) as im:
                w, h = im.size
                if max(w, h) > max_size:
                    scale = max_size / max(w, h)
                    new = (max(1, round(w * scale)), max(1, round(h * scale)))
                    buf = BytesIO()
                    # JPEG rather than PNG *once downscaling*. Resampling
                    # introduces noise that defeats PNG's flat-panel
                    # compression -- the same 768-wide frame is 47 KB as PNG
                    # and 26 KB as JPEG -- and lossless buys little after
                    # LANCZOS has already interpolated every pixel. A frame
                    # needing no resize is still passed through untouched, so
                    # the small, lossless case is preserved.
                    im.resize(new, Image.LANCZOS).convert("RGB").save(
                        buf, format="JPEG", quality=88, optimize=True
                    )
                    return base64.b64encode(buf.getvalue()).decode(), "jpeg", new
                return base64.b64encode(raw).decode(), _mime_for(path), (w, h)
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 - a resize failure must not lose evidence
            pass

    try:
        from PIL import Image

        with Image.open(path) as im:
            size = im.size
    except Exception:  # noqa: BLE001
        size = (0, 0)
    return base64.b64encode(raw).decode(), _mime_for(path), size


def _mime_for(path: Path) -> str:
    return path.suffix.lower().lstrip(".").replace("jpg", "jpeg") or "png"
