"""Prompts and tool schemas for the induction agent.

Adapted from the prompts Work2Skill uses, so that results stay comparable
across the two, with two web adaptations noted inline:

  * "NexAU skill" becomes "skill" -- the output format is the Agent Skills
    convention (a folder containing SKILL.md with YAML frontmatter), which is
    what the paper uses too and what makes induced artifacts portable.
  * video-evidence guidance is unchanged, because the tools are unchanged.

The default induction prompt is deliberately *concise*. The paper's RQ4 ablation
found that prescribing the exploration order ("Pipeline Prompt") scored 3.97
points lower while costing 12.7% more induction tokens, with the suggested
explanation that a fixed route narrows the evidence the model considers. We use
the concise prompt as the default and keep the pipeline prompt as a baseline.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# D.1 Induction system prompt (default, concise)
# --------------------------------------------------------------------------

INDUCTION_SYSTEM = """You extract reusable skills from one recorded computer-use demonstration episode.

- Stay within the exposed input and output roots. Never seek grading rubrics, judge output, reference answers, or files outside them.
- First load `skill-creator`; it is the sole authority for skill boundaries and content. Do not restate, shorten, or weaken its authoring rules.
- Read the authoritative `task.json` before interpreting the trajectory. Treat traces and recordings as fallible evidence; recording completion is not task success.
- When indexed evidence images exist, inspect representative initial, critical, and final-state frames. Before sampling any video, call `get_video_metadata` for that exact path.
- Write generated skill folders only under the output root. Do not create or edit runtime-owned `extraction-manifest.json`, `run-events.jsonl`, `run-metadata.json`, or `run-summary.json`.
- Every skill must ship a machine-checkable completion verifier in `<skill-name>/verify.json`, per the authoring policy. Read it back after its last write alongside `SKILL.md`.
- Read each final `SKILL.md` and `verify.json` after their last writes, then call `finalize_extraction`. Correct every reported error and retry. Only successful finalization completes the task."""


# --------------------------------------------------------------------------
# D.3 Pipeline prompt (baseline: prescribes the exploration order)
# --------------------------------------------------------------------------

PIPELINE_SYSTEM = """You extract reusable skills from recorded computer-use demonstration artifacts.

## Boundaries
- The tools expose one logical input root and one logical output root. Treat those boundaries as absolute.
- Never seek grading rubrics, judge output, reference answers, or files outside the exposed roots.
- The runtime owns `extraction-manifest.json`, `run-events.jsonl`, `run-metadata.json`, and `run-summary.json`. Never create, edit, or overwrite those files.
- A normal text response does not complete the task. Only a successful `finalize_extraction` call completes it.
- The task instruction is authoritative. Recording status only means recording finished; it does not prove task success.
- Read the authoritative task instruction before interpreting the trajectory. Preserve its goals, quantities, exclusions, ordering constraints, and requested scope while parameterizing episode-specific values.
- A demonstrated state change teaches interface mechanics but does not authorize a broader goal or an additional persistent mutation.
- Treat screenshots, action logs, key logs, summaries, and video as fallible evidence that must be reconciled.
- Before the first `watch_video` or `extract_video_frames` call for any video path, call `get_video_metadata` for that exact path. This ordering is irreversible within a run.

## Image evidence
- Files under `evidence/` are event-aligned evidence frames, not arbitrary screenshots. They are decoded from the episode video at each action's time.
- Read `evidence/manifest.json` or `evidence/image_actions.jsonl` before selecting images. These indexes connect each image to its trigger, its frame time, and the nearest trajectory action. A nonzero `action_delta_ms` means the frame and the action were only approximately aligned.
- An event frame shows the UI at or near the input event. Do not assume it proves the action's resulting state. Verify cause and effect by comparing the next relevant evidence frame. Because images are event-triggered, the final successful state may require inspection near the end of the video.
- Pointer coordinates, timestamps, and CSS paths are trace evidence only. Convert them into semantic targets and observable state; never copy them into a reusable skill as fixed instructions.
- Inspect 1-20 representative images together with `read_visual_evidence`. Cover the initial state, critical choices or inputs, important transitions, and the final observable outcome. `watch_video` samples do not replace this full-resolution inspection.

## Workflow
1. Locate and read the authoritative `task.json` before interpreting the trajectory, then inventory the input with `list_directory` and `glob`.
2. Read textual and structured artifacts with `read_file`.
3. Read the evidence index, select representative initial, critical, and final event frames, and inspect them with `read_visual_evidence`.
4. For video, call `get_video_metadata` for the exact path before any sampling.
5. Load `skill-creator` before authoring output.
6. Infer reusable procedures, semantic target-selection rules, observable completion checks, and supported recovery behavior. Separate these from episode-specific values and incidental human actions.
7. Write each skill as `<skill-name>/SKILL.md` under the output root.
8. Before finalizing, read every final `SKILL.md` back with `read_file` after its last write and self-review it.
9. Call `finalize_extraction`. If it reports any problem, correct the output and call it again. Do not finish with an ordinary text response.

## Quality rules
- Do not encode fixed screen coordinates, action sequence indexes, timestamps, local machine paths, session IDs, or one recording's dates, names, IDs, and other instance values as general procedure.
- Prefer semantic UI roles, visible labels, relative state, and task-derived selection criteria.
- Omit actions that appear to be retries, misclicks, idle behavior, or exploratory scrolling unless they reveal a reusable recovery strategy.
- State only what the instruction or observable artifacts support. Express material uncertainty as an observable check instead of inventing hidden success criteria.
- Use the minimum sufficient operational detail. The skill must remain executable without the source recording or extraction manifest."""


INITIAL_MESSAGE = """Load the bundled `skill-creator` policy first. Then read the task in `task.json`, inspect the recorded evidence, author the skill(s) under the output root, read each final `SKILL.md` back after its last write, and call `finalize_extraction` to complete."""


# --------------------------------------------------------------------------
# D.5 Downstream execution wrapper (used by the Day-4 evaluation)
# --------------------------------------------------------------------------

def downstream_wrapper(guidance_text: str) -> str:
    return f"""<task_skills>
The following reusable skills are advisory guidance for this task. Adapt them to the live screen and current task values. The user's task instruction remains authoritative. Do not assume recorded coordinates, timestamps, identities, instance values, or completion state. Verify the requested result in the live environment before finishing.

{guidance_text}
</task_skills>"""


# --------------------------------------------------------------------------
# Tool schemas (Appendices C, in OpenAI function-calling form)
# --------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "load_skill_creator",
            "description": "Load the bundled skill-creator authoring policy. Call this before authoring any output.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories within an exposed directory. Pass '.' for the input root, 'output' for generated files.",
            "parameters": {
                "type": "object",
                "properties": {"dir_path": {"type": "string", "description": "Directory to list. Defaults to '.'."}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern within an exposed directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Filename pattern, e.g. '*.jsonl'."},
                    "dir_path": {"type": "string", "description": "Directory to search. Defaults to '.'."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read text and structured evidence with line numbers. Handles text, JSON, JSONL, YAML, and Markdown. Directs image and video requests to the corresponding tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "line_offset": {"type": "integer", "description": "Zero-based line offset."},
                    "line_limit": {"type": "integer", "description": "Maximum lines to return."},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_visual_evidence",
            "description": "Return an ordered batch of 1-20 images labelled with their source paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "1-20 distinct image paths.",
                    }
                },
                "required": ["file_paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_video_metadata",
            "description": "Inspect video duration, dimensions, frame rate, codec, and file size. Must be called for a video path before sampling it.",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "watch_video",
            "description": "Sample timestamped frames over an interval. At most 20 frames per call; at least 100 ms between samples.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "start_ms": {"type": "integer"},
                    "end_ms": {"type": "integer"},
                    "interval_ms": {"type": "integer", "description": "Defaults to 5000."},
                    "max_frames": {"type": "integer", "description": "Defaults to 12, max 20. Frames are downscaled before they reach you."},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_video_frames",
            "description": "Request frames at selected millisecond timestamps (1-20).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "timestamps_ms": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["file_path", "timestamps_ms"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a complete output file. Writes are limited to the output root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": (
                "Ask the person who gave the demonstration a question you cannot answer "
                "from the evidence. Use this when the demonstration shows WHAT was done "
                "but not WHY -- for example when the produced output excludes items that "
                "none of the rules you can state would exclude. Ask one specific question. "
                "If no person is attached to the run you will be told so, and you must "
                "then declare the gap rather than invent a rule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "One specific question about the procedure or its rules.",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_extraction",
            "description": "Check output structure and tool-use requirements, then write the extraction manifest on success. Only a successful call completes the task.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
