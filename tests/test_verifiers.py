"""Does each shipped verifier actually discriminate?

A completion verifier exists to refuse `done` when the work is wrong. Twenty-one
runs in this repo used a working verifier and every one of them passed it, so the
gate has been proven to *block* -- by breaking four verifiers and watching them
block forever -- and never proven to block for the right reason. Nothing has
checked that the assertions fail on work that is wrong.

That is the failure this test exists to catch, and it is a live risk: a
`text_absent` assertion passes when the string is missing, which is also true of
a page that never had it, and of a page where the check is looking in the wrong
place. `A declared gap` is a different mechanism and does not have this problem,
because it never claims to check anything.

Each verifier is run against a state where the task has provably not been done.
Every one of them must fail. A verifier that passes here is not verifying.

    python tests/test_verifiers.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "bench"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from verifier import Verifier  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, timeout: float = 25.0) -> None:
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
    raise RuntimeError(f"server did not come up: {last}")


# Which page state each shipped skill's verifier should be judged against when
# nothing has been done.
WRONG_STATE = {
    "expensedesk-submit-travel-claim": "default",
    "expense-period-report": "reports",
    "expense-period-report-json": "reports",
    "prepare-expense-report-json": "reports",
    "saucedemo-cheapest-item-checkout": None,   # third-party; needs the network
}


def case_verifiers_discriminate() -> None:
    print("\n-- every shipped verifier rejects an untouched page --")

    found = sorted(ROOT.glob("induced/**/verify.json"))
    check("verifiers are shipped at all", bool(found))

    # One server per variant, started lazily.
    servers: dict[str, tuple[subprocess.Popen, str]] = {}

    def server_for(variant: str) -> str:
        if variant not in servers:
            port = free_port()
            url = f"http://127.0.0.1:{port}"
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "bench" / "site" / "server.py"),
                 "--port", str(port), "--variant", variant],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            wait_for(f"{url}/api/state")
            servers[variant] = (proc, url)
        return servers[variant][1]

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(viewport={"width": 1280, "height": 860}).new_page()

            for vpath in found:
                skill_dir = vpath.parent
                name = skill_dir.name
                label = f"{vpath.parent.parent.name}/{name}"

                if name not in WRONG_STATE:
                    check(f"{label}: has a known wrong state", False,
                          "add it to WRONG_STATE or it is never checked")
                    continue
                variant = WRONG_STATE[name]
                if variant is None:
                    print(f"  [skip] {label}: third-party site, needs the network")
                    continue

                verifier = Verifier.load(vpath)
                problems = verifier.problems()
                if problems:
                    check(f"{label}: parses", False, str(problems[:2]))
                    continue

                # An empty workspace, plus a page where nothing has been done.
                workspace = Path(tempfile.mkdtemp(prefix="vtest-"))
                page.goto(server_for(variant), wait_until="networkidle")
                page.wait_for_timeout(200)

                report = verifier.run(page, workspace)

                # A verifier whose only assertions are declared gaps checks
                # nothing, and passing here is correct but not evidence.
                checks = [r for r in report.results if r["type"] != "unverifiable"]
                if not checks:
                    check(f"{label}: has at least one real check", False,
                          "every assertion is a declared gap")
                    continue

                failing = [r["id"] for r in checks if not r["ok"]]
                holding = [r["id"] for r in checks if r["ok"]]
                check(
                    f"{label}: rejects the untouched page ({len(checks)} checks)",
                    not report.passed,
                    f"all {len(checks)} checks passed on work that was not done: "
                    f"{[r['id'] for r in checks]}",
                )
                if failing:
                    print(f"           rejects because of: {', '.join(failing)}")
                if holding:
                    # Not a failure. A check like "no non-trip receipt attached"
                    # is a legitimate invariant -- true before the task and true
                    # after it -- and holds here for the right reason.
                    #
                    # But it is not evidence the gate discriminates, and a
                    # verifier made entirely of them would be the vacuous case
                    # this test catches above. Reporting which is which means a
                    # reader can tell a check that guards the result from one
                    # that was already true.
                    print(f"           already true here:  {', '.join(holding)}")

            browser.close()
    finally:
        for proc, _ in servers.values():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    case_verifiers_discriminate()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("every shipped verifier discriminates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
