# Recording data format

This document specifies the on-disk format a skillproof episode. It is a
web-adapted version of the Work2Skill evidence schema (Appendix B). Everything
downstream — skill induction, macro replay, evaluation — reads this and
nothing else.

The design goal is that an induction agent written against the paper's schema
can read these episodes without modification. Web-specific fields are added
under new keys; a paper-compatible reader can ignore them.

## Directory layout

```
<episode_id>/
  task.json                     authoritative instruction and task inputs
  episode.json                  manifest: file index, metadata, counts
  trace/actions.jsonl           normalized action records, temporal order
  trace/keylog.jsonl            raw input-event log
  evidence/manifest.json        image index
  evidence/image_actions.jsonl  image <-> action associations
  evidence/000001.png ...       evidence frames
  video.mp4                     recording video
  summary.md                    textual operation summary
```

A real recording is checked in at `episodes/expense-submit-default/`.

`produced/` holds the files the demonstration saved — downloads it made, and
any deliverable the task was supposed to write. **Its paths are relative to the
task's own output root, and the directory name is packaging, not part of the
path.** A task that writes `report.json` produces an episode containing
`produced/report.json`; the deliverable is still `report.json`.

This is called out because it was got wrong: an induction read
`produced/report.json`, concluded the deliverable path was
`produced/report.json`, and generated a completion verifier asserting that
path. The execution agent, being obedient, wrote the file there *as well as*
where the task asked. It scored full marks and the verifier passed — but only
because the agent happened to write both. An agent that had written only the
path the verifier named would have failed the task while satisfying its own
completion check, which is the worst outcome the verifier exists to prevent.

## File contracts

### task.json

The authoritative task statement. The induction agent must read this before
interpreting the trajectory.

```json
{
  "task_id": "expense-submit-default",
  "application": "ExpenseDesk",
  "instruction": "Get my March 2026 travel reimbursement claim into the approval queue.",
  "task_inputs": { "claim_id": "clm_2001", "period": "2026-03" }
}
```

**`task.json` must not contain a grading field.** The writer raises on
`grading`, `rubric`, `grader`, or `answer` keys, so a rubric cannot leak into
the induction agent's input. This matters: the paper's baselines are only
comparable if no method can see how it will be scored.

### episode.json

The manifest. Per the paper, `source` records where the episode was originally
exported from and is **provenance, not an additional input root** — the
induction agent must not follow it.

```json
{
  "schema_version": "s2s-episode/1.0",
  "episode_id": "expense-submit-default",
  "task_id": "expense-submit-default",
  "application": "ExpenseDesk",
  "recording": {
    "duration_ms": 15234,
    "started_at": "...", "finished_at": "...",
    "viewport": { "width": 1280, "height": 860 },
    "user_agent": "...",
    "target_url": "http://127.0.0.1:59263",
    "input_source": "scripted",
    "capture_config": { "...": "effective capture policy, see below" }
  },
  "counts": {
    "actions": 23, "keylog_events": 64, "images": 24, "keyframes": 24
  },
  "files": ["task.json", "episode.json", "trace/actions.jsonl", "..."],
  "evidence_roots": { "input": ".", "output": "output/" },
  "source": "local:default"
}
```

`counts.actions` and `counts.images` differ by design. Frame reuse means
actions and keyframes are **not** one-to-one: an action whose predecessor
frame is still fresh reuses it. Recorded keyframes reflect the capture policy;
exported images reflect later evidence processing.

### trace/actions.jsonl

One JSON object per line, in temporal order. The first six fields are the
paper's; everything from `value` down is web-specific.

| field | meaning |
|---|---|
| `sequence_index` | position in the demonstration |
| `action_id` | stable id, joins to the image index |
| `kind` | `click`, `type`, `select`, `observe`, `verify`, `scroll`, `key` |
| `media_time_ms` | video-relative start time |
| `caption` | what the action did, in words |
| `target_label` | `"<role> - <accessible name>"`, the paper's target form |
| `value` | text entered or option selected |
| `point` | click coordinates |
| `url_before` / `url_after` | page identity across the action |
| `frame_time_ms` | before-action evidence frame |
| `result_frame_time_ms` | frame captured after settling |
| `target` | resolved UI target, see below |
| `raw_event_seqs` | which raw events this action grouped |

The `target` object is the web counterpart of an AT-SPI target element and is
the single most useful field for induction:

```json
{
  "tag": "button", "role": "button",
  "name": "Attach",
  "testid": "attach-rcp_3310",
  "css_path": "button[data-testid=\"attach-rcp_3310\"]",
  "text": "Attach",
  "bounds": { "x": 1190, "y": 698.25, "w": 57, "h": 27.39 },
  "attrs": { "type": "button", "data-testid": "attach-rcp_3310" }
}
```

`role` + `name` are the semantic key. `css_path`, `testid`, and `bounds` are
provenance for the agent to disambiguate with. Coordinates are trace evidence
only and must never be copied into a skill as fixed instructions — the
paper's authoring policy is explicit about this, and the induction prompt
enforces it.

### trace/keylog.jsonl

The raw event stream, ungrouped, one event per line: `pointer_down`, `click`,
`dblclick`, `input`, `change`, `focus`, `key`, `scroll`. Each carries `seq`,
`kind`, `t_ms`, `url`, and a `target` descriptor.

This is the raw layer. `actions.jsonl` is the grouped layer. Keeping both
means the grouping rules can be revised and re-derived without re-recording.

Two deliberate capture policies, both from the paper:

* **Scrolls are emitted once, on settle**, not per scroll tick — the paper's
  "scroll completion" trigger.
* **`input` events record the settled value**, not every keystroke. Full
  keystroke capture is a separate concern; when enabled it lands in
  `key` events.

### evidence/

`manifest.json` indexes every frame; `image_actions.jsonl` is the flat
association form. Each record carries `frame_time_ms`, `trigger`, and
`action_delta_ms`.

`trigger` is one of `boundary`, `before_action`, `result`,
`result_unsettled`.

**`result_unsettled` is load-bearing.** It means the interface was still
changing when the settling window expired, so the frame shows a state, not
necessarily the *final* state. A consumer that treats every `result` frame as
proof the action completed will misread these. This is the paper's position:
"a result-frame link does not by itself establish that the interface has
finished updating."

Never assume an evidence frame proves the action's effect. Because frames are
event-triggered, the final successful state often only appears near the end of
the video.

## Capture policy

Effective values are recorded in `episode.json` under
`recording.capture_config` so an episode is self-describing. Defaults:

| policy | value | rationale |
|---|---|---|
| `before_frame_freshness_ms` | 1500 | reuse a recent frame as before-context; the paper's default. Consequence: before-context can be absent. |
| `settle_timeout_ms` | 2500 | bound on waiting for the UI to stop mutating |
| `settle_quiet_ms` | 260 | no DOM mutation for this long ⇒ settled |
| `max_result_frames_per_action` | 1 | the paper allows up to two; one is enough for a click-driven form |

These are implementation defaults, not tuned settings. They are recorded per
episode precisely so that a reader can tell what policy produced the evidence
rather than assuming.

## Known gaps

Called out so they are not mistaken for done:

1. **`input_source` is `scripted`, not human.** The demonstration is driven by
   `recorder/tasks.py` rather than by a person. The capture, settling, frame
   selection, action grouping, and packaging layers are the same code a human
   session would use; only the input source differs. Out of scope so far; a
   human-in-the-loop path needs an operator-driven browser.
2. **No accessibility-tree snapshot stream.** On the web the DOM *is* the tree,
   so `target` descriptors are read directly at action time. The paper attaches
   independent AX snapshots as surrounding interface context; we have no
   equivalent of a periodic full-tree sample.
3. **No scroll/keyframe milestone triggers.** The paper captures frames at
   scroll milestones. We capture on actions only.
4. **Video evidence is not indexed by interval.** `video.mp4` is produced and
   `media_time_ms` gives the offsets, but there is no episode-level
   `video_intervals.json` describing which spans are worth sampling.
