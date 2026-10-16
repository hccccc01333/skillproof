"""Playwright-driven recorder producing skillproof episodes.

Design notes
------------
The paper separates raw capture (WorkRecorder) from benchmark conversion into
action-level records (Appendix B). We keep that split:

  * capture.js emits raw input events with DOM-level target descriptors;
  * this module groups them into semantic actions and attaches evidence frames.

The only thing that changes between a scripted sample and a real human session
is where the input comes from. Everything downstream -- target resolution,
settling, frame capture, action grouping, episode packaging -- is the same
code, because a human session differs only in that the browser is driven by
the operator instead of by this script.

Not yet implemented, and called out so it is not mistaken for done:
  * human-in-the-loop input capture (needs a browser the operator drives);
  * video-interval evidence, since the paper's video tools operate on a
    finished mp4 and we already produce one.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

from .schema import Action, EpisodeWriter, EvidenceImage, Target

CAPTURE_JS = (Path(__file__).parent / "capture.js").read_text(encoding="utf-8")

# Capture policy, mirroring the paper's Appendix A.2 defaults where they have
# a web meaning. These are implementation defaults, not tuned settings.
BEFORE_FRAME_FRESHNESS_MS = 1500
SETTLE_TIMEOUT_MS = 2500
SETTLE_QUIET_MS = 260
MAX_RESULT_FRAMES_PER_ACTION = 1


class Recorder:
    """Records one demonstration into one episode directory."""

    def __init__(
        self,
        writer: EpisodeWriter,
        *,
        settle_timeout_ms: int = SETTLE_TIMEOUT_MS,
        quiet_ms: int = SETTLE_QUIET_MS,
    ) -> None:
        self.w = writer
        self.settle_timeout_ms = settle_timeout_ms
        self.quiet_ms = quiet_ms
        self.page: Page | None = None
        self._t0 = 0.0
        self._drained_until = 0  # seq of last raw event consumed
        self._last_before_image: EvidenceImage | None = None
        self.captured_frames = 0
        self.downloads: list[Path] = []
        self._video_dir: Path | None = None

    # ---------------------------------------------------------------- time

    def _now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    # ------------------------------------------------------------- capture

    def _drain_events(self) -> list[dict]:
        """Return raw events not yet consumed, advancing the watermark."""
        events = self.page.evaluate("() => window.__s2s ? window.__s2s.events : []")
        fresh = [e for e in events if e["seq"] >= self._drained_until]
        if events:
            self._drained_until = max(e["seq"] for e in events) + 1
        return fresh

    def _mutation_count(self) -> int:
        return self.page.evaluate(
            "() => (window.__s2s && window.__s2s.mutations) ? window.__s2s.mutations.length : 0"
        )

    def _settle(self) -> bool:
        """Wait until the page stops mutating. Returns True if it settled."""
        deadline = time.monotonic() + self.settle_timeout_ms / 1000
        last = self._mutation_count()
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(0.05)
            now_count = self._mutation_count()
            if now_count != last:
                last = now_count
                stable_since = time.monotonic()
            elif (time.monotonic() - stable_since) * 1000 >= self.quiet_ms:
                return True
        return False

    def _shoot(self, trigger: str, caption: str | None = None) -> EvidenceImage:
        name = self.w.next_image_name()
        path = self.w.dir / "evidence" / name
        self.page.screenshot(path=str(path), full_page=False)
        self.captured_frames += 1
        return EvidenceImage(
            index=0,
            filename=name,
            frame_time_ms=self._now_ms(),
            captured_at_ms=int(time.time() * 1000),
            trigger=trigger,
            caption=caption,
            url=self.page.url,
        )

    def _before_frame(self, caption: str) -> EvidenceImage:
        """Reuse a recent frame as before-action context when it is fresh
        enough; otherwise capture one. Mirrors the paper's 1.5 s freshness
        rule, including the consequence that before-context can be absent."""
        last = self._last_before_image
        if last and (self._now_ms() - last.frame_time_ms) <= BEFORE_FRAME_FRESHNESS_MS:
            return last
        return self._shoot("before_action", caption)

    # ---------------------------------------------------------- action API

    def _record(
        self,
        *,
        kind: str,
        caption: str,
        value: str | None = None,
        point: dict | None = None,
        target: Target | None = None,
        url_before: str | None = None,
        raw: list[dict] | None = None,
    ) -> Action:
        settled = self._settle()
        url_after = self.page.url

        before = self._before_frame(caption)
        result_frames = []
        if settled:
            for _ in range(MAX_RESULT_FRAMES_PER_ACTION):
                result_frames.append(self._shoot("result", caption))
        else:
            # Settling timed out: keep the available state but flag it, per the
            # paper's policy. A result frame here does not prove the UI is done.
            result_frames.append(self._shoot("result_unsettled", caption))

        for img in result_frames:
            self.w.add_image(img)
        if result_frames:
            self._last_before_image = result_frames[-1]

        # The before frame must be registered too. `_before_frame` reuses a
        # recent frame when it is fresh and *shoots a new one* when it is not --
        # and `_shoot` writes the file while `add_image` records it in the
        # index. Registering only the result frames leaves a freshly shot before
        # frame on disk and absent from the manifest: an episode whose own index
        # does not describe it.
        #
        # It went unnoticed until an artifact test compared the manifest's
        # counts against the directory. Three episodes reused their before
        # frames and were fine; the one with a settling gap longer than the
        # freshness window had an orphan.
        if all(img is not before for img in self.w.images):
            self.w.add_image(before)

        action = Action(
            sequence_index=0,
            action_id=self.w.new_action_id(),
            kind=kind,
            media_time_ms=before.frame_time_ms,
            caption=caption,
            target_label=target.label if target else None,
            target=target,
            value=value,
            point=point,
            url_before=url_before,
            url_after=url_after,
            frame_time_ms=before.frame_time_ms,
            result_frame_time_ms=result_frames[-1].frame_time_ms if result_frames else None,
            raw_event_seqs=[e["seq"] for e in (raw or [])],
        )
        self.w.add_action(action)

        # Link images back to the action for evidence/image_actions.jsonl.
        for img in [before, *result_frames]:
            if img.action_id is None:
                img.action_id = action.action_id
                img.action_delta_ms = img.frame_time_ms - action.media_time_ms
        return action

    def _target_for(self, locator: Locator) -> Target | None:
        """Resolve the DOM descriptor for a locator's element."""
        try:
            raw = locator.evaluate("el => window.__s2s.describe(el)")
        except Exception:
            return None
        return Target.from_js(raw)

    def click(self, caption: str, locator: Locator, *, expect_navigation: bool = False) -> Action:
        target = self._target_for(locator)
        url_before = self.page.url
        box = locator.bounding_box() or {}
        point = {
            "x": int(box.get("x", 0) + box.get("width", 0) / 2),
            "y": int(box.get("y", 0) + box.get("height", 0) / 2),
        }
        self._drain_events()
        locator.click()
        if expect_navigation:
            self.page.wait_for_load_state("networkidle")
        raw = self._drain_events()
        return self._record(
            kind="click", caption=caption, point=point, target=target,
            url_before=url_before, raw=raw,
        )

    def download(self, caption: str, locator: Locator, dest_dir: Path) -> Action:
        """Click something that triggers a file download and keep the file.

        A download is a real action with a real artifact, so it is recorded as
        one. The saved file becomes part of the episode: what the demonstration
        produced is evidence, and for a data task it is the most important
        evidence there is.
        """
        target = self._target_for(locator)
        url_before = self.page.url
        box = locator.bounding_box() or {}
        point = {
            "x": int(box.get("x", 0) + box.get("width", 0) / 2),
            "y": int(box.get("y", 0) + box.get("height", 0) / 2),
        }
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        self._drain_events()
        with self.page.expect_download() as dl_info:
            locator.click()
        download = dl_info.value
        saved = dest_dir / download.suggested_filename
        download.save_as(str(saved))
        self.downloads.append(saved)
        raw = self._drain_events()
        return self._record(
            kind="download", caption=caption, point=point, target=target,
            value=download.suggested_filename, url_before=url_before, raw=raw,
        )

    def fill(self, caption: str, locator: Locator, text: str) -> Action:
        target = self._target_for(locator)
        url_before = self.page.url
        self._drain_events()
        locator.fill(text)
        raw = self._drain_events()
        # A password typed by a script is still a password. The DOM capture
        # redacts by the field's type, and the target carries that same
        # attribute, so the scripted path can use the same signal instead of a
        # second round trip. What a skill might have learned from the literal is
        # not worth a credential in a file that ships with the episode.
        secret = bool(target and target.attrs.get("type", "").lower() == "password")
        return self._record(
            kind="type", caption=caption, value="[redacted]" if secret else text,
            target=target, url_before=url_before, raw=raw,
        )

    def select(self, caption: str, locator: Locator, option: str) -> Action:
        target = self._target_for(locator)
        url_before = self.page.url
        self._drain_events()
        locator.select_option(option)
        raw = self._drain_events()
        return self._record(
            kind="select", caption=caption, value=option, target=target,
            url_before=url_before, raw=raw,
        )

    def mark(self, caption: str, kind: str = "observe") -> Action:
        """Record a pure observation (for boundary frames and verification)."""
        raw = self._drain_events()
        return self._record(kind=kind, caption=caption, url_before=self.page.url, raw=raw)


# --------------------------------------------------------------------------
# Session driver
# --------------------------------------------------------------------------


def record_demo(
    *,
    out_root: Path,
    episode_id: str,
    task: dict,
    demo,
    base_url: str,
    viewport: dict | None = None,
    workspace: Path | None = None,
    headed: bool = False,
    source: str | None = None,
) -> dict:
    """Run `demo(page, recorder)` against `base_url` and write an episode.

    `demo` is a callable taking (page, recorder). It stands in for the human
    demonstrator; see recorder/tasks.py.
    """
    viewport = viewport or {"width": 1280, "height": 860}
    video_dir = Path(out_root) / episode_id / "_video"
    video_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport=viewport,
            record_video_dir=str(video_dir),
            record_video_size=viewport,
            device_scale_factor=1,
        )
        context.add_init_script(CAPTURE_JS)
        page = context.new_page()

        writer = EpisodeWriter(
            out_root,
            episode_id,
            task,
            recorder_meta={
                "started_at": datetime.now(timezone.utc).isoformat(),
                "viewport": viewport,
                "target_url": base_url,
                "input_source": "scripted",
                "source": source,
                "capture_config": {
                    "before_frame_freshness_ms": BEFORE_FRAME_FRESHNESS_MS,
                    "settle_timeout_ms": SETTLE_TIMEOUT_MS,
                    "settle_quiet_ms": SETTLE_QUIET_MS,
                    "max_result_frames_per_action": MAX_RESULT_FRAMES_PER_ACTION,
                    "viewport": viewport,
                },
            },
        )
        rec = Recorder(writer)
        rec.page = page
        rec._t0 = time.monotonic()

        page.goto(base_url, wait_until="networkidle")
        # Every episode begins from a reset server state so that the
        # demonstration, a replayed macro, and a free agent all start equal.
        page.request.post(f"{base_url}/api/reset")
        page.reload(wait_until="networkidle")
        page.evaluate("() => { window.__s2s.enabled = true; }")
        rec._settle()
        start_frame = rec._shoot("boundary", "episode start")
        writer.add_image(start_frame)
        rec._last_before_image = start_frame

        demo(page, rec, workspace)

        rec._settle()
        rec.mark("end of demonstration")

        ua = page.evaluate("() => navigator.userAgent")
        writer.recorder_meta["user_agent"] = ua
        writer.recorder_meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        writer.recorder_meta["captured_frames"] = rec.captured_frames

        writer.add_keylog(rec._drain_events())
        all_events = page.evaluate("() => window.__s2s.events")
        writer.keylog = all_events  # full stream, not just the post-watermark tail

        video = page.video
        page.close()
        context.close()
        video_path = Path(video.path()) if video else None

        browser.close()

    # Whatever the demonstration produced is evidence. Copy the workspace into
    # the episode so the induction agent can see the artifacts, not just the
    # actions that led to them -- for a data task the output *is* the answer.
    if workspace is not None:
        ws = Path(workspace)
        if ws.is_dir():
            dest = writer.dir / "produced"
            dest.mkdir(parents=True, exist_ok=True)
            for f in sorted(ws.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(ws)
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest / rel)
            writer.recorder_meta["workspace_files"] = [
                p.relative_to(ws).as_posix() for p in sorted(ws.rglob("*")) if p.is_file()
            ]

    manifest = writer.finalize(video_src=video_path)
    # The intermediate webm is a byproduct; the schema ships video.mp4 only.
    shutil.rmtree(video_dir, ignore_errors=True)
    return manifest
