"""Episode schema for skillproof recordings.

The field names follow the episode schema Work2Skill introduces, so that an
induction agent written against that schema reads these episodes unchanged. The web-specific additions are additive and namespaced under keys
the paper does not use, so a paper-compatible reader can ignore them.

Directory layout produced by EpisodeWriter.finalize():

    <episode_dir>/
      task.json                  authoritative instruction + task inputs
      episode.json               manifest: file index, recording metadata, counts
      trace/actions.jsonl        normalized action records, temporal order
      trace/keylog.jsonl         raw input-event log
      evidence/manifest.json     image index
      evidence/image_actions.jsonl  image <-> action associations
      evidence/000001.png ...    evidence frames
      video.mp4                  recording video
      summary.md                 textual operation summary

Deliberate omissions, both taken from the paper:
  * task.json carries no grading/rubric field. The demonstrator and the
    induction agent must not see the evaluator.
  * Evidence images are event-triggered frames. Their capture time does not
    prove the interface finished updating, so each record carries
    action_delta_ms and an explicit is_result_frame flag.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "s2s-episode/1.0"


# --------------------------------------------------------------------------
# Target descriptor: the web analogue of an AT-SPI target element
# --------------------------------------------------------------------------


@dataclass
class Target:
    """A resolved UI target. `role` + `name` are the semantic key; the rest is
    provenance for the induction agent to disambiguate when it needs to."""

    tag: str
    role: str
    name: str | None = None
    testid: str | None = None
    id: str | None = None
    css_path: str | None = None
    text: str | None = None
    value: str | None = None
    bounds: dict[str, float] | None = None
    attrs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_js(cls, d: dict | None) -> "Target | None":
        if not d:
            return None
        return cls(
            tag=d.get("tag", ""),
            role=d.get("role", ""),
            name=d.get("name"),
            testid=d.get("testid"),
            id=d.get("id"),
            css_path=d.get("css_path"),
            text=d.get("text"),
            value=d.get("value"),
            bounds=d.get("bounds"),
            attrs=d.get("attrs") or {},
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {}, [])}

    @property
    def label(self) -> str:
        """`role - name` form used by the paper's target_label field."""
        if self.name:
            return f"{self.role} - {self.name}"
        return self.role


# --------------------------------------------------------------------------
# Action record (trace/actions.jsonl)
# --------------------------------------------------------------------------


@dataclass
class Action:
    sequence_index: int
    action_id: str
    kind: str
    media_time_ms: int
    caption: str
    target_label: str | None = None
    # --- web-specific provenance (ignorable by a paper-compatible reader) ---
    target: Target | None = None
    value: str | None = None
    point: dict[str, int] | None = None
    url_before: str | None = None
    url_after: str | None = None
    frame_time_ms: int | None = None  # evidence frame for this action
    result_frame_time_ms: int | None = None  # frame captured after settling
    duration_ms: int | None = None
    raw_event_seqs: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "sequence_index": self.sequence_index,
            "action_id": self.action_id,
            "kind": self.kind,
            "media_time_ms": self.media_time_ms,
            "caption": self.caption,
        }
        if self.target_label:
            d["target_label"] = self.target_label
        for key in (
            "value",
            "point",
            "url_before",
            "url_after",
            "frame_time_ms",
            "result_frame_time_ms",
            "duration_ms",
        ):
            v = getattr(self, key)
            if v is not None:
                d[key] = v
        if self.target:
            d["target"] = self.target.to_dict()
        if self.raw_event_seqs:
            d["raw_event_seqs"] = self.raw_event_seqs
        return d


# --------------------------------------------------------------------------
# Evidence image index
# --------------------------------------------------------------------------


@dataclass
class EvidenceImage:
    index: int
    filename: str
    frame_time_ms: int
    captured_at_ms: int
    trigger: str  # "before_action" | "result" | "boundary" | "user_mark"
    action_id: str | None = None
    action_delta_ms: int | None = None
    caption: str | None = None
    url: str | None = None

    @property
    def rel_path(self) -> str:
        return f"evidence/{self.filename}"

    def to_index_dict(self) -> dict:
        d: dict[str, Any] = {
            "index": self.index,
            "path": self.rel_path,
            "frame_time_ms": self.frame_time_ms,
            "captured_at_ms": self.captured_at_ms,
            "trigger": self.trigger,
        }
        if self.action_id:
            d["action_id"] = self.action_id
            d["action_delta_ms"] = self.action_delta_ms
        if self.caption:
            d["caption"] = self.caption
        if self.url:
            d["url"] = self.url
        return d

    def to_assoc_dict(self) -> dict:
        return {
            "image": self.rel_path,
            "action_id": self.action_id,
            "frame_time_ms": self.frame_time_ms,
            "action_delta_ms": self.action_delta_ms,
            "trigger": self.trigger,
        }


# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------


class EpisodeWriter:
    """Accumulates a recording and writes the episode on finalize()."""

    def __init__(
        self,
        root: Path,
        episode_id: str,
        task: dict,
        recorder_meta: dict | None = None,
    ) -> None:
        self.root = Path(root)
        self.episode_id = episode_id
        self.dir = self.root / episode_id
        self.task = task
        self.recorder_meta = recorder_meta or {}

        self.actions: list[Action] = []
        self.images: list[EvidenceImage] = []
        self.keylog: list[dict] = []
        self._next_action = 0
        self._image_counter = 0

        (self.dir / "trace").mkdir(parents=True, exist_ok=True)
        (self.dir / "evidence").mkdir(parents=True, exist_ok=True)

    # ---- ids ------------------------------------------------------------

    def new_action_id(self) -> str:
        aid = f"act_{self.episode_id}_{self._next_action:04d}"
        self._next_action += 1
        return aid

    # ---- collection -----------------------------------------------------

    def add_action(self, action: Action) -> Action:
        action.sequence_index = len(self.actions)
        self.actions.append(action)
        return action

    def next_image_name(self) -> str:
        self._image_counter += 1
        return f"{self._image_counter:06d}.png"

    def add_image(self, img: EvidenceImage) -> EvidenceImage:
        img.index = len(self.images)
        self.images.append(img)
        return img

    def add_keylog(self, events: list[dict]) -> None:
        self.keylog.extend(events)

    # ---- output ---------------------------------------------------------

    def finalize(self, video_src: Path | None = None) -> dict:
        """Write every file and return the episode manifest."""
        self._write_task()
        self._write_trace()
        self._write_evidence_index()
        self._write_summary()
        video_rel = self._place_video(video_src)
        manifest = self._write_manifest(video_rel)
        return manifest

    def _write_task(self) -> None:
        # Grading fields are excluded by construction; assert it so a caller
        # cannot leak the rubric into the induction agent's input.
        leaked = [k for k in self.task if k.lower() in {"grading", "rubric", "grader", "answer"}]
        if leaked:
            raise ValueError(f"task.json must not carry grading fields: {leaked}")
        payload = dict(self.task)
        payload.setdefault("task_id", self.episode_id)
        _write_json(self.dir / "task.json", payload)

    def _write_trace(self) -> None:
        _write_jsonl(self.dir / "trace" / "actions.jsonl", [a.to_dict() for a in self.actions])
        _write_jsonl(self.dir / "trace" / "keylog.jsonl", self.keylog)

    def _write_evidence_index(self) -> None:
        _write_json(
            self.dir / "evidence" / "manifest.json",
            {
                "episode_id": self.episode_id,
                "count": len(self.images),
                "images": [i.to_index_dict() for i in self.images],
            },
        )
        _write_jsonl(
            self.dir / "evidence" / "image_actions.jsonl",
            [i.to_assoc_dict() for i in self.images],
        )

    def _write_summary(self) -> None:
        lines = [
            f"# Demonstration summary: {self.episode_id}",
            "",
            f"**Task instruction.** {self.task.get('instruction', '(none)')}",
            "",
            f"**Recorded actions.** {len(self.actions)}",
            f"**Evidence images.** {len(self.images)}",
            f"**Raw input events.** {len(self.keylog)}",
            "",
            "## Action sequence",
            "",
        ]
        for a in self.actions:
            detail = f" `{a.value}`" if a.value else ""
            lines.append(
                f"{a.sequence_index + 1}. [{_fmt_ms(a.media_time_ms)}] "
                f"{a.caption}{detail}"
            )
        lines.append("")
        lines.append("_Summary is derived evidence, not ground truth; reconcile it "
                     "against the action trace and frames._")
        (self.dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _place_video(self, video_src: Path | None) -> str | None:
        if not video_src or not Path(video_src).exists():
            return None
        dest = self.dir / "video.mp4"
        if Path(video_src).suffix.lower() == ".mp4":
            shutil.copy2(video_src, dest)
        else:
            dest = _transcode_to_mp4(Path(video_src), dest)
        return dest.name if dest else None

    def _write_manifest(self, video_rel: str | None) -> dict:
        files = ["task.json", "episode.json", "trace/actions.jsonl"]
        if self.keylog:
            files.append("trace/keylog.jsonl")
        if video_rel:
            files.append(video_rel)
        files += ["summary.md", "evidence/manifest.json", "evidence/image_actions.jsonl"]

        durations = [a.media_time_ms for a in self.actions]
        duration_ms = max(durations) if durations else 0
        if self.images:
            duration_ms = max(duration_ms, max(i.frame_time_ms for i in self.images))

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "episode_id": self.episode_id,
            "task_id": self.task.get("task_id", self.episode_id),
            "application": self.task.get("application"),
            "recording": {
                "duration_ms": duration_ms,
                "started_at": self.recorder_meta.get("started_at"),
                "finished_at": self.recorder_meta.get("finished_at"),
                "viewport": self.recorder_meta.get("viewport"),
                "user_agent": self.recorder_meta.get("user_agent"),
                "target_url": self.recorder_meta.get("target_url"),
                "capture_config": self.recorder_meta.get("capture_config", {}),
                "input_source": self.recorder_meta.get("input_source", "scripted"),
            },
            "counts": {
                "actions": len(self.actions),
                "keylog_events": len(self.keylog),
                "images": len(self.images),
                "keyframes": self.recorder_meta.get("captured_frames", len(self.images)),
            },
            "files": files,
            "evidence_roots": {"input": ".", "output": "output/"},
            # Provenance of the original export. Per Appendix B.1 this is NOT
            # an additional input root for the induction agent.
            "source": self.recorder_meta.get("source"),
        }
        _write_json(self.dir / "episode.json", manifest)
        return manifest


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _fmt_ms(ms: int) -> str:
    s, _ = divmod(int(ms), 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _transcode_to_mp4(src: Path, dest: Path) -> Path | None:
    """Playwright records webm; the paper's schema specifies video.mp4."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(dest),
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"[warn] ffmpeg transcode failed: {proc.stderr.decode(errors='replace')[:400]}")
        return None
    return dest
