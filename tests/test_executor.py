"""The executor must survive a click that navigates.

Found on a third-party page: the executor clicked a form's submit button, the
browser started a full-page POST + redirect, and the very next page view called
`page.evaluate` while the old execution context was being torn down. The run
died with

    Page.evaluate: Execution context was destroyed, most likely because of a
    navigation

Every page this repo owned was a single-page app with no full-page navigations,
so the pipeline never met the case its own click handling creates. This test
builds the case locally, offline, and deterministically: a form that POSTs to a
handler which sleeps before redirecting, so the navigation is still in flight
when the next page view happens. Without the retry in the executor, the first
`_page_view` after the click raises.

    python tests/test_executor.py
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "bench"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


LOGIN_PAGE = """<!doctype html><html><body>
<h1>Sign in</h1>
<form action="/go" method="post">
  <label for="user">Username</label><input id="user" name="user">
  <label for="pass">Password</label><input id="pass" name="pass" type="password">
  <button type="submit">Log in</button>
</form>
</body></html>"""

OK_PAGE = """<!doctype html><html><body>
<div class="flash">You logged into a secure area!</div>
<h1>Secure Area</h1>
<a href="/login">Log out</a>
</body></html>"""

# A real form POST spends time on the wire and in the handler. This one spends
# it deliberately: long enough that the navigation is certainly still in flight
# when the next page view runs, which is what makes the race deterministic
# rather than occasionally lucky.
HANDLER_DELAY_S = 0.6


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output clean
        pass

    def do_GET(self):  # noqa: N802
        body = OK_PAGE if self.path.startswith("/ok") else LOGIN_PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        time.sleep(HANDLER_DELAY_S)
        self.send_response(303)
        self.send_header("Location", "/ok")
        self.send_header("Content-Length", "0")
        self.end_headers()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def case_click_that_navigates() -> None:
    print("\n-- a click that navigates does not kill the run --")
    from executor.agent import _act, _page_view  # the code under test

    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(viewport={"width": 900, "height": 700}).new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")

            elements, _ = _page_view(page)
            names = [e["name"] for e in elements]
            check("the form's controls are enumerated", len(elements) >= 3, str(names))

            submit = next((e["i"] for e in elements
                           if e["name"].strip().lower() == "log in"), None)
            if submit is None:
                check("the submit button is found by its accessible name", False, str(names))
                return
            check("the submit button is found by its accessible name", True)

            # The click itself returns before the navigation finishes; the
            # failure happens on the page view that follows, which is exactly
            # where it happened on the real site.
            acted = _act(page, "click", {"index": submit})
            check("the click is accepted", acted.startswith("clicked"), acted)

            try:
                elements_after, _ = _page_view(page)
            except Exception as exc:  # noqa: BLE001
                check("the next page view survives the navigation", False,
                      f"{type(exc).__name__}: {str(exc)[:90]}")
                return
            check("the next page view survives the navigation", True)

            text = page.inner_text("body")
            check("and it is the page the click led to",
                  "Secure Area" in text, text[:60].replace("\n", " "))
            check("and the controls on it are enumerated",
                  any("log out" in e["name"].strip().lower() for e in elements_after),
                  str([e["name"] for e in elements_after]))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def case_perturbation_actually_perturbs() -> None:
    """A perturbation that does not perturb must not look like a pass.

    Both perturb scripts died the moment they ran: an init script executes
    before the document exists, so `document.documentElement` is null and
    `observe(null)` throws. The scripts never renamed anything, every perturbed
    run silently measured an unperturbed page, and the third-party comparison
    this repo published was a perturbed replay against an unperturbed skill.

    Nothing noticed, because a perturbation that does nothing looks exactly like
    a skill that survives one. This test applies the real script the way the
    executor applies it -- `add_init_script` -- to a local page carrying the id
    shape it renames, and requires the vocabulary to change.
    """
    print("\n-- the perturbation scripts actually rename the page --")
    from playwright.sync_api import sync_playwright

    from executor.agent import _page_view

    real_script = (ROOT / "bench" / "external" / "perturb-theinternet.js").read_text(
        encoding="utf-8")

    # The shape the real page has, served locally so this stays offline.
    login = """<!doctype html><html><body>
    <h2>Login Page</h2>
    <form id="login" action="/authenticate" method="post">
      <label for="username">Username</label><input id="username" name="username">
      <label for="password">Password</label><input id="password" name="password" type="password">
      <button type="submit">Login</button>
    </form></body></html>"""

    class Handler2(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            body = login.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler2)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def vocabulary(init_script: str | None) -> tuple[list[str], str]:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            if init_script:
                context.add_init_script(init_script)
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(250)
            elements, _ = _page_view(page)
            shape = page.evaluate(
                "() => [...document.querySelectorAll('input')].map(e => e.id)"
                ".concat([...document.querySelectorAll('label')].map(l => l.getAttribute('for')))"
                ".join(',')")
            names = [f"{e['role']}:{e['name']}" for e in elements]
            page.close()
            context.close()
            browser.close()
            return names, shape

    try:
        before, shape_before = vocabulary(None)
        check("the fixture renders the controls it should",
              "username" in shape_before and any("Username" in n for n in before),
              f"{before} / {shape_before}")

        mild, shape_mild = vocabulary(real_script)
        check("mild renames the controls", any("Account name" in n for n in mild), str(mild))
        check("mild leaves the ids alone",
              "username" in shape_mild and "xusername" not in shape_mild, shape_mild)

        strong, shape_strong = vocabulary("window.__S2S_PERTURB_STRONG = true;\n" + real_script)
        check("strong renames the controls too",
              any("Account name" in n for n in strong), str(strong))
        check("strong regenerates the ids", "xusername" in shape_strong, shape_strong)
        # Twice, because the shape lists the input's id and the label's `for`:
        # the association has to follow the regenerated id, not point at the old one.
        check("and the labels still point at their field",
              shape_strong.count("xusername") == 2, shape_strong)

        twice, shape_twice = vocabulary(
            "window.__S2S_PERTURB_STRONG = true;\n" + real_script + "\n" + real_script)
        check("applying it twice is idempotent", "xx" not in shape_twice, shape_twice)
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    case_click_that_navigates()
    case_perturbation_actually_perturbs()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("the executor survives a navigation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
