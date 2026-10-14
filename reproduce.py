"""Reproduce this project's headline result, with no model and no credentials.

    python reproduce.py            # ~40s, verifies the deterministic baselines
    python reproduce.py --all      # every variant and both baselines
    python reproduce.py --agents   # also runs the model conditions (needs an endpoint)

The claim being checked
-----------------------
A recorded macro replay scores **100/100 on the page the demonstration was
recorded from**. Replaying the recording is the cheapest possible alternative to
learning anything from it, and on that page nothing beats it. On a page whose
data, labels, section order and test hooks have all changed, the same recording
scores **25/100**.

That comparison is what this file verifies, and it needs no model to do it:
macro replay is deterministic. A skeptic can run this in under a minute and get
the same numbers, which is the point -- the rest of the project's results depend
on trusting a task design, a rubric and a model choice, and this part does not.

Every number below was published before this script existed; the script asserts
them rather than deriving them, so a change in behaviour shows up as a failure
rather than as a new baseline.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "bench", ROOT / "replay"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# --------------------------------------------------------------------------
# The published claim. These are the numbers in docs/results.md and README.md.
# --------------------------------------------------------------------------

DETERMINISTIC_CELLS: dict[tuple[str, str], tuple[float, int]] = {
    # (mode, variant): (score, full_credit)
    ("replay", "default"): (100.0, 1),
    ("replay", "jitter"): (70.0, 0),
    ("replay", "relayout"): (70.0, 0),
    ("replay", "jitter-remap"): (35.0, 0),
    ("replay", "jitter-nostid"): (35.0, 0),
    ("replay", "relayout-nostid"): (25.0, 0),
    ("reparam", "default"): (100.0, 1),
    ("reparam", "jitter"): (100.0, 1),
    ("reparam", "relayout"): (100.0, 1),
    ("reparam", "jitter-remap"): (65.0, 0),
    ("reparam", "jitter-nostid"): (50.0, 0),
    ("reparam", "relayout-nostid"): (25.0, 0),
}

# The cells that carry the argument. The default run checks only these, so the
# whole thing finishes in well under a minute.
DECISIVE_CELLS = [
    ("replay", "default"),
    ("replay", "relayout-nostid"),
    ("reparam", "default"),
    ("reparam", "relayout-nostid"),
]

EPISODE = "expense-submit-default"
EPISODE_DIR = ROOT / "episodes" / EPISODE


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(0.2)
    raise RuntimeError(f"server did not come up: {last}")


def run_cell(job: tuple[str, str]) -> dict:
    """Replay one episode against one variant and score it. Process-pool safe."""
    mode, variant = job
    from evaluator import evaluate_any
    from macro import replay_episode

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "bench" / "site" / "server.py"),
         "--port", str(port), "--variant", variant],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for(f"{base_url}/api/state")
        result = replay_episode(
            episode_dir=EPISODE_DIR, base_url=base_url, variant=variant,
            reparam=(mode == "reparam"),
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    rubric = evaluate_any("expense-submit", variant, result.final_state or {}, None)
    return {
        "mode": mode,
        "variant": variant,
        "score": rubric["score"],
        "sr": rubric["sr"],
        "failed_steps": len(result.failed),
        "resolution": result.resolution_histogram(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="check every variant instead of the four decisive cells")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    if not EPISODE_DIR.is_dir():
        print(f"missing episode: {EPISODE_DIR}", file=sys.stderr)
        print("run `python run_sample.py` first to record one.", file=sys.stderr)
        return 2

    jobs = list(DETERMINISTIC_CELLS) if args.all else DECISIVE_CELLS
    print(f"checking {len(jobs)} cell(s) with {args.jobs} workers; no model, no credentials\n")

    t0 = time.time()
    with futures.ProcessPoolExecutor(max_workers=args.jobs) as ex:
        got = list(ex.map(run_cell, jobs))
    elapsed = time.time() - t0

    print(f"{'mode':<9} {'variant':<18} {'score':>7} {'SR':>4}   expected      result")
    print("-" * 72)
    failures = []
    for r in sorted(got, key=lambda x: (x["mode"], x["variant"])):
        exp_score, exp_sr = DETERMINISTIC_CELLS[(r["mode"], r["variant"])]
        ok = abs(r["score"] - exp_score) < 0.01 and r["sr"] == exp_sr * 100
        if not ok:
            failures.append(r)
        mark = "ok  " if ok else "FAIL"
        print(f"{r['mode']:<9} {r['variant']:<18} {r['score']:>7.2f} {r['sr'] // 100:>4}   "
              f"{exp_score:>6.2f}/SR{exp_sr}   {mark}")

    print()
    default_replay = next(r for r in got if r["mode"] == "replay" and r["variant"] == "default")
    default_reparam = next(r for r in got if r["mode"] == "reparam" and r["variant"] == "default")
    hardest = [r for r in got if r["variant"] == "relayout-nostid"]

    print("The claim:")
    print(f"  replaying the recording on the page it was recorded from: "
          f"{default_replay['score']:.0f}/100")
    if hardest:
        print(f"  the same recording after a UI revision with the hooks removed: "
              f"{hardest[0]['score']:.0f}/100")
        print(f"  -> a recording is worth {default_replay['score'] - hardest[0]['score']:.0f} points "
              f"less the moment the page moves")
    print(f"\nfinished in {elapsed:.1f}s")

    if failures:
        print(f"\n{len(failures)} cell(s) did not reproduce the published numbers:", file=sys.stderr)
        for r in failures:
            exp = DETERMINISTIC_CELLS[(r["mode"], r["variant"])]
            print(f"  {r['mode']}/{r['variant']}: got {r['score']}, published {exp[0]}",
                  file=sys.stderr)
        return 1

    print("all checked cells reproduce the published numbers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
