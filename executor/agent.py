"""The downstream executor: a web agent that actually does the task.

This is the condition the induced skill is supposed to help. It is also the
"original agent" baseline when no skill is supplied, so the two differ *only*
by the appended guidance block -- same model, same tools, same step limit,
same page state. That control is why the comparison means anything.

Access model
------------
The executor sees a screenshot plus a numbered list of interactive elements
resolved from the DOM (role, accessible name, current value), and acts by
index. This is the standard modern web-agent interface, and it is deliberately
comparable to what the macro baseline gets: the macro resolves targets by
`data-testid` and role/name, so giving the executor a DOM-derived element list
keeps the comparison about *skill quality* rather than about who has better
eyes.

A pixel-only executor would be a different experiment. It would likely lose to
the macro for reasons that have nothing to do with induction, which would make
the comparison useless rather than conservative.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

# Enumerate what a web agent can act on. Kept in one place so every condition
# sees exactly the same view of the page.
ENUMERATE_JS = """
() => {
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=tab], [role=checkbox], [role=radio], [role=option], [role=menuitem]';
  const out = [];
  let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue;
    const label = el.labels && el.labels.length ? el.labels[0].textContent.trim() : null;
    const name = (el.getAttribute('aria-label') || label || (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? el.getAttribute('placeholder') : null) || el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 90);
    const tag = el.tagName.toLowerCase();
    let role = el.getAttribute('role') || tag;
    if (tag === 'input') role = (el.type === 'checkbox' || el.type === 'radio') ? el.type : (el.type === 'submit' || el.type === 'button') ? 'button' : 'textbox';
    if (tag === 'select') role = 'combobox';
    if (tag === 'a') role = 'link';
    out.push({ i: i++, el, role, name, value: (el.value === undefined || el.type === 'password') ? null : String(el.value).slice(0, 60), disabled: !!el.disabled });
  }
  window.__s2s_els = out;
  return out.map(({ i, role, name, value, disabled }) => ({ i, role, name, value, disabled }));
}
"""

CLICK_JS = """
(idx) => { const e = window.__s2s_els[idx]; if (!e) return 'no such element'; e.el.scrollIntoView({block:'center'}); e.el.click(); return 'clicked'; }
"""

TYPE_JS = """
([idx, text]) => {
  const e = window.__s2s_els[idx]; if (!e) return 'no such element';
  e.el.scrollIntoView({block:'center'}); e.el.focus();
  if (e.el.tagName === 'SELECT') { return 'use select_option for a dropdown'; }
  const proto = e.el.tagName === 'TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
  const setter = Object.getOwnPropertyDescriptor(proto.prototype, 'value').set;
  setter.call(e.el, text);
  e.el.dispatchEvent(new Event('input', { bubbles: true }));
  e.el.dispatchEvent(new Event('change', { bubbles: true }));
  e.el.blur();
  return 'typed';
}
"""

SELECT_JS = """
([idx, option]) => {
  const e = window.__s2s_els[idx]; if (!e) return 'no such element';
  const el = e.el;
  if (el.tagName !== 'SELECT') return 'not a dropdown';
  const match = [...el.options].find(o => o.value === option || o.textContent.trim() === option || o.textContent.trim().startsWith(option));
  if (!match) return 'no option matching ' + option + '; available: ' + [...el.options].map(o => o.value).filter(Boolean).join(' | ');
  el.value = match.value;
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return 'selected ' + match.value;
}
"""


@dataclass
class ExecStep:
    step: int
    tool: str
    args: dict
    result: str
    url: str


@dataclass
class ExecRun:
    condition: str
    episode_id: str
    variant: str
    model: str
    steps: list[ExecStep] = field(default_factory=list)
    final_state: dict | None = None
    finished: bool = False
    finish_note: str = ""
    wall_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: list[str] = field(default_factory=list)
    # Verifier bookkeeping. `done_rejections` is the number of times the agent
    # tried to declare completion and was told the task was not verifiably
    # finished -- the direct measure of how much false confidence the verifier
    # removed.
    verifier_present: bool = False
    verifier_runs: int = 0
    done_rejections: int = 0
    verifier_at_finish: dict | None = None
    workspace: str | None = None
    downloads: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "episode_id": self.episode_id,
            "variant": self.variant,
            "model": self.model,
            "finished": self.finished,
            "finish_note": self.finish_note,
            "steps": len(self.steps),
            "wall_ms": self.wall_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "errors": self.errors,
            "verifier_present": self.verifier_present,
            "verifier_runs": self.verifier_runs,
            "done_rejections": self.done_rejections,
            "verifier_at_finish": self.verifier_at_finish,
            "workspace": self.workspace,
            "downloads": self.downloads,
            "trajectory": [
                {"step": s.step, "tool": s.tool,
                 "args": {k: (v[:80] + "…" if isinstance(v, str) and len(v) > 80 else v) for k, v in s.args.items()},
                 "result": s.result[:200], "url": s.url}
                for s in self.steps
            ],
        }


BASE_SYSTEM = """You operate a web application in a browser to complete a user's task.

You are given a screenshot of the current page and a numbered list of interactive elements. Act by calling exactly one tool per turn.

- `click(index)` — click element by its number
- `type(index, text)` — replace the contents of a text field
- `select_option(index, option)` — choose an option in a dropdown
- `scroll(direction)` — 'down' or 'up'
- `done(note)` — declare the task finished

Rules:
- Make task state changes through visible application controls. Never edit application state by any other means.
- Do not act on an element that is disabled.
- Read the page after each action before deciding the next one.
- When you call `done`, the result will be verified in the live application. Verify the requested outcome yourself before declaring completion."""


def _tools_schema(with_verifier: bool = False, with_files: bool = False) -> list[dict]:
    tools = [
        {"type": "function", "function": {
            "name": "click", "description": "Click an interactive element by index.",
            "parameters": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}}},
        {"type": "function", "function": {
            "name": "type", "description": "Replace the contents of a text field.",
            "parameters": {"type": "object", "properties": {"index": {"type": "integer"}, "text": {"type": "string"}}, "required": ["index", "text"]}}},
        {"type": "function", "function": {
            "name": "select_option", "description": "Choose an option in a dropdown.",
            "parameters": {"type": "object", "properties": {"index": {"type": "integer"}, "option": {"type": "string"}}, "required": ["index", "option"]}}},
        {"type": "function", "function": {
            "name": "scroll", "description": "Scroll the page.",
            "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["down", "up"]}}, "required": ["direction"]}}},
        {"type": "function", "function": {
            "name": "done", "description": "Declare the task finished. Call only after verifying the requested outcome.",
            "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}},
    ]
    if with_files:
        tools[-1:-1] = [
            {"type": "function", "function": {
                "name": "list_files",
                "description": "List the files in your workspace. Downloads land here.",
                "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {
                "name": "read_file",
                "description": "Read a text file from your workspace, with line numbers.",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {
                "name": "write_file",
                "description": ("Create or replace a file in your workspace. Use this to "
                                "produce any deliverable the task asks for."),
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}}},
        ]
    if with_verifier:
        tools.insert(-1, {"type": "function", "function": {
            "name": "run_verifier",
            "description": ("Run the completion checks that ship with the skill. Returns PASS or the "
                            "list of checks that still fail. Call this before declaring the task finished."),
            "parameters": {"type": "object", "properties": {}, "required": []}}})
    return tools


MAX_FILE_BYTES = 200_000


def _ws_path(workspace: Path, raw: str) -> Path:
    """Resolve inside the workspace, refusing traversal."""
    rel = (raw or "").replace("\\", "/").lstrip("/")
    target = (workspace / rel).resolve()
    if target != workspace.resolve() and not str(target).startswith(str(workspace.resolve()) + os.sep):
        raise ValueError(f"path escapes the workspace: {raw!r}")
    return target


def _file_tool(workspace: Path, name: str, args: dict) -> str:
    if name == "list_files":
        files = sorted(p for p in workspace.rglob("*") if p.is_file())
        if not files:
            return "(workspace is empty)"
        return "\n".join(
            f"{p.relative_to(workspace).as_posix()}  {p.stat().st_size:,} B" for p in files
        )
    if name == "read_file":
        target = _ws_path(workspace, args.get("path", ""))
        if not target.is_file():
            return f"no such file: {args.get('path')}"
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        out, used = [], 0
        for i, line in enumerate(lines, 1):
            rendered = f"{i}	{line[:2000]}"
            used += len(rendered) + 1
            if used > 40_000:
                out.append(f"... truncated ({len(lines)} lines total)")
                break
            out.append(rendered)
        return "\n".join(out) or "(empty file)"
    if name == "write_file":
        target = _ws_path(workspace, args.get("path", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        content = args.get("content") or ""
        target.write_text(content, encoding="utf-8")
        return f"wrote {args.get('path')} ({len(content):,} characters)"
    return f"unknown file tool {name}"


def _page_view(page: Page) -> tuple[list[dict], dict]:
    elements = page.evaluate(ENUMERATE_JS)
    shot = page.screenshot(type="png")
    return elements, {"type": "image_url",
                      "image_url": {"url": "data:image/png;base64," + base64.b64encode(shot).decode()}}


def _render(elements: list[dict]) -> str:
    lines = ["Interactive elements on the current page:"]
    for e in elements:
        bits = [f"[{e['i']}]", e["role"], f'"{e["name"]}"']
        if e["value"]:
            bits.append(f'value="{e["value"]}"')
        if e["disabled"]:
            bits.append("(disabled)")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def execute(
    *,
    base_url: str,
    variant: str,
    instruction: str,
    condition: str,
    guidance_text: str | None = None,
    verifier=None,
    model: str | None = None,
    max_steps: int = 30,
    workspace: Path | None = None,
    reset: bool = True,
    capture_state: bool = True,
    headed: bool = False,
    verbose: bool = False,
) -> ExecRun:
    """Run one execution episode. If guidance_text is set, it is appended in the
    paper's `<task_skills>` wrapper; otherwise this is the no-skill baseline."""
    from induction.prompts import downstream_wrapper

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import llm as _llm

    client = _llm.make_client()
    model = model or _llm.model_name()

    system = BASE_SYSTEM + ("\n\n" + downstream_wrapper(guidance_text) if guidance_text else "")
    if verifier is not None:
        system += (
            "\n\nThis task ships a completion verifier. Call `run_verifier` before `done`; "
            "if it reports failures, fix them and check again. Declaring completion while the "
            "verifier fails will be rejected."
        )
    run = ExecRun(condition=condition, episode_id="", variant=variant, model=model)
    run.verifier_present = verifier is not None

    t0 = time.monotonic()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1280, "height": 860}, accept_downloads=True)
        page = context.new_page()

        if workspace is not None:
            workspace = Path(workspace)
            workspace.mkdir(parents=True, exist_ok=True)
            run.workspace = str(workspace)

            def _on_download(download):
                # A browser saves downloads without being asked; the agent then
                # finds the file in its workspace, exactly as a person would.
                try:
                    download.save_as(str(workspace / download.suggested_filename))
                    run.downloads.append(download.suggested_filename)
                    if verbose:
                        print(f"    [download] {download.suggested_filename}")
                except Exception as exc:  # noqa: BLE001
                    run.errors.append(f"download failed: {type(exc).__name__}: {exc}")

            page.on("download", _on_download)
        page.goto(base_url, wait_until="networkidle")
        if reset:
            # The benchmark's app exposes a reset endpoint so every condition
            # starts from an identical state. An arbitrary page has no such
            # thing, and asking for it would be an error rather than a no-op.
            page.request.post(f"{base_url}/api/reset")
            page.reload(wait_until="networkidle")
        page.wait_for_timeout(250)

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Task: {instruction}\n\nBegin."},
        ]

        for step in range(max_steps):
            elements, image = _page_view(page)
            messages.append({"role": "user", "content": [image, {"type": "text", "text": _render(elements)}]})

            try:
                resp = _llm.chat(
                    client,
                    model=model, messages=messages,
                    tools=_tools_schema(verifier is not None, workspace is not None),
                    tool_choice="auto", temperature=0, max_tokens=8000,
                    # One action per turn. Without this the model sometimes
                    # batches several tool calls into one message, and a
                    # single-action loop leaves the extra `tool_call_id`s
                    # unanswered -- which the API rejects on the *next* request
                    # with "An assistant message with 'tool_calls' must be
                    # followed by tool messages responding to each
                    # 'tool_call_id'". That failure lands mid-episode and looks
                    # like the agent giving up; it silently invalidated three
                    # runs before it was diagnosed.
                    parallel_tool_calls=False,
                    verbose=verbose,
                )
            except Exception as exc:  # noqa: BLE001
                run.errors.append(f"endpoint error: {type(exc).__name__}: {str(exc)[:1500]}")
                break

            if resp.usage:
                run.prompt_tokens += resp.usage.prompt_tokens or 0
                run.completion_tokens += resp.usage.completion_tokens or 0

            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            messages.append({"role": "assistant", "content": msg.content or "",
                             **({"tool_calls": [c.model_dump() for c in calls]} if calls else {})})
            if not calls:
                messages.append({"role": "user", "content": "Call one of the tools."})
                continue

            call = calls[0]
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            # Belt and braces: answer every tool call in the message, so the
            # transcript stays valid even if the endpoint ignores
            # parallel_tool_calls.
            for extra in calls[1:]:
                messages.append({
                    "role": "tool", "tool_call_id": extra.id,
                    "content": "not executed: this agent performs one action per turn.",
                })

            if name == "run_verifier":
                report = verifier.run(page, workspace)
                run.verifier_runs += 1
                run.verifier_at_finish = report.to_dict()
                result = ("VERIFIER PASSED. All completion checks hold."
                          if report.passed else
                          "VERIFIER FAILED:\n" + report.summary()
                          + "\nFix these before declaring completion.")
                run.steps.append(ExecStep(step, name, {}, result, page.url))
                if verbose:
                    print(f"  [{step}] run_verifier -> {'PASS' if report.passed else 'FAIL'}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                continue

            if name == "done":
                # The gate. A verifier that does not block an unverified claim is
                # decoration; the point is that the agent cannot talk past it.
                if verifier is not None:
                    report = verifier.run(page, workspace)
                    run.verifier_runs += 1
                    run.verifier_at_finish = report.to_dict()
                    if not report.passed:
                        run.done_rejections += 1
                        result = ("REJECTED: the completion verifier does not pass, so the task is "
                                  "not finished.\n" + report.summary()
                                  + "\nContinue working, then call run_verifier again.")
                        run.steps.append(ExecStep(step, name, args, result, page.url))
                        if verbose:
                            print(f"  [{step}] done REJECTED by verifier")
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                        continue
                run.finished = True
                run.finish_note = args.get("note", "")
                run.steps.append(ExecStep(step, name, args, "declared done", page.url))
                if verbose:
                    print(f"  [{step}] done: {run.finish_note[:90]}")
                break

            if workspace is not None and name in ("list_files", "read_file", "write_file"):
                try:
                    result = _file_tool(workspace, name, args)
                except Exception as exc:  # noqa: BLE001
                    result = f"error: {type(exc).__name__}: {exc}"
            else:
                result = _act(page, name, args)
                if workspace is not None:
                    page.wait_for_timeout(120)  # let a download handler fire
            run.steps.append(ExecStep(step, name, args, result, page.url))
            if verbose:
                print(f"  [{step}] {name}({args}) -> {result[:70]}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        page.wait_for_timeout(300)
        if capture_state:
            try:
                run.final_state = page.request.get(f"{base_url}/api/state").json()
            except Exception:  # noqa: BLE001
                run.final_state = None
        context.close()
        browser.close()

    run.wall_ms = int((time.monotonic() - t0) * 1000)
    return run


def _act(page: Page, name: str, args: dict) -> str:
    try:
        if name == "click":
            return page.evaluate(CLICK_JS, int(args["index"]))
        if name == "type":
            return page.evaluate(TYPE_JS, [int(args["index"]), str(args.get("text", ""))])
        if name == "select_option":
            return page.evaluate(SELECT_JS, [int(args["index"]), str(args.get("option", ""))])
        if name == "scroll":
            amount = 500 if args.get("direction", "down") == "down" else -500
            page.mouse.wheel(0, amount)
            return f"scrolled {args.get('direction', 'down')}"
        return f"unknown tool {name}"
    except Exception as exc:  # noqa: BLE001
        return f"error: {type(exc).__name__}: {str(exc)[:120]}"
    finally:
        page.wait_for_timeout(220)
