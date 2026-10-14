# show2skill

Inducing reusable, parameterized agent skills from recorded GUI demonstrations,
with a web target instead of a desktop one.

This is an independent reimplementation and extension built on the evidence
schema and induction method of **Work2Skill: Capturing Human GUI Experience for
Reusable Agent Skill Induction** (arXiv:[2610.12984v1](https://arxiv.org/abs/2610.12984),
[official repo](https://github.com/china-qijizhifeng/Work2Skill)). See
[Relationship to Work2Skill](#relationship-to-work2skill) for exactly what is
reproduced and what is new — that split is deliberate and load-bearing.

## Verify the headline yourself, in 11 seconds

No model, no API key, no credentials:

```bash
git clone <this repo> && cd show2skill
python -m venv .venv
.venv/Scripts/python.exe -m pip install playwright pillow
.venv/Scripts/python.exe -m playwright install chromium

.venv/Scripts/python.exe reproduce.py          # 11s, four decisive cells
.venv/Scripts/python.exe reproduce.py --all    # 21s, all twelve
```

The claim it checks:

> Replaying a recorded demonstration scores **100/100** on the page it was
> recorded from. After a UI revision that also drops the test hooks, the same
> recording scores **25/100**.

Macro replay is deterministic, which is why this needs nothing but Python. The
numbers are **asserted rather than derived** — they were published before the
script existed — so a change in behaviour fails the check instead of quietly
becoming a new baseline.

The rest of the project's results do need a model and do depend on trusting a
task design, a rubric and a model choice. Those are the ones worth arguing with,
and [docs/policies/expense-policy.md](docs/policies/expense-policy.md) exists so
that the rubrics can be checked rather than believed.

## Status

Five days executed end to end: demonstration recorded, skill induced, agents
run, everything scored against a deterministic rubric by a state-based
evaluator. **The headline claim holds, and the number that decides it is the
gap between a recording and an induced skill on a page that moved.**

| condition | `default` | `relayout-nostid` | SR |
|---|---|---|---|
| original agent | 58.3 | 55.0 | 0 % |
| agent + skill (first induction) | 70.0 | 70.0 | 0 % |
| agent + skill + verifier (broken verifier) | 90.0 | 75.0 | 0 % |
| **agent + skill + verifier** | **100.0** | **100.0** | **100 %** |
| macro, re-parameterized | 100.00 | **25.0** | 0 % |
| macro, verbatim | 100.00 | 25.0 | 0 % |
| do-nothing floor | 15.00 | 15.00 | 0 % |

`relayout-nostid` is the honest version of "换新数据、调整页面布局": new data,
every control relabelled, sections reordered, and the test hooks a recording
would lean on removed. Three runs, three perfect scores, three declarations of
completion.

The induced skill **ties the recording on the demonstrated page and beats it by
75 points on the revised one.** The paper's comparison against No Skill cannot
show this, because it never measures the recording.

### What made the difference

The first induced skill captured the whole procedure and reduced the actual
decision — which receipts belong — to the word "relevant". Every run that used
it attached the personal hotel upgrade. The second states the rule, and the
criterion that had passed once in eleven runs across every earlier condition
passes five times out of five.

Getting there required two fixes, both documented: the evidence pipeline had to
actually downscale frames (`image_max_size` was accepted and ignored, and
induction could not finish on an image-heavy request), and the authoring policy
had to force a completion verifier — which in turn had to be a *correct*
verifier, because a broken one makes the task unfinishable rather than merely
unreliable.

Full results, including the seven harness bugs found along the way, the twelve
runs quarantined as invalid, and the two baselines rebuilt because they
flattered the wrong method: [docs/results.md](docs/results.md).

### The boundary, from a second task

Task 1's result was strong enough to be suspicious — one task, designed by the
person running the experiment, whose judgement happened to be derivable from
receipt titles. So a second task was built with a different shape of judgement:
open the Reports section, download the period's expense lines, decide which rows
count, aggregate by cost center, write `report.json`.

| task | condition | mean | SR | declared done |
|---|---|---|---|---|
| claim (per-item judgement) | original agent | 56.7 | 0 % | 5/6 |
| | + skill | 70.0 | 0 % | 4/4 |
| | + skill + verifier | **100.0** | **100 %** | 6/6 |
| report (table-level judgement) | original agent | 35.0 | 0 % | 3/3 |
| | + skill, no question | 35.0 | 0 % | 3/3 |
| | + skill, curated answer, + verifier | **100.0** | **100 %** | 3/3 |
| | **+ skill, casual answer, + verifier** | **100.0** | **100 %** | 3/3 |

On the report task the induced skill **changed nothing** — identical wrong
output, identical score. The judgement there has three rules; two are explicit
CSV columns and one (`Meals & Entertainment` is reimbursed elsewhere) is visible
only as a difference between the demonstrated input and the demonstrated output.
The skill states the two column rules, in its own words says to "decide it from
the export's `status` column", and stops.

**The method transfers a rule that is legible as a column and does not transfer
one that must be inferred by reconciling two artifacts.** Task 1's rule was
judgement too — "a title containing `Personal`" is not a column — and it
transferred. The line is not procedure versus judgement; it is whether the rule
can be read off a field.

That is fixable, and the fix is a product affordance rather than a better model.
The authoring policy now requires reconciling output against input, and the
induction may call `ask_human` — which reads stdin, so the interaction is the
real one. Given both, it asked this, unprompted:

> …the approved claims clm_3003 (client dinner) and clm_3006 (team coffee) were
> left out of claim_ids, while other approved claims were included. The only
> field that separates them is `category = "Meals & Entertainment"`. Is the
> counting rule "exclude the Meals & Entertainment category specifically", or is
> there a broader non-reimbursable-category policy…?

**One answered question takes the task from 35 to 100**, and it works on a real
answer rather than a curated one. The demonstrator who produced the 100 above
said:

> oh, a few different reasons there. the ones that aren't approved yet obviously
> don't count… the april one's just a different month… and the food ones… yeah
> we never put those in the period report, they get handled somewhere else
> entirely. has been like that for as long as i've been here.

Unstructured, out of order, no category name quoted back. The skill states all
three rules precisely and adds a warning the answer did not contain. **The
interaction does not require the user to phrase anything carefully**, which is
the property a shipped plugin needs.

The human's narration is load-bearing, and the plugin's job is to ask for the
part the recording cannot carry.

## The comparison the paper does not run

The paper compares against No Skill, ShowUI-Aloha, and Demo2Tutorial — all
*text guidance* methods — and reports gains over No Skill. On the demonstrated
page, replaying the recording is already perfect, so that comparison sets a bar
a recording clears for free. The interesting question is not whether induction
beats no-skill but **which** part of the task requires it, and the baseline
ladder built here answers that: structure, ordering, values and completion
checks are all mechanical, and judgement is what is left over.

## Completion verifiers

The paper's `finalize_extraction` checks output structure and tool use and
states that it does **not** verify correctness — which is how 67% of the
completed runs measured here declared success while scoring 70-85.

A skill therefore ships a machine-checkable verifier in `verify.json`, and the
executor's `done` is rejected while the verifier fails. The gate is real, and
the first generated verifier was broken in three independent ways — one caught
by the validator, two not — including an assertion on a confirmation *toast*
that hides itself after 3.2 seconds. That made the task unfinishable on the
demonstrated page: two runs scored a perfect 100/100 and could not declare
completion. See [docs/results.md](docs/results.md).

The finding for the product is that a verifier is only useful when its
assertions are about **persistent, meaningful** state; a broken one does not
make an agent lie, it makes an agent unable to stop.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install playwright
.venv/Scripts/python.exe -m playwright install chromium

.venv/Scripts/python.exe run_sample.py            # record the default episode
.venv/Scripts/python.exe run_sample.py --headed   # watch it happen

.venv/Scripts/python.exe run_macro.py --variant default        # macro baseline
.venv/Scripts/python.exe run_macro.py --variant jitter
.venv/Scripts/python.exe run_macro.py --variant jitter-nostid
```

That serves the target app, drives a demonstration against it, and writes an
episode to `episodes/<episode_id>/`. A recorded episode is checked in at
`episodes/expense-submit-default/` so the format can be inspected without
running anything.

`ffmpeg`/`ffprobe` must be on `PATH` (Playwright records WebM; the schema
specifies `video.mp4`).

## Layout

```
bench/site/            ExpenseDesk, the target web application
  server.py            stdlib HTTP server + JSON state API, resettable
  static/              the UI, laid out from the variant's layout_spec
bench/evaluator.py     weighted rubric over server state
recorder/
  capture.js           injected browser hook: structured UI evidence per event
  schema.py            the episode format, authoritatively
  recorder.py          Playwright driver: settling, frame capture, grouping
  tasks.py             per-variant instructions + demonstration
induction/
  tools.py             evidence-exploration tool surface (paper Appendix C)
  policy/              skill-creator authoring policy (Appendix D.4)
  prompts.py           induction prompts (D.1, D.3, D.5) + tool schemas
  agent.py             the induction loop
verifier/checks.py     completion-verifier assertions and their runtime
replay/macro.py        fixed-replay baseline, verbatim and re-parameterized
executor/agent.py      downstream web agent (all agent conditions)
llm.py                 shared provider client with retry/backoff
tests/test_tools.py    tool-surface + verifier contract assertions
docs/evidence-schema.md      the format spec
docs/day2-macro-baseline.md  baseline results and what they imply
docs/results.md              full results, exclusions, and conclusions
docs/roadmap-review.zh-CN.md roadmap critique
results/                     per-condition records; _invalid/ holds exclusions
episodes/                    recorded episodes, one per variant
```

## The target application

`bench/site` is a small reimbursement portal built for one purpose: to make
every experimental condition start from a byte-identical state. `POST
/api/reset` restores the seed, so a demonstration, a replayed macro, and a
free-running agent face exactly the same starting point, and task success is a
pure function of server state rather than of a screenshot someone eyeballed.

`--variant jitter` serves the same application with changed entities,
parameters, and constraints. That is the Week-3 "changed page" condition.

The demonstration reads the values it enters **off the screen** — the cost
center from the header, the receipt amounts from the receipt rows — rather
than hardcoding them. This matters more than it looks: a demo that hardcoded
them would still record cleanly under `--variant jitter`, but it would be
demonstrating the *old* values against the *new* page, and the changed-page
condition would prove nothing. Verified: under jitter the recorded amounts
become `538.20` (was `412.80`) and the cost center `CC-5120` (was `CC-4471`).

The recorded task deliberately separates *goal* from *procedure*. The
instruction is only:

> Get my March 2026 travel reimbursement claim into the approval queue.

Everything needed to actually do it — which claim, which three receipts, that
the personal hotel upgrade stays off, that the total crosses a cost-center
threshold, that submission needs confirmation — is carried by the
demonstration and nowhere else. That gap is the thing being studied.

## Relationship to Work2Skill

### Reproduced

- **Episode evidence schema** (paper Appendix B): `task.json`, `episode.json`,
  `trace/actions.jsonl`, `trace/keylog.jsonl`, `evidence/`, `summary.md`,
  `video.mp4`, with the paper's field names. A reader written for the paper can
  read these episodes.
- **Rubric isolation**: `task.json` carries no grading field, enforced in code.
- **Capture policies** (Appendix A.2): before-action frame reuse with a 1.5 s
  freshness limit, settling before result frames, scroll emitted on completion
  rather than per tick, and the `result_unsettled` distinction that stops a
  frame from being read as proof of completion.
- **Evidence-exploration tool surface** (Appendix C) is the interface the
  induction phase will be built against: file discovery and paged reading,
  batched image inspection, video metadata before sampling, timestamped frame
  extraction, restricted writes, and a validating finalization step.

### Original

- **Web instead of desktop.** The paper records macOS screen regions via
  ScreenCaptureKit with CoreGraphics event taps, against a Linux guest queried
  through AT-SPI over an SSH tunnel. That stack is the main reason its
  pipeline is hard to reproduce, and it is replaced here with a browser, which
  collapses three problems into one: capture is in-process, targets are
  resolvable exactly rather than by proximity ranking over sampled snapshots,
  and the environment is a local process instead of a VM. The interesting
  question — whether human procedural knowledge can be induced into a reusable
  parameterized skill — does not depend on which of the two it runs against.
- **A macro-replay baseline.** The paper compares against No Skill,
  ShowUI-Aloha, and Demo2Tutorial. All three are *text guidance* methods. None
  of them tests the obvious cheap alternative: replaying the recorded action
  sequence verbatim. It turns out to matter a great deal — the macro scores
  **100/100 on the demonstrated task**, so the paper's "No Skill" comparison
  (15/100 here) sets a bar that a competent non-inductive method already
  clears. See [docs/day2-macro-baseline.md](docs/day2-macro-baseline.md).
- **Cost accounting as a first-class result.** The paper reports score and
  success rate as its headline numbers; its own Table 2 shows induction token
  usage roughly double the baselines (334.5k vs 170.7k on GPT-5.5/MyPCBench)
  and *more* execution steps than No Skill for one of four models. Cost here is
  measured and reported alongside success, not as a footnote.

### Not attempted

The paper's desktop pipeline, `WorkDemo-350`, and its benchmark task sets are
not reproduced. WorkDemo-350 requires the macOS recorder and hours of human
demonstration; its task sets depend on MyPCBench and OSWorld environments. The
official repo currently ships the recorder, an induction example, and task
definitions, with evaluation integration still pending.

## License

Code is MIT. The reference paper text is not redistributed.
