# skillproof

**Turn a demonstration into a reusable agent skill — and a completion check that
says what it could not verify.**

```bash
git clone https://github.com/hccccc01333/skillproof && cd skillproof
python -m venv .venv && .venv/Scripts/python.exe -m pip install playwright pillow
.venv/Scripts/python.exe -m playwright install chromium

.venv/Scripts/python.exe reproduce.py        # 11 seconds, no model, no credentials
```

---

## The finding this started from

Everyone measures a new agent method against **doing nothing**. Nobody measures
it against the cheap alternative: **replaying the demonstration**.

So we measured it. A recording replayed verbatim, no model involved:

| | the page it was recorded from | after a UI revision that also drops the test hooks |
|---|---|---|
| **a recording** | **100 / 100** | **25 / 100** |

Two things follow, and both shape everything else here.

**On the demonstrated page, a recording is perfect.** Nothing that learns from it
can beat it there — at best it ties, at more cost. Any claim of the form "our
method beats doing nothing" is measuring against the wrong opponent.

**A recording is worth 75 points less the moment the page moves.** That is the
gap a skill has to close, and it is the only gap worth closing.

## Results

Every number below is measured on this repo's benchmark, three to six runs per
cell, and the recording half reproduces in 11 seconds without a model.

| task | original agent | recording | skill + verifier |
|---|---|---|---|
| claim submission | 56.7 | **100** (demo page) / 25 (revised) | **100 · SR 100** |
| period report | 35.0 | — | **100 · SR 100** |
| period report, two non-legible rules | 20.0 | — | **100 · SR 100** |

## What actually makes it work

This is the part we got wrong first and had to correct, so it is worth stating
plainly.

Some rules a workflow depends on are **not in the data**. In the reporting task,
one claim is excluded because it was already paid on a company card. Nothing in
the export says so. It is visible only as a **difference between what the
demonstration consumed and what it produced**.

An induction that reads the evidence and writes a skill scored **35/100** on
that task — exactly what an agent with no skill scored. Identical wrong output.

**What fixed it was not a better model. It was forcing the induction to
reconcile the two artifacts**: read the produced output as carefully as the
input, find what was dropped, identify what distinguishes it, and account for
the *whole* difference. With that one instruction and no human in the loop, the
same model scores **100/100**.

The induction may also ask the person who gave the demonstration
(`ask_human`), and on a task with two such rules it asks **two questions** — one
per rule — and goes from 20 to 100. But the question is a fallback for rules
that are not visible even in the input/output difference. The reconciliation
step is the load-bearing part.

## Why a completion check, and why it declares gaps

We measured 6 agent runs that declared the task finished. **4 of them were
wrong.** All four said "successfully submitted" while scoring 70–85.

So a skill ships a `verify.json` of machine-checkable assertions, and the
execution agent's `done` is **rejected** while it fails. The gate is real.

The harder half is honesty. A verifier must declare what it *cannot* check
rather than approximate it. From a generated one, unedited:

```
A1  file_exists        report.json
A2  json_field_equals  report.json:period
A3  json_field_equals  report.json:claim_count
A4  unverifiable       whether each excluded claim was excluded for the correct reason
```

`A4` is the point. A verifier that reports a clean pass it cannot support is
worse than no verifier, because an agent obeys the verifier it is given.

## Verify it yourself

```bash
.venv/Scripts/python.exe reproduce.py          # 11s, four decisive cells
.venv/Scripts/python.exe reproduce.py --all    # 21s, all twelve
```

The numbers are **asserted, not derived** — they were published before the
script existed — so a change in behaviour fails the check instead of quietly
becoming a new baseline.

```bash
.venv/Scripts/python.exe tests/test_tools.py   # 24 tool-surface + verifier contracts
```

## Recording your own workflow

```bash
.venv/Scripts/python.exe record_session.py \
    --url https://your-intranet/reports \
    --episode monthly-report \
    --instruction "Prepare the monthly expense report and save it as report.json" \
    --workspace ./work
```

A browser opens with the evidence hook installed. Do the task once, at your own
pace, saving whatever the task is supposed to produce. Close the window; the
episode is written. Then:

```bash
.venv/Scripts/python.exe run_induct.py --episode monthly-report --interactive
```

`--interactive` puts the induction's questions to you on stdin. Answer in your
own words — a rambling spoken sentence works exactly as well as a written one;
we tested both and got identical scores.

## What this does not claim

- **Unattended automation of anything.** A recording beats everything on the page
  it came from, and an induction cannot invent a rule that was never observable.
- **That the tasks are neutral.** They were designed by the person who wrote the
  method. That is the standard credibility hole for a benchmark like this, and
  the mitigation is that the rules are [written down](docs/policies/expense-policy.md)
  with a rubric mapping, so the scoring can be checked rather than believed.
- **That it generalises.** Two tasks, one model, 3–6 runs per cell. Someone
  re-running this will get different numbers.
- **That the verifier is mature.** It failed in four distinct ways during
  development, two of them silently, including one that made an agent write the
  wrong file. All four are documented; the assertion language is deliberately
  small as a result.

## The part we would want you to attack

`docs/results.md` is 900 lines and most of it is what went wrong: **eight harness
faults** that produced plausible-looking numbers, **four verifier failure modes**,
and twelve runs quarantined as invalid with their reasons in the filenames.

Two runs scored **100/100 while being unable to finish**, because their verifier
gated completion on something already false. A results table without a `finished`
column would have reported them as successes.

If you re-run this and get different numbers, that is the most useful thing you
can send us.

## Layout

```
bench/site/      ExpenseDesk, the target web app — resettable, variant-perturbed
bench/evaluator.py   rubrics, scored from server state (no LLM judge)
recorder/        evidence capture producing the paper-aligned episode schema
induction/       the tool surface, the authoring policy, and the loop
verifier/        completion assertions and the runtime that gates on them
replay/          the macro baseline, verbatim and re-parameterised
executor/        the downstream web agent, for every agent condition
docs/            results, the format spec, the published policy, a roadmap critique
reproduce.py     the 11-second verification
record_session.py    record a workflow you drive yourself
```

## Relationship to Work2Skill

An independent reimplementation and extension of
[Work2Skill](https://arxiv.org/abs/2610.12984) (arXiv:2610.12984), on a web
target instead of a desktop one. The episode schema follows the paper's
Appendix B so a reader written for it can read these episodes.

The contribution here is the baseline the paper does not run, and the
measurement discipline around it. See
[docs/results.md](docs/results.md) for what was reproduced, what was extended,
and what was deliberately not attempted.

## License

MIT.
