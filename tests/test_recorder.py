"""Unit tests for the recorder's frame bookkeeping.

`recorder/recorder.py` has real logic in it -- settling, before-frame freshness,
result-frame capture -- and until now it was exercised only end to end, by
recording an episode against a live browser. That is how a real defect got in:
`_before_frame` reuses a recent frame when it is fresh and shoots a new one when
it is not, and `_record` registered only the result frames. A freshly shot
before-frame was written to disk and left out of the manifest, and nothing
noticed until an artifact test compared an episode's counts against its
directory.

The guard added for that has not itself been tested, which is the same gap one
level up. These tests use a stub page so they need no browser and no network.

    python tests/test_recorder.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recorder.recorder import BEFORE_FRAME_FRESHNESS_MS, Recorder  # noqa: E402
from recorder.schema import Action, EpisodeWriter, Target  # noqa: E402

FAILURES: list[str] = []

# A one-pixel PNG, so a "screenshot" is a real file.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


class StubPage:
    """Enough of a Page for the recorder's bookkeeping."""

    def __init__(self) -> None:
        self.url = "about:blank"
        self.shots = 0
        self.clock = 0.0          # ms the recorder thinks have passed

    def screenshot(self, path, full_page=False, **_) -> None:
        Path(path).write_bytes(PNG)
        self.shots += 1

    def evaluate(self, _js):
        return []                 # no raw events, and no mutations to settle on

    def wait_for_timeout(self, _ms) -> None:
        pass

    def is_closed(self) -> bool:
        return False


def make_recorder(tmp: Path, page: StubPage) -> tuple[Recorder, EpisodeWriter]:
    writer = EpisodeWriter(tmp, "unit", {"instruction": "unit test"})
    rec = Recorder(writer)
    rec.page = page
    rec._t0 = 1_000.0
    # Deterministic clock: _shoot stamps frames with the recorder's own clock,
    # so a test can make a frame "stale" by advancing it past the freshness
    # window without sleeping.
    rec._now_ms = lambda: int(page.clock)
    return rec, writer


def _record_one(rec: Recorder, rec_writer: EpisodeWriter, caption: str) -> None:
    rec._record(
        kind="click",
        caption=caption,
        target=Target(tag="button", role="button", name=caption),
    )


def case_fresh_before_frame_is_reused() -> None:
    print("\n-- a fresh before-frame is reused, not re-shot --")
    tmp = Path(tempfile.mkdtemp(prefix="rec-"))
    page = StubPage()
    rec, writer = make_recorder(tmp, page)

    start = rec._shoot("boundary", "start")
    writer.add_image(start)
    rec._last_before_image = start
    base_shots = page.shots

    # Well inside the freshness window, so the boundary frame stands in as
    # before-context for the action.
    page.clock = BEFORE_FRAME_FRESHNESS_MS - 100
    _record_one(rec, writer, "click while fresh")

    check("no new before-frame was shot",
          page.shots == base_shots + 1,       # +1 is the result frame only
          f"expected one new frame (the result), got {page.shots - base_shots}")
    check("no frame was registered twice",
          len({id(i) for i in writer.images}) == len(writer.images),
          f"{len(writer.images)} images, {len({id(i) for i in writer.images})} distinct")


def case_stale_before_frame_is_shot_and_registered() -> None:
    print("\n-- a stale before-frame is shot, and registered --")
    tmp = Path(tempfile.mkdtemp(prefix="rec-"))
    page = StubPage()
    rec, writer = make_recorder(tmp, page)

    start = rec._shoot("boundary", "start")
    writer.add_image(start)
    rec._last_before_image = start

    # Past the freshness window, so a new before-frame is required. This is the
    # path that produced an orphan image on disk, absent from the index.
    page.clock = BEFORE_FRAME_FRESHNESS_MS + 1
    _record_one(rec, writer, "click while stale")

    on_disk = sorted(p.name for p in (writer.dir / "evidence").glob("*.png"))
    indexed = sorted(Path(i.rel_path).name for i in writer.images)

    check("a new before-frame was shot", page.shots == 3,
          f"boundary + before + result = 3, got {page.shots}")
    check("every image on disk is in the index", on_disk == indexed,
          f"on disk {on_disk} vs indexed {indexed}")
    check("the shots column and the directory agree",
          writer.images and len(on_disk) == len(writer.images),
          f"{len(on_disk)} files, {len(writer.images)} records")


def case_action_links_to_its_frames() -> None:
    print("\n-- an action points at the frames that support it --")
    tmp = Path(tempfile.mkdtemp(prefix="rec-"))
    page = StubPage()
    rec, writer = make_recorder(tmp, page)

    start = rec._shoot("boundary", "start")
    writer.add_image(start)
    rec._last_before_image = start

    page.clock = BEFORE_FRAME_FRESHNESS_MS + 1
    action = rec._record(
        kind="click", caption="click something",
        target=Target(tag="button", role="button", name="Submit"),
    )

    by_id = {i.action_id: i for i in writer.images if i.action_id}
    check("the action has an evidence image", action.action_id in by_id,
          f"action {action.action_id} has no image")
    check("the action records both frame times",
          action.frame_time_ms is not None and action.result_frame_time_ms is not None)
    check("the result frame is not before the action frame",
          action.result_frame_time_ms >= action.frame_time_ms,
          f"{action.frame_time_ms} -> {action.result_frame_time_ms}")
    check("target_label follows the paper's '<role> - <name>' form",
          action.target_label == "button - Submit", repr(action.target_label))


def main() -> int:
    case_fresh_before_frame_is_reused()
    case_stale_before_frame_is_shot_and_registered()
    case_action_links_to_its_frames()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("recorder frame bookkeeping holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
