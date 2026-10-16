"""A second demonstration, on another site this project does not own.

`saucedemo` was the first, and it has a weakness as evidence: it is a shopping
flow whose payoff is a confirmation *page*, which is the easiest possible thing
to verify. This one is a different shape on purpose.

The task is an authentication flow on `the-internet.herokuapp.com`, a public
site built for automation practice:

- the success marker is a **persistent flash message**, not a new page: if the
  verifier asserts it rather than a transient one, that is a claim the pipeline
  has to earn on a page whose structure nobody here designed;
- the credentials are the only thing that varies between runs, so they are the
  first real test of whether an induced skill takes a value from the request or
  bakes in the one it saw. The demonstration uses the credentials the site
  prints on its own login page, and the run in `docs/walkthrough-theinternet.md`
  hands it a wrong password on purpose.

    python bench/external/theinternet.py            # record the demonstration
    python run_induct.py --episode theinternet
    python run_skill.py --skill induced/<run>/theinternet--concise ...

Nothing is special-cased for this site, and nothing pins it: if it moves a
control, this breaks, and that is the normal case.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from recorder.recorder import CAPTURE_JS, Recorder  # noqa: E402
from recorder.schema import EpisodeWriter  # noqa: E402

SITE = "https://the-internet.herokuapp.com/login"
USER = "tomsmith"
PASSWORD = "SuperSecretPassword!"  # printed on the site's own login page

TASK = {
    "application": "the-internet.herokuapp.com",
    "instruction": (
        "Log in to the-internet with the username 'tomsmith' and the password "
        "'SuperSecretPassword!', then confirm the secure area is displayed."
    ),
    "task_inputs": {"user": USER, "password": PASSWORD},
    "notes": (
        "A second third-party site, recorded with a scripted demonstration. The "
        "credentials are typed as given rather than read off the page, because "
        "the task supplies them; a skill induced from this is expected to take "
        "them from the request. No reset endpoint and no state API: the episode "
        "starts from whatever the site serves."
    ),
}


def demo(page, rec) -> None:
    """Drive the workflow the way a person would."""

    rec.fill("Type the username", page.locator("#username"), USER)
    rec.fill("Type the password", page.locator("#password"), PASSWORD)
    rec.click("Click Login", page.locator("button[type=submit]"), expect_navigation=True)

    # The marker a verifier can gate on. Asserted as text, because on this site
    # the confirmation is a message on a page rather than a page of its own.
    rec.mark(
        "Confirm the secure area is displayed, which the page shows as "
        "'You logged into a secure area!'",
        kind="verify",
    )


def record(out_root: Path, episode_id: str = "theinternet") -> dict:
    viewport = {"width": 1280, "height": 860}
    video_dir = out_root / episode_id / "_video"
    video_dir.mkdir(parents=True, exist_ok=True)

    writer = EpisodeWriter(out_root, episode_id, TASK,
                           recorder_meta={"target_url": SITE, "input_source": "scripted",
                                          "viewport": viewport})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport=viewport, record_video_dir=str(video_dir),
                                      record_video_size=viewport)
        context.add_init_script(CAPTURE_JS)
        page = context.new_page()

        rec = Recorder(writer)
        rec.page = page
        rec._t0 = time.monotonic()

        page.goto(SITE, wait_until="networkidle")
        # No reset endpoint to call; the site starts whatever state it serves.
        page.evaluate("() => { if (window.__s2s) window.__s2s.enabled = true; }")
        rec._settle()
        start = rec._shoot("boundary", "episode start")
        writer.add_image(start)
        rec._last_before_image = start

        demo(page, rec)
        rec._settle()
        rec.mark("end of demonstration")

        writer.recorder_meta["user_agent"] = page.evaluate("() => navigator.userAgent")
        writer.recorder_meta["captured_frames"] = rec.captured_frames
        writer.keylog = page.evaluate("() => window.__s2s.events")

        video = page.video
        page.close()
        context.close()
        video_path = Path(video.path()) if video else None
        browser.close()

    manifest = writer.finalize(video_src=video_path)
    import shutil

    shutil.rmtree(video_dir, ignore_errors=True)
    return manifest


def main() -> int:
    out = ROOT / "episodes"
    print(f"recording a demonstration against {SITE}")
    manifest = record(out)
    print(f"  actions {manifest['counts']['actions']}  "
          f"frames {manifest['counts']['images']}  "
          f"events {manifest['counts']['keylog_events']}")
    print(f"  -> {out / 'theinternet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
