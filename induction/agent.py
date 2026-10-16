"""The induction agent loop.

Mirrors the paper's Appendix D.2: one agent, structured tool calls, evidence
inspection and skill authoring in the same conversation. There is deliberately
no separate controller state and no numerical information-gain objective -- the
model decides what to inspect next.

The loop ends in exactly two ways:
  * ``finalize_extraction`` returns ok -- the run succeeded;
  * the iteration or wall-clock budget is exhausted -- the run failed.

A plain text response never ends the run. That is the paper's rule and it
matters: without it, a model that narrates a good skill but never writes it
would be scored as if it had produced one.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .prompts import (
    INDUCTION_SYSTEM,
    INITIAL_MESSAGE,
    PIPELINE_SYSTEM,
    TOOL_SCHEMAS,
)
from .tools import DEFAULT_IMAGE_MAX_SIZE, EvidenceTools, ToolError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llm as _llm  # noqa: E402

POLICY_PATH = Path(__file__).parent / "policy" / "skill-creator.md"

# Runtime settings, from the paper's Table 8 (skill-induction settings).
DEFAULT_MAX_ITERATIONS = 100
DEFAULT_CONTEXT_LIMIT = 200_000
DEFAULT_OUTPUT_LIMIT = 16_000

# How many identical finalizer failures in a row before the harness intervenes.
FINALIZE_THRASH_LIMIT = 3

# Re-exported, not redefined. There used to be a second class of this name here,
# left behind when client construction moved into `llm`, and `run_induct.py`
# caught that one while `llm` raised the other -- so an unconfigured model
# escaped as a traceback instead of reaching the handler written for it. Two
# classes with one name is a bug that reads as working code.
from llm import EndpointNotConfigured  # noqa: E402,F401


@dataclass
class InductionRun:
    episode_id: str
    model: str
    prompt_variant: str
    ok: bool = False
    iterations: int = 0
    tool_calls: int = 0
    wall_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: list[str] = field(default_factory=list)
    manifest: dict | None = None
    questions: list[dict] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "transcript"}
        d["transcript_turns"] = len(self.transcript)
        return d


def model_name() -> str:
    return _llm.model_name()


# --------------------------------------------------------------------------
# Tool dispatch
# --------------------------------------------------------------------------

def _dispatch(tools: EvidenceTools, name: str, args: dict) -> Any:
    if name == "load_skill_creator":
        return POLICY_PATH.read_text(encoding="utf-8")
    if name == "list_directory":
        return tools.list_directory(args.get("dir_path", "."))
    if name == "glob":
        return tools.glob(args["pattern"], args.get("dir_path", "."))
    if name == "read_file":
        return tools.read_file(
            args["file_path"], args.get("line_offset", 0), args.get("line_limit", 0)
        )
    if name == "read_visual_evidence":
        return tools.read_visual_evidence(args["file_paths"])
    if name == "get_video_metadata":
        return tools.get_video_metadata(args["file_path"])
    if name == "watch_video":
        return tools.watch_video(
            args["file_path"],
            args.get("start_ms", 0),
            args.get("end_ms", 0),
            args.get("interval_ms", 5000),
            args.get("max_frames", 12),
        )
    if name == "extract_video_frames":
        return tools.extract_video_frames(args["file_path"], args["timestamps_ms"])
    if name == "ask_human":
        return tools.ask_human(args.get("question", ""))
    if name == "write_file":
        return tools.write_file(args["file_path"], args["content"])
    if name == "finalize_extraction":
        return tools.finalize_extraction()
    raise ToolError(f"unknown tool: {name}")


def _render_result(result: Any) -> str | list[dict]:
    """Tool results are text, except image batches which keep their blocks."""
    if isinstance(result, list) and result and isinstance(result[0], dict) and "type" in result[0]:
        return result
    if isinstance(result, dict):
        return json.dumps(result, indent=2, ensure_ascii=False)
    return str(result)


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

def induce(
    *,
    episode_dir: Path,
    output_dir: Path,
    prompt_variant: str = "concise",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_wall_s: float = 1800.0,
    temperature: float = 0.0,
    ask=None,
    verbose: bool = False,
    drop_verifier_clause: bool = False,
) -> InductionRun:
    """Run one induction. `prompt_variant` is 'concise' (ours) or 'pipeline'.

    `drop_verifier_clause` removes the one prompt line that tells the induction
    every skill must ship a completion verifier. It is an ablation, not a
    setting: the tool contract still requires the file, so the run measures what
    the *prompt* is worth, which is the variable that differed between two
    generations of this project's own skills. The prompt actually used is
    recorded in `run-metadata.json`, so the artifact identifies its own arm.
    """
    episode_dir = Path(episode_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    system = INDUCTION_SYSTEM if prompt_variant == "concise" else PIPELINE_SYSTEM
    if drop_verifier_clause:
        kept = [ln for ln in system.splitlines()
                if "machine-checkable completion verifier" not in ln]
        assert len(kept) == len(system.splitlines()) - 1, "clause not found to drop"
        system = "\n".join(kept)
    run = InductionRun(episode_id=episode_dir.name, model=model_name(),
                       prompt_variant=prompt_variant)

    client = _llm.make_client()
    tools = EvidenceTools(episode_dir, output_dir, ask=ask)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": INITIAL_MESSAGE},
    ]

    t0 = time.monotonic()
    last_finalize_problems: tuple[str, ...] = ()
    repeat_finalize_failures = 0
    for iteration in range(max_iterations):
        if time.monotonic() - t0 > max_wall_s:
            run.errors.append(f"wall-clock budget {max_wall_s:.0f}s exhausted")
            break
        run.iterations = iteration + 1

        try:
            resp = _llm.chat(
                client,
                model=run.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=DEFAULT_OUTPUT_LIMIT,
                verbose=verbose,
            )
        except Exception as exc:  # noqa: BLE001
            run.errors.append(f"endpoint error: {type(exc).__name__}: {str(exc)[:300]}")
            break

        if resp.usage:
            run.prompt_tokens += resp.usage.prompt_tokens or 0
            run.completion_tokens += resp.usage.completion_tokens or 0

        msg = resp.choices[0].message
        calls = msg.tool_calls or []

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                **({"tool_calls": [c.model_dump() for c in calls]} if calls else {}),
            }
        )
        run.transcript.append(
            {"iteration": iteration, "text": (msg.content or "")[:400],
             "tools": [c.function.name for c in calls]}
        )

        if not calls:
            # A text-only turn does not complete the run.
            if verbose:
                print(f"  [{iteration}] no tool call: {(msg.content or '')[:120]!r}")
            messages.append(
                {"role": "user",
                 "content": "Continue the work using the tools. Only a successful "
                            "finalize_extraction call completes the task."}
            )
            continue

        finalized = False
        for call in calls:
            run.tool_calls += 1
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if verbose:
                print(f"  [{iteration}] {name}({', '.join(f'{k}=…' for k in args)})")

            try:
                result = _dispatch(tools, name, args)
                tools._log(name, args, result)
            except ToolError as exc:
                result = {"ok": False, "error": str(exc)}
                tools._log(name, args, exc)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                tools._log(name, args, exc)

            if name == "finalize_extraction" and isinstance(result, dict):
                if result.get("ok"):
                    finalized = True
                    run.ok = True
                    run.manifest = result.get("manifest")
                else:
                    signature = tuple(sorted(result.get("problems") or []))
                    if signature == last_finalize_problems:
                        repeat_finalize_failures += 1
                    else:
                        repeat_finalize_failures = 1
                        last_finalize_problems = signature
                    if repeat_finalize_failures >= FINALIZE_THRASH_LIMIT:
                        # The agent is circling. Say so plainly rather than
                        # letting it burn the budget: a failing finalizer with
                        # an unchanged problem set is not a signal to try again
                        # verbatim, and there is no delete tool, so the fix is
                        # always an in-place correction.
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "finalize_extraction has now failed "
                                    f"{repeat_finalize_failures} times with the same problems:\n"
                                    + "\n".join(f"- {p}" for p in signature)
                                    + "\n\nStop creating new skill folders. There is no delete "
                                    "tool, so extra files cannot be removed. Fix the reported "
                                    "problems by rewriting the existing files in place with "
                                    "write_file, read each one back, then finalize."
                                ),
                            }
                        )
                        repeat_finalize_failures = 0

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _render_result(result),
                }
            )

        if finalized:
            break

    run.wall_ms = int((time.monotonic() - t0) * 1000)
    run.questions = list(tools.questions)

    # Runtime-owned artifacts, written regardless of success. The paper's
    # runtime writes provenance, event logs, and a run summary too.
    (output_dir / "run-events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in tools.events) + "\n",
        encoding="utf-8",
    )
    (output_dir / "run-metadata.json").write_text(
        json.dumps(
            {
                "episode_id": run.episode_id,
                "model": run.model,
                "prompt_variant": run.prompt_variant,
                "temperature": temperature,
                "max_iterations": max_iterations,
                "image_max_size": DEFAULT_IMAGE_MAX_SIZE,
                "demonstrator_attached": ask is not None,
                "system_prompt": system,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "run-summary.json").write_text(
        json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return run
