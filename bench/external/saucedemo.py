"""A demonstration recorded against a site this project does not own.

Every number in this repo was measured on ExpenseDesk, a 400-line app written
for the benchmark. That is the project's largest credibility hole: a reader
cannot tell whether the pipeline works on real pages or only on the page its
author designed for it.

So this records a real multi-step workflow — log in, add an item, check out —
against **saucedemo.com**, a public demo site with documented credentials, and
produces an episode in the same schema as everything else. Nothing here is
special-cased for it; if the pipeline only worked on ExpenseDesk, this would
show it.

    python bench/external/saucedemo.py            # record the demonstration
    python run_induct.py --episode saucedemo --interactive
    python run_skill.py --skill induced/saucedemo --url https://www.saucedemo.com \
        --instruction "..."

Two things differ from the benchmark tasks and are not worked around:

**There is no reset endpoint and no state API.** ExpenseDesk is scored from its
own server state, which is only possible because it is ours. A third-party site
offers neither, so the episode starts from whatever the site serves and any
evaluation has to read the rendered page. That is the normal case outside a
benchmark, and it is worth knowing what it costs.

**The site can change under us.** Nothing here pins it. If saucedemo moves a
control, this breaks, and that is also the normal case.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from recorder.recorder import CAPTURE_JS, Recorder  # noqa: E402
from recorder.schema import EpisodeWriter  # noqa: E402

SITE = "https://www.saucedemo.com"
USER = "standard_user"
PASSWORD = "secret_sauce"  # published on the site's own login page

TASK = {
    "application": "saucedemo.com",
    "instruction": (
        "Log in, add the cheapest item to the cart, and complete checkout with "
        "the name 'Dana Whitfield' and postal code '18503'."
    ),
    "task_inputs": {"user": USER, "name": "Dana Whitfield", "postal_code": "18503"},
    "notes": (
        "A third-party site, not an app written for this benchmark. No reset "
        "endpoint and no state API, so the episode starts from whatever the site "
        "serves and any evaluation must read the rendered page."
    ),
}


def _price(text: str) -> float:
    """'$9.99' -> 9.99, from what the page displays."""
    return float(text.replace("$", "").strip())


def demo(page, rec) -> None:
    """Drive the workflow the way a person would, reading values off the screen."""

    rec.fill("Type the user name", page.locator("#user-name"), USER)
    rec.fill("Type the password", page.locator("#password"), PASSWORD)
    rec.click("Click Login", page.locator("#login-button"), expect_navigation=True)

    # Find the cheapest item by reading the prices the page shows, rather than
    # by knowing which one it is. A skill induced from this can only generalise
    # if the demonstration actually did the comparison.
    cards = page.locator("[data-test='inventory-item']")
    priced = []
    for i in range(cards.count()):
        card = cards.nth(i)
        priced.append((_price(card.locator("[data-test='inventory-item-price']").inner_text()), card))
    priced.sort(key=lambda t: t[0])
    cheapest_price, cheapest = priced[0]
    cheapest_name = cheapest.locator("[data-test='inventory-item-name']").inner_text()
    rec.mark(
        f"Compare the {len(priced)} prices; the cheapest is {cheapest_name} at ${cheapest_price:.2f}",
        kind="observe",
    )

    rec.click(
        f"Add the cheapest item, {cheapest_name}, to the cart",
        cheapest.get_by_role("button", name="Add to cart"),
    )
    rec.click("Open the cart", page.locator("[data-test='shopping-cart-link']"),
              expect_navigation=True)
    rec.click("Click Checkout", page.locator("[data-test='checkout']"),
              expect_navigation=True)

    rec.fill("Type the first name", page.locator("[data-test='firstName']"), "Dana")
    rec.fill("Type the last name", page.locator("[data-test='lastName']"), "Whitfield")
    rec.fill("Type the postal code", page.locator("[data-test='postalCode']"), "18503")
    rec.click("Click Continue", page.locator("[data-test='continue']"), expect_navigation=True)
    rec.click("Click Finish", page.locator("[data-test='finish']"), expect_navigation=True)

    rec.mark("Verify the order confirmation is shown", kind="verify")


def record(out_root: Path, episode_id: str = "saucedemo") -> dict:
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
        rec._t0 = __import__("time").monotonic()

        page.goto(SITE, wait_until="networkidle")
        # No reset endpoint to call. The site starts whatever state it serves.
        page.evaluate("() => { if (window.__s2s) window.__s2s.enabled = true; }")
        rec._settle()
        start = rec._shoot("boundary", "episode start")
        writer.add_image(start)
        rec._last_before_image = start

        demo(page, rec)
        rec._settle()
        rec.mark("end of demonstration")

        ua = page.evaluate("() => navigator.userAgent")
        writer.recorder_meta["user_agent"] = ua
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
    print(f"  -> {out / 'saucedemo'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
