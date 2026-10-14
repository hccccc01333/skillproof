"""Replay a recorded episode as a fixed macro and score it.

    .venv/Scripts/python.exe run_macro.py                          # demonstrated page
    .venv/Scripts/python.exe run_macro.py --variant jitter         # changed page

Macro replay is deterministic -- no model is involved -- so a single trial is
the correct sample size, not a shortcut. Any variation across runs would mean
the target application itself is non-deterministic, which would invalidate the
comparison and should be reported as a bug rather than averaged away.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "bench", ROOT / "replay"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evaluator import evaluate, format_report as rubric_report  # noqa: E402
from macro import format_report as replay_report, replay_episode  # noqa: E402
from run_sample import free_port, wait_for  # noqa: E402

import subprocess  # noqa: E402


def start_server(port: int, variant: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "bench" / "site" / "server.py"),
         "--port", str(port), "--variant", variant],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    wait_for(f"http://127.0.0.1:{port}/api/state")
    return proc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", default="expense-submit-default")
    ap.add_argument("--variant", default="default",
                    choices=["default", "jitter", "jitter-nostid", "jitter-remap", "relayout", "relayout-nostid"])
    ap.add_argument("--episodes-dir", default=str(ROOT / "episodes"))
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--reparam", action="store_true",
                    help="re-read field values from the live page instead of replaying recorded literals")
    ap.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = ap.parse_args()

    episode_dir = Path(args.episodes_dir) / args.episode
    if not episode_dir.is_dir():
        print(f"episode not found: {episode_dir}", file=sys.stderr)
        return 2

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = start_server(port, args.variant)
    try:
        replay = replay_episode(
            episode_dir=episode_dir, base_url=base_url, variant=args.variant,
            reparam=args.reparam,
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    rubric = evaluate(args.variant, replay.final_state or {})

    condition = "macro-reparam" if args.reparam else "macro-replay"
    record = {
        "condition": condition,
        "episode_id": args.episode,
        "variant": args.variant,
        "reparam": args.reparam,
        "score": rubric["score"],
        "sr": rubric["sr"],
        "passed": rubric.get("passed", False),
        "rubric_items": [
            {"id": i.id, "weight": i.weight, "requirement": i.requirement,
             "satisfied": i.satisfied, "detail": i.detail}
            for i in rubric.get("items", [])
        ],
        "replay": {
            "steps": len(replay.steps),
            "failed_steps": len(replay.failed),
            "resolution_histogram": replay.resolution_histogram(),
            "reparam_histogram": replay.reparam_histogram(),
            "wall_ms": replay.wall_ms,
            "failures": [
                {"step": s.sequence_index, "caption": s.caption, "error": s.error}
                for s in replay.failed
            ],
            "values_used": [
                {"step": s.sequence_index, "kind": s.kind, "source": s.value_source,
                 "value": s.value_used, "caption": s.caption}
                for s in replay.steps if s.value_source
            ],
        },
        "final_state": replay.final_state,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{condition}-{args.variant}.json"
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
    else:
        print(replay_report(replay, rubric))
        print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
