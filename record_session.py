"""Record a session you drive yourself, rather than a scripted demonstration.

This is the difference between a benchmark harness and something a person can
use. Every other recording path in this project drives the browser from Python:
it knows what it is about to click, which is exactly the knowledge a real
demonstration is supposed to supply. Here the actions come from you.

    python record_session.py --url http://127.0.0.1:8765 --episode my-task

A headed browser opens with the evidence hook installed. Do the task once, at
your own pace. Close the browser window (or press Ctrl-C in the terminal) and
the episode is written.

The capture layer is the same one the benchmark uses, so a hand-recorded
episode and a scripted one are indistinguishable downstream -- the induction
cannot tell which it got, and does not need to.

What is captured per action, as in the paper's schema: the resolved UI target
(role, accessible name, value, bounds), the before and result frames, and the
raw input stream. What is not: a reason. The recording shows what you did; the
induction reconciles it against what you produced and asks about the rest.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from recorder.recorder import CAPTURE_JS, Recorder  # noqa: E402
from recorder.schema import Action, EpisodeWriter, EvidenceImage, Target  # noqa: E402


def _bursts(fresh: list[dict]) -> list[dict]:
    """Group raw events into one entry per user intent.

    The operator path has to infer intent from events, and the naive version --
    one action per drain -- silently loses actions: a person clicking three
    times in a second produces three clicks in one drain, and only the last
    survives. What the grouping has to do instead:

      * ignore pointer_down and focus; they accompany an action, they are not one
      * merge consecutive typing on the same field into a single action, because
        a person thinks of "type the amount" as one step, not one per keystroke
      * keep everything else separate, because two clicks are two intents

    This is a heuristic, and it is recorded as one: the raw stream is kept whole
    in the keylog, so a different grouping can be derived later without
    re-recording. That is the same reason the paper keeps both layers.
    """
    SKIP = {"pointer_down", "focus"}
    out: list[dict] = []
    for e in fresh:
        kind = e.get("kind")
        if kind in SKIP:
            continue
        target = e.get("target") or {}
        key = (kind, target.get("css_path"), target.get("testid"))
        if out and kind == "input" and out[-1]["_key"] == key:
            # Same field, still typing: extend rather than append.
            out[-1]["value"] = e.get("value")
            out[-1]["seqs"].append(e["seq"])
            continue
        merged = dict(e)
        merged["_key"] = key
        merged["seqs"] = [e["seq"]]
        out.append(merged)
    return out


def _drain(page):
    return page.evaluate("() => (window.__s2s && window.__s2s.events) ? window.__s2s.events : []")


def record(
    *,
    url: str,
    out_root: Path,
    episode_id: str,
    instruction: str,
    workspace: Path | None = None,
    settle_ms: int = 400,
    max_idle_s: float = 900.0,
    selftest: bool = False,
) -> dict:
    """Open a browser, watch the operator work, write an episode."""
    viewport = {"width": 1280, "height": 860}
    video_dir = out_root / episode_id / "_video"
    video_dir.mkdir(parents=True, exist_ok=True)

    task = {
        "application": url,
        "instruction": instruction,
        "notes": "Recorded by hand; no scripted demonstration was involved.",
    }

    writer = EpisodeWriter(
        out_root, episode_id, task,
        recorder_meta={
            "started_at": datetime.now(timezone.utc).isoformat(),
            "viewport": viewport,
            "target_url": url,
            "input_source": "human",
            "capture_config": {"settle_ms": settle_ms, "viewport": viewport},
        },
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            viewport=viewport,
            record_video_dir=str(video_dir),
            record_video_size=viewport,
            accept_downloads=True,
            device_scale_factor=1,
        )
        context.add_init_script(CAPTURE_JS)
        page = context.new_page()

        rec = Recorder(writer)
        rec.page = page
        rec._t0 = time.monotonic()

        if workspace is not None:
            workspace = Path(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

            def _on_download(download):
                try:
                    download.save_as(str(workspace / download.suggested_filename))
                    rec.downloads.append(workspace / download.suggested_filename)
                except Exception:  # noqa: BLE001
                    pass

            page.on("download", _on_download)

        page.goto(url, wait_until="networkidle")
        page.evaluate("() => { if (window.__s2s) window.__s2s.enabled = true; }")
        rec._settle()
        start_frame = rec._shoot("boundary", "session start")
        writer.add_image(start_frame)
        rec._last_before_image = start_frame

        print(f"\n  Recording. Do the task in the browser window.")
        print(f"  Close the window when you are finished.\n")

        consumed = 0
        idle_since = time.monotonic()

        if selftest:
            # Exercises the operator path without an operator: the same event
            # drain, action construction and frame capture the loop below does,
            # driven by a few clicks. It exists because the human path is the
            # one part of this file that cannot be tested by running it.
            print("  [selftest] driving a few actions")
            for _ in range(3):
                try:
                    page.mouse.click(640, 300)
                    page.wait_for_timeout(settle_ms)
                except Exception:  # noqa: BLE001
                    break

        while True:
            if page.is_closed():
                break
            try:
                page.wait_for_timeout(250)
            except Exception:  # noqa: BLE001 - window closed mid-wait
                break

            events = _drain(page)
            fresh = [e for e in events if e["seq"] >= consumed]
            if fresh:
                consumed = max(e["seq"] for e in events) + 1
                idle_since = time.monotonic()
                # Let the interface settle, then record one action per intent
                # rather than one per drain.
                page.wait_for_timeout(settle_ms)
                for burst in _bursts(fresh):
                    target = Target.from_js(burst.get("target"))
                    caption = target.label if target else burst.get("kind", "interact")
                    if burst.get("kind") == "input" and burst.get("value"):
                        caption = f'{caption} = "{str(burst["value"])[:60]}"'
                    action = Action(
                        sequence_index=0,
                        action_id=writer.new_action_id(),
                        kind=burst.get("kind", "interact"),
                        media_time_ms=int((time.monotonic() - rec._t0) * 1000),
                        caption=caption,
                        target_label=target.label if target else None,
                        target=target,
                        value=burst.get("value"),
                        point=burst.get("point"),
                        url_before=burst.get("url"),
                        url_after=page.url,
                        raw_event_seqs=burst["seqs"],
                    )
                    writer.add_action(action)
                    if not page.is_closed():
                        frame = rec._shoot("result", caption)
                        writer.add_image(frame)
                        rec._last_before_image = frame

            if time.monotonic() - idle_since > max_idle_s:
                print(f"\n  No activity for {max_idle_s:.0f}s; stopping.")
                break

        try:
            writer.recorder_meta["user_agent"] = page.evaluate("() => navigator.userAgent")
        except Exception:  # noqa: BLE001
            pass
        writer.recorder_meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        writer.recorder_meta["captured_frames"] = rec.captured_frames

        try:
            writer.keylog = _drain(page)
        except Exception:  # noqa: BLE001
            writer.keylog = []

        video = page.video
        try:
            context.close()
        except Exception:  # noqa: BLE001
            pass
        video_path = Path(video.path()) if video else None
        browser.close()

    if workspace is not None and Path(workspace).is_dir():
        import shutil

        dest = writer.dir / "workspace"
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(Path(workspace).rglob("*")):
            if f.is_file():
                rel = f.relative_to(workspace)
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest / rel)
        writer.recorder_meta["workspace_files"] = [
            p.relative_to(workspace).as_posix()
            for p in sorted(Path(workspace).rglob("*")) if p.is_file()
        ]

    manifest = writer.finalize(video_src=video_path)
    import shutil

    shutil.rmtree(video_dir, ignore_errors=True)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="page to open and record against")
    ap.add_argument("--episode", required=True, help="episode id, e.g. my-workflow")
    ap.add_argument("--instruction", default="",
                    help="what you are about to do, in one sentence. This is what a "
                         "later run will be asked to reproduce.")
    ap.add_argument("--out", default=str(ROOT / "episodes"))
    ap.add_argument("--workspace", default=None,
                    help="directory downloads land in and deliverables should be written to")
    ap.add_argument("--max-idle", type=float, default=900.0)
    ap.add_argument("--selftest", action="store_true",
                    help="drive a few clicks instead of waiting for a person, "
                         "to exercise the capture path")
    args = ap.parse_args()

    instruction = args.instruction or input("What are you about to do? ").strip()
    if not instruction:
        print("an instruction is required: it is the goal a later run is given", file=sys.stderr)
        return 2

    manifest = record(
        url=args.url,
        out_root=Path(args.out),
        episode_id=args.episode,
        instruction=instruction,
        workspace=Path(args.workspace) if args.workspace else None,
        max_idle_s=args.max_idle,
        selftest=args.selftest,
    )

    episode_dir = Path(args.out) / args.episode
    print(f"\n  Recorded -> {episode_dir}")
    print(f"  actions {manifest['counts']['actions']}  "
          f"frames {manifest['counts']['images']}  "
          f"events {manifest['counts']['keylog_events']}")
    if manifest.get("recording", {}).get("input_source") == "human":
        print("  source: human")
    print(f"\n  Next: python run_induct.py --episode {args.episode} --interactive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
