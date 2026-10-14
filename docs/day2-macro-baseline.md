# Day 2 results: the macro-replay baseline

> **Superseded in part.** Two corrections were made after Day 5 and are
> detailed in [results.md](results.md). First, `jitter` left receipt
> identifiers stable, so the macro's 70.00 included 35 points it earned by
> replaying recorded ids; adding `jitter-remap` drops it to 35.00. Second, all
> agent-condition runs on `jitter` are discarded because the perturbation
> renamed the claim on the page but not in the task instruction, making the
> task unsatisfiable. The `default` and `jitter-nostid` rows below stand.

This is the baseline the Work2Skill paper does not run. Its three comparison
methods — No Skill, ShowUI-Aloha, Demo2Tutorial — all produce *text guidance*
that a model interprets. None of them asks the cheaper question: replay the
recorded action sequence verbatim and see how far it gets.

The answer changes what this project is arguing for.

## Results

Episode replayed: `expense-submit-default` (23 actions, recorded on the
default page). Rubric: 7 weighted items, 100 points, success requires all.

| condition | Score | SR | failed steps | target resolution |
|---|---|---|---|---|
| `default` — the demonstrated page | **100.00** | **100** | 0 / 23 | `testid` ×19 |
| `jitter` — changed values, hooks intact | 70.00 | 0 | 0 / 23 | `testid` ×19 |
| `jitter-nostid` — changed values, no hooks | 35.00 | 0 | 4 / 23 | `role+name` ×15, **failed ×4** |
| *do-nothing floor* | 15.00 | 0 | — | — |

The do-nothing floor is 15 points because R5 ("no non-trip receipt attached")
is vacuously satisfied by an agent that attaches nothing. That is a real
weakness of the rubric, and it is reported rather than patched, because
patching it now would be tuning the rubric to flatter whichever method is
being measured. Affect on SR: none — SR requires every item, so a no-op still
scores 0.

## What the three rows mean

**Row 1 is the finding that matters most.** The macro scores a perfect 100 on
the demonstrated task. No induction method can beat it there — at best it can
tie, at higher token cost. This is why comparing against "No Skill", the way
the paper does, is not a fair test of whether induction is worth doing: it
sets the bar at 15 when a competent alternative already reaches 100.

**Row 2 is target staleness.** The macro executes flawlessly — zero failed
steps — and produces a factually wrong claim. It enters the cost center
`CC-4471` that was on screen during recording; the page now says `CC-5120`.
It enters `712.50` in lines; the receipts now total `837.90`. Everything the
macro does works, and the result is still wrong. Cost: 30 points and success
rate 100 → 0.

**Row 3 is target ambiguity.** With the `data-testid` hooks removed — which is
what a real third-party site looks like — the macro falls back to role and
accessible name and dies in four places. Three different buttons are all named
"Attach", so it cannot tell them apart, and the claim title changed from
"March 2026" to "April 2026" so the entry step no longer matches. A macro has
no disambiguation strategy and no recovery policy; it stops.

## A correction to how this baseline is usually described

It is tempting to say "macros break when pages change." Rows 2 and 3 show that
is two different failures with different mechanisms, and only one of them is
about the page changing:

| failure | triggered by | mechanism | recoverable by a macro? |
|---|---|---|---|
| stale values | task parameters changing | cannot re-read the page | no |
| ambiguous targets | losing stable hooks | cannot disambiguate | no |

Notably, **the changed page alone does not break this macro.** Row 2's page
changed and the macro resolved all 19 targets without incident, because
`data-testid` is stable across the jitter. On the web a recorded macro is
structurally *more* robust than the paper's desktop equivalent, which resolves
through AT-SPI snapshots and proximity ranking. The macro's weakness is
semantic, not structural, and the honest framing is about values and
disambiguation rather than about breakage.

## What this sets up for Day 3

The bar an induced skill must clear, in order of difficulty:

1. **On `default`** — must reach 100/100, or the macro wins outright. A skill
   that scores 85 here has lost to the baseline, regardless of what the paper
   reports against No Skill.
2. **On `jitter`** — must re-read the page and use `CC-5120` and `837.90`,
   rather than replaying recorded constants. This is the case induction has to
   make, and it is the one the paper does not test.
3. **On `jitter-nostid`** — must resolve targets by semantic role and visible
   label without relying on test hooks, which is exactly what the paper's
   authoring policy demands ("use semantic UI targets instead of fixed
   coordinates... give a stable visible role or relationship").

Point 3 is worth noting: the paper's skill-authoring policy already requires
skills to be written this way. `jitter-nostid` is the condition that actually
measures whether the induced skill obeys its own policy.

## Reproducing

```bash
.venv/Scripts/python.exe run_macro.py --variant default
.venv/Scripts/python.exe run_macro.py --variant jitter
.venv/Scripts/python.exe run_macro.py --variant jitter-nostid
```

Macro replay is deterministic — no model is involved — so a single trial is
the correct sample size, not a shortcut. Raw records land in `results/`.
