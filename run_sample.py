"""End-to-end Week-1 sample: serve the app, record a demonstration, print the episode.

    .venv/Scripts/python.exe run_sample.py
    .venv/Scripts/python.exe run_sample.py --variant jitter   # changed-page condition
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from recorder.recorder import record_demo  # noqa: E402
from recorder.tasks import DEMOS, TASKS  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(0.25)
    raise RuntimeError(f"server did not come up at {url}: {last}")


def start_server(port: int, variant: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "bench" / "site" / "server.py"),
         "--port", str(port), "--variant", variant],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    wait_for(f"http://127.0.0.1:{port}/api/state")
    return proc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="expense-submit", choices=sorted(TASKS))
    ap.add_argument("--variant", default=None,
                    choices=["default", "jitter", "jitter-nostid", "jitter-remap",
                             "relayout", "relayout-nostid", "reports"])
    ap.add_argument("--out", default=str(ROOT / "episodes"))
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--headed", action="store_true", help="watch the recording run")
    args = ap.parse_args()

    # The report task only exists in the `reports` variant; the claim task only
    # in the others. Defaulting the variant per task keeps the invocation short
    # without letting a mismatched pair through silently.
    if args.variant is None:
        args.variant = "reports" if args.task == "expense-report" else "default"

    port = args.port or free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = start_server(port, args.variant)
    print(f"[serve] ExpenseDesk [{args.variant}] on {base_url}")

    try:
        episode_id = f"{args.task.replace('_', '-')}-{args.variant}"
        # A scratch workspace, outside the episode so packaging cannot recurse.
        workspace = Path(args.out) / "_work" / episode_id
        if workspace.exists():
            import shutil as _sh
            _sh.rmtree(workspace, ignore_errors=True)
        workspace.mkdir(parents=True, exist_ok=True)
        print(f"[record] episode '{episode_id}' ...")
        t0 = time.time()
        manifest = record_demo(
            out_root=Path(args.out),
            episode_id=episode_id,
            task=TASKS[args.task],
            demo=DEMOS[args.task],
            base_url=base_url,
            workspace=workspace,
            headed=args.headed,
            source=f"local:{args.variant}",
        )
        dt = time.time() - t0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    episode_dir = Path(args.out) / episode_id
    print(f"[done] recorded in {dt:.1f}s -> {episode_dir}")
    print(f"       counts: {json.dumps(manifest['counts'])}")
    print(f"       files:")
    for rel in sorted(manifest["files"]):
        p = episode_dir / rel
        size = p.stat().st_size if p.exists() else 0
        print(f"         {rel:<36} {size:>10,} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
