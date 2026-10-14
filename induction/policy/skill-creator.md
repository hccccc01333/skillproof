---
name: skill-creator
description: Create self-contained, operationally complete skills from inspected
  computer-use evidence. Use when an extractor must convert task instructions,
  action traces, screenshots, and video observations into portable skill folders
  without copying episode-specific details.
---

# Create reusable skills

Convert observed task behavior into instructions that another agent can execute
with fresh task inputs. Describe stable decisions, semantic targets, visible
state, completion checks, and supported recovery rather than replaying the
recorded trajectory. This skill is the authoring policy for generated skills;
do not replace its requirements with a shorter summary.

## Runtime contract

The execution agent receives the generated skill and its bundled resources, not
the source recording, action trace, or extraction manifest. Put every
correctness-critical instruction in `SKILL.md`; supporting references must not be
required to reconstruct an omitted workflow, formula, selection rule, quantity,
ordering constraint, stop condition, or completion check.

For a graphical computer-use task, preserve the interaction modality. Instruct
the agent to make task-state changes through visible application controls and
verify them in the visible application. Never substitute an API, database edit,
script, browser console, developer tool, or other hidden state mutation unless
the authoritative task explicitly requires that mechanism.

Length is not a quality target. Remove generic explanation and trace provenance,
not operational invariants. If removing a detail could change the selected
target, computed value, action order, affected quantity, visible success state,
or recovery behavior, retain it.

## Define the skill boundary

Create one skill for each coherent reusable capability. Keep phases together
when they exchange task-derived data, share application state or counts, or must
execute in a particular order. Split skills only when each capability is
independently invocable and useful; do not fragment one workflow merely to make
individual files shorter.

Choose a short lowercase hyphen-case name under 64 characters. Use the same name
for the output folder and the frontmatter `name`.

## Separate procedure from trace

Treat the task instruction as the goal and the recording as fallible evidence.
Read the task first, then reconcile task data, action logs, evidence images, and
video before stating the reusable procedure. Recording completion alone does not
prove task success.

A recorded state change demonstrates interface mechanics but does not authorize
an extra persistent mutation. Preserve only state changes required by the task,
and retain:

- semantic application, page, dialog, field, item, and control names;
- rules for choosing the correct target from changing task inputs;
- exact formulas, operands, units, basis, thresholds, rounding rules, and where
  each computed result is used;
- requested quantities and scope, including per-item repetition and count-based
  stop conditions;
- dependencies, required order, and data or state passed between phases;
- visible checks after critical mutations and a final observable completion
  check, including refresh or reopen checks when persistence matters;
- evidence-supported recovery from loading delays, stale searches, hidden
  controls, misclicks, dialogs, validation errors, and partial completion.

Remove screen coordinates, action indexes, timestamps, session identifiers,
local machine paths, and retries or idle actions that do not teach recovery.
Replace one episode's names, dates, IDs, routes, values, filenames, and messages
with task-derived parameters when they are inputs rather than reusable constants.

Parameterize episode-specific values without abstracting away the formula,
threshold, relationship between inputs, requested count, ordering constraint,
selection rule, or visible verification that makes the procedure correct. Do not
promote one observed layout, value, or incidental action into a universal
requirement.

When evidence is incomplete, state an observable conditional check or supported
limitation in the skill. Never invent a hidden rubric or success condition.

## Write the skill

Create `<skill-name>/SKILL.md` with `write_file`. Start with exactly this
frontmatter shape:

```
---
name: skill-name
description: Explain what the skill does and the situations that should trigger it.
---
```

Write the body in clear imperative language. Include the complete workflow,
selection and calculation rules, scope and count constraints, phase handoffs,
visible completion checks, and only recovery guidance supported by evidence.
Avoid introductory material a capable execution agent already knows, but never
remove a step, dependency, decision, stop condition, or recovery check that can
affect correctness.

Use semantic UI targets instead of fixed coordinates. When labels or layouts may
vary, give a stable visible role or relationship that identifies the target
without guessing. For persistent changes, verify the resulting visible state;
refresh, revisit, or reopen the relevant view when the observed workflow shows
that this is necessary to distinguish a saved result from a transient one.

Add `references/` only for genuinely supporting knowledge, never as a place to
hide required runtime instructions. Add `scripts/` or `assets/` only when they
are essential to reuse and their correctness can be established from the
available evidence. Do not initialize templates, run packaging scripts, or
create archives.

## Reconcile the demonstration's input against its output

A demonstration shows an input and the artifact the person produced from it. The
difference between them is the procedure, and any rule that explains part of
that difference is a rule you must state.

**Do the diff explicitly, and do not stop at the first rule that fits.** A
recorded run of this harness produced a skill for a reporting task that decided
which rows counted purely from the export's `status` column — correct as far as
it went, and silent about the second rule the demonstration applied, because
`status` was the most legible column in the file. The agent using that skill
scored exactly what an agent with no skill scored.

So:

- Read the demonstrated **output** as carefully as the input. If the
  demonstration produced a file, that file is the answer to the task and the
  most informative artifact in the episode.
- If the output contains fewer items than the input, or different totals, find
  out which ones were dropped and what distinguishes them. Every such
  distinction is a rule.
- Check that your stated rules account for the **whole** difference. If the
  demonstration's output implies an exclusion that none of your rules produces,
  you have not finished.
- Prefer a rule that requires knowing how the work is done over one that reads a
  single obvious field. The field is the easy answer; the demonstration may
  exist precisely because the field is not sufficient.

A rule you cannot find evidence for is a gap to declare, per the verifier
section below — but "I did not look" is not a gap.

### Ask when the demonstration shows what but not why

`ask_human` puts one specific question to the person who gave the demonstration.
Use it when the reconciliation above leaves an unexplained difference: the
output drops items, or applies a rule, that nothing you can state accounts for.

Ask about the **rule**, not the instance. "Why were these two claims left out?"
is answerable and generalises; "were clm_3003 and clm_3006 excluded?" invites a
yes that teaches nothing.

If no person is attached, you will be told so. Then declare the gap — do not
invent a rule to cover it, and do not silently drop the difference either.

#### Some rules cannot be applied, and asking again will not change that

A rule an agent can use needs an **observable test** — something visible on the
page that decides it. Some rules have none. "This purchase was already paid" is
a real organisational rule, and there may be nothing on screen that says so.

You will be tempted to ask where the marker is, because you need one. Ask
**once**. If the answer describes a rule but names no visible marker, then:

- the rule is real and belongs in the skill as a stated **limitation**, so a
  reader knows the procedure does not handle it;
- there is no further question to ask. Repeating the request in different words
  does not produce a marker, and a run of variations on one unanswerable
  question is the worst thing this interaction can do to a person.

State it in the skill like this:

> Claims already settled outside this reimbursement run (for example a purchase
> paid on a company card) must be left off. **No visible field identifies such a
> claim.** Confirm this out of band before relying on the report.

A recorded run of this harness asked the same unanswerable question seven times
in seven phrasings — "where in the app is that visible?", "which element shows
it?", "does the UI display it?" — before finally writing the rule as a
limitation. The last seven questions produced nothing the first answer had not
already given.

## The demonstration's output directory is packaging

Files the demonstration saved — downloads, and any deliverable the task wrote —
are exposed under `produced/`. **That prefix is the episode's packaging, not
part of the task's path.** A task that writes `report.json` shows up as
`produced/report.json`, and the deliverable is still `report.json`.

Never carry `produced/` into a skill, a verifier path, or an instruction. An
execution agent obeys the verifier it is given, so a verifier naming the wrong
path makes the agent write the wrong file — and if it writes *only* that file,
the task fails while the completion check passes.

## Emit a completion verifier

Alongside `SKILL.md`, write `<skill-name>/verify.json`: machine-checkable
assertions that decide whether the task actually succeeded. The execution agent
must run it before it may declare completion, so this is what stands between a
finished task and a confident-sounding unfinished one.

```json
{
  "assertions": [
    {"id": "A1", "type": "text_present", "value": "Pending approval",
     "description": "The claim shows an approval-queue status"},
    {"id": "A2", "type": "text_count_at_least", "value": "Attached", "count": 3,
     "description": "At least three receipts are marked as attached"}
  ]
}
```

Available types:

- `text_present` — a string appears in the page's visible text
- `text_absent` — a string does not appear in the page's visible text
- `text_count_at_least` — a string appears at least `count` times
- `element_present` — an interactive control with a matching accessible name exists
- `file_exists` — a file with the given path exists in the workspace
- `json_field_equals` — a JSON file has a top-level field equal to `expected`;
  `value` is `"<path>:<field>"`, e.g. `"report.json:grand_total"`
- `unverifiable` — declares something the task requires that this assertion
  language cannot check. It carries a `description` and **no** `value`, and it
  never fails the verifier; it is reported as a gap.

**Check the deliverable on the surface where it lives.** A task whose output is
a file must be checked with the file predicates. Asserting a file's contents
against the page's visible text produces a verifier that can never pass, because
the strings are not on the page and never will be — and some of those assertions
will appear to pass, vacuously, for the same reason the task is correct. A
recorded run of this harness produced sixteen such assertions and could not
finish a task it had completed perfectly.

Rules, in order of how easily they are broken:

1. **Assert only what the agent can observe for itself.** These predicates run
   against the rendered page. A verifier that reads application state the user
   cannot see is not verifying, it is asking the grader, and it is worthless the
   moment the task leaves this episode.
2. **Cover the task's completion conditions, not the steps.** "I clicked
   submit" is not a completion condition; "the claim shows Pending approval" is.
3. **Declare the gap when you cannot check something.** If a required condition
   is not expressible in the types above, add an assertion of type
   `unverifiable` whose `description` names what cannot be checked and why. It
   must not carry a `value`: a gap expressed as a checkable assertion makes the
   verifier impossible to satisfy, and an agent that can never finish is worse
   off than one with no verifier at all. An honest gap is worth more than a
   weaker assertion presented as sufficient — the latter is how an agent comes
   to believe it finished a task it did not.
4. **Do not hardcode the episode.** Assertions must hold for the task as
   stated, not for the particular demonstration the skill came from. A verifier
   that checks for "March 2026", or for the recorded receipt names, fails a
   correct run on a page showing April.
4. **Do not pad.** Every assertion must correspond to something the task
   actually requires. Assertions that pass trivially make the verifier look
   complete while checking nothing.

Read `verify.json` back after writing it, exactly as for `SKILL.md`, and include
it in the self-review. `finalize_extraction` validates that it parses and that
every assertion is well-formed.

## Self-review

Before finalization, read every final `SKILL.md` back with `read_file` after its
last write and verify:

- the folder name and frontmatter name match, the description identifies the
  right trigger, and the body is non-empty;
- an execution agent can complete the workflow without the source recording,
  trace, extraction manifest, or unstated episode knowledge;
- graphical tasks make state changes through visible UI actions and do not offer
  backend or developer shortcuts unless the task explicitly requires one;
- every explicit goal, formula, operand, unit, quantity, scope, selection rule,
  ordering relationship, phase handoff, and count-based stop condition needed at
  runtime is present;
- semantic targets replace coordinates and incidental layout;
- critical mutations and the final result have observable UI checks, including
  persistence checks where required;
- every instructed persistent mutation is authorized by the task;
- supported failure modes retain their recovery and stop conditions;
- episode-specific values are parameterized without erasing the relationships
  that govern their use;
- material uncertainty is an observable conditional check or limitation, not an
  invented action or hidden success criterion;
- every bundled file is referenced, necessary, and contains no core instruction
  that belongs in `SKILL.md`.

Call `finalize_extraction`. The runtime writes the extraction manifest. Treat
the finalizer result as authoritative: correct every reported issue and call it
again. Do not finish with an ordinary text response.

---

*Adapted from the skill-creator authoring policy reproduced in Work2Skill
Appendix D.4 (arXiv:2610.12984v1). Web adaptations: "benchmark evidence" is
replaced with the episode's exposed evidence roots, and UI targets are DOM
role/accessible-name based rather than AT-SPI based.*
