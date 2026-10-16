# skillproof: a technical report

**What this is.** A pipeline that turns one recorded web demonstration into a
reusable skill *and* a machine-checkable completion verifier, plus the
measurements that say what that is worth and where it stops working. The
chronological record, including four conclusions that were published and then
corrected, is [results.md](results.md). This document is the short version: the
claims, the setup, the numbers, the limits, and what would falsify them.

Every number below is recomputable from files in this repository, and every
deterministic one is asserted by `reproduce.py` on every push. Where a number is
model-dependent, the model is named in the same table.

## 1. The claim

1. **The opponent everyone compares against is the wrong one.** GUI-agent
   methods are usually measured against *doing nothing*. The cheap alternative
   is *replaying the demonstration*, and nobody measures it. On the same page a
   replay is perfect; after a UI revision that also removes the test hooks it
   scores 25/100 and a re-parameterized replay-of-the-replay scores 25 as well.
   The only gap worth closing is the one that opens when the page moves.
2. **A skill induced from one demonstration closes that gap, when the induction
   model can write the rule down.** The same pipeline produced a skill whose
   target-selection rule was the word "relevant" (that model was excluded), and
   skills that state the rule explicitly (two other models), at 100/100 on the
   moved page.
3. **A completion verifier is what makes an agent's report of success worth
   anything.** Measured: 10 of 10 unaided declarations were false, 18 of 18
   skilled ones were true.
4. **Page-state verification has a boundary, and it is not the obvious one.**
   It closes *"did the page end up right"*. It does not close *"did you do it
   the way I asked"* — demonstrated on an impossible task where the agent
   substituted an input and the verifier passed with zero declared gaps.

## 2. Method

**Pipeline.** `record → induce → verify → run`.

- **Record.** A demonstration is captured as an *episode*: `task.json`,
  `episode.json`, a normalized action trace with accessible-name targets
  (`<role> - <name>`), an input-event keylog, indexed evidence frames, and a
  video. Recording is either scripted or hand-driven (`record_session.py`).
- **Induce.** An agent with evidence-exploration tools (read files, inspect
  frames, sample video) writes `SKILL.md` per the Agent Skills convention plus
  `verify.json`, an ordered list of assertions. Completion is gated on
  `finalize_extraction`, which validates structure only — the manifest says so
  itself.
- **Verify.** Assertions (`text_present`, `text_absent`, `text_count_at_least`,
  `element_present`, `file_exists`, `json_field_equals`) read the rendered page
  and the workspace. `unverifiable` declares a gap: reported, never blocking,
  and the prose form of a gap is rejected by both validators so it cannot be
  written as a check that never passes.
- **Run.** An executor that sees a screenshot plus a numbered list of
  interactive elements resolved from the DOM, and acts by index, one action per
  turn. This is what makes the comparison about skill quality rather than about
  which condition has better eyes.

**Measurement design.**

- *Rubrics over server state*, not an LLM judge: weighted items summing to 100,
  evaluated against the application's own state, so scoring is deterministic and
  auditable (`bench/evaluator.py`). `SR` = full credit.
- *A perturbation ladder* on the app this repository owns: values changed
  (`jitter`), receipt identity reissued (`jitter-remap`), test hooks removed
  (`-nostid`), sections and labels revised (`relayout`), and the combinations.
- *Third-party controls*: the same comparison on `saucedemo.com` and
  `the-internet.herokuapp.com`, whose controls are renamed under the agent by an
  injected script, because a site nobody here owns cannot be revised directly.
- *The `finished` column is mandatory.* Every record carries the agent's own
  completion declaration, the verifier's verdict, and the count of refusals.
  A table without them reports runs that could not finish as successes.

## 3. Setup

| | |
|---|---|
| Application (benchmark) | ExpenseDesk, a resettable web app in `bench/site` (664 lines of Python plus a small SPA: 1,310 lines in total), written for the benchmark |
| Tasks | `expense-submit`: get a draft travel claim into the approval queue (attach the right receipts, one line per receipt, category, cost center, submit). `expense-report`: build a JSON period report from a CSV export, where "which claims count" is the whole task; a hard variant adds a second non-legible rule |
| Page variants | `default`, `jitter`, `jitter-remap`, `jitter-nostid`, `relayout`, `relayout-nostid`; `reports`, `reports-hard` |
| Scoring | weighted rubrics over server state, weights sum to 100, no LLM judge |
| Executor | DOM-derived element list + screenshot, one action per turn, step budget 25 (benchmark) / 30 (harness default), temperature 0 |
| Executor model | `deepseek-v4.1-flash` (historical runs), `longcat-2.5-preview-free` (2026-10-16 runs) |
| Induction model | `doubao-seed-2-0-code-preview-260215`, `deepseek-v4.1-flash`, `longcat-2.5-preview-free` (see the ablation) |
| Repetitions | N=3 per cell unless stated |

## 4. Results

### 4.1 Deterministic baselines (no model, asserted by `reproduce.py`)

| condition | `default` | `jitter` | `relayout` | `jitter-remap` | `jitter-nostid` | `relayout-nostid` |
|---|---|---|---|---|---|---|
| replay the recording | **100 · SR 100** | 70 · SR 0 | 70 · SR 0 | 35 · SR 0 | 35 · SR 0 | **25 · SR 0** |
| replay, re-parameterized | **100 · SR 100** | **100 · SR 100** | **100 · SR 100** | 65 · SR 0 | 50 · SR 0 | **25 · SR 0** |
| do nothing | 15 · SR 0 | | | | | |

Two readings matter. The re-parameterized baseline — its value readers are
~90 hand-written lines of JavaScript in `replay/macro.py`, one per field, and
it still takes target *selection* from the recording — recovers the *values*
everywhere, and still
collapses to 25 where the page stops supplying stable targets. And a recording
survives relabelling as long as its CSS paths still resolve: `relayout` keeps
the hooks and the replay scores 70.

### 4.2 Agent conditions on the benchmark app

| condition | task | scores | declarations |
|---|---|---|---|
| unaided agent | `expense-submit`, both pages | 56.7 mean over 6 runs | 10 of 10 false |
| skill + verifier | `expense-submit`, `default` | 100 · SR 100 ×3 | 3 of 3 true |
| skill + verifier | `expense-submit`, `relayout-nostid` | 100 · SR 100 ×3 | 3 of 3 true |
| unaided agent | `expense-report` | 35.0 | — |
| skill + verifier | `expense-report` (3 induction modes) | 100 · SR 100 ×9 | — |
| unaided agent | `expense-report-hard` | 20.0 | — |
| skill + verifier | `expense-report-hard` | 100 · SR 100 ×3 | — |

Cost, as means over the live runs (tokens = prompt + completion):

| task | condition | tokens | steps | score |
|---|---|---|---|---|
| `expense-report` | no skill | 56,281 | 9.0 | 35.0 |
| | skill + verifier | 46,377 | 7.4 | 100.0 |
| `expense-submit` | no skill | 96,766 | 12.2 | 56.7 |
| | skill + verifier | 213,448 | 19.0 | 100.0 |
| `expense-report-hard` | no skill | 33,254 | 7.0 | 20.0 |
| | skill + verifier | 195,284 | 17.3 | 100.0 |

The skill is cheaper than the unaided agent on one task and two to six times
more expensive on the other two. **The unaided agent is cheap because it stops
early**: it declares success before checking, so the skill's cost is largely the
work that was being skipped.

### 4.3 The induction ablation (2026-10-16, one free model, one episode)

Addendum 12 left three variables changed between the 70-point and the 100-point
skill; Addendum 14 varies one of them. Same episode, same model
(`longcat-2.5-preview-free`), same settings, one prompt line different
(`--drop-verifier-clause`, recorded verbatim in `run-metadata.json`).

| arm | skill | states the selection rule | scores | steps | finished |
|---|---|---|---|---|---|
| run3 (history, doubao) | 2,133 B | no — "relevant" | 70 · 70 · 70 | 21–22 | 3 / 3 |
| with the clause | 5,998 B | yes | 100 · 100 · 100 | 19–20 | **3 / 3** |
| without it | 6,583 B | yes | 100 · 100 · 100 | 30 · 30 · 30 | **0 / 3** |
| v3 (history's skill) | 6,839 B | yes | 100 · 100 · **85** | 18 · 21 · 30 | 2 / 3 |

- The prompt clause does not earn the selection rule: both arms wrote it, and
  both passed the two receipt-selection rubric items in all six runs. The
  induction model is what remains as the explanation for the 70-point
  generation, at N=1 against N=3, with that model unavailable on this endpoint
  and `image_max_size` unvaried.
- `score` reports nine of nine as fine; `finished` reports five of nine. The
  no-clause arm's runs did the work correctly and spent the whole step budget
  without declaring completion — the verifier never ran, and the rubric, which
  reads end state, scored them 100.
- The stock skill's published 100 · 100 · 100 does not reproduce intact on a
  second executor model: 100 · 100 · 85, one run exhausting the budget. That
  figure is a *(skill, executor model)* claim.
- Cost tracks the skill's precision: 325k tokens at 18 steps versus 843k at 30
  for the same page and the same rubric.

### 4.4 Third-party sites

`saucedemo.com` — log in, compare six prices, add the cheapest, check out:

| | site as-is | controls renamed | renamed, hooks regenerated |
|---|---|---|---|
| replay the recording | completed | completed | **failed — 8 of 14 steps** |
| skill + verifier (×3) | — | — | **completed 3 of 3**, 2 gaps declared |

`the-internet.herokuapp.com` — log in and confirm the secure area
([walkthrough](walkthrough-theinternet.md)):

| | recorded | run | renamed | renamed + re-hooked |
|---|---|---|---|---|
| skill + verifier | 5 actions | 5 steps, verifier PASSED | 5 steps | 5 steps |

The induction asked nothing (12 iterations, 113k tokens), forbade reading
credentials off the login page — which that site prints in plain text — and
hedged about the confirmation banner being dismissible. Handed a password one
character short, the agent read the real one off the page, logged in, and
declared success; the verifier passed and declared no gaps. That is §1.4.

## 5. What went wrong, and what it cost

Ten harness faults and five verifier failure modes are catalogued in
[results.md](results.md) with the runs that produced them. The categories are
the useful part:

- **A control that does nothing looks like a result.** A page-renaming script
  died at document start (`observe(null)`); a whole round of "the skill
  survived the page moving" was measured against a page that had not moved, and
  a *perturbed replay* had been compared against an *unperturbed skill run*.
- **A score without `finished` reports unfinished runs as successes.** The
  verifier gated on a toast (Addendum 4), the stock skill's third repetition in
  §4.3, and all three no-clause runs there — the last four would read as
  successes in any table with only a score column.
- **The evaluator's blind spots become the pipeline's.** A verifier gated on a
  transient toast made the task unfinishable; a gap written as a check made it
  unsatisfiable; a filename collision let two batches write the same records.
- **Owned pages hide whole classes of failure.** Every page this project had
  run against was a single-page app, so the executor's first click that
  navigated killed the run — found on the first real page.

## 6. Threats to validity

- **Two tasks, one app, one demonstration each.** The hard variant is ours too.
- **N=3**, which cannot separate conditions 15 points apart, and the design
  confounds induction variance with execution variance: three repetitions test
  one skill, not three skills.
- **Model-dependent in two places**: the skill is what the induction model can
  write, and the score is a *(skill, executor model)* pair. One of the two
  ablation arms could not be re-run because its model is not served.
- **Public sites can change.** Nothing pins them; these results are
  reproducible today and maybe not tomorrow.
- **No real user has run this on real work.** Every task is a demonstration
  written for a measurement, including the third-party ones.
- **The verifier cannot check provenance.** Which values an agent used is
  invisible to page-state assertions; the demonstrated false success is
  unresolved, not mitigated.
- **`finalize_extraction` validates structure, not correctness.** It says so.

## 7. Reproducing

```bash
bash setup.sh                     # install, then verify the published numbers
.venv/Scripts/python.exe reproduce.py --all --jobs 2   # deterministic cells only
.venv/Scripts/python.exe tests/test_artifacts.py       # every published number, recomputed
```

`reproduce.py` needs no model and no credentials. The agent conditions need an
OpenAI-compatible endpoint (`S2S_INDUCT_BASE_URL`, `S2S_INDUCT_API_KEY`,
`S2S_INDUCT_MODEL`); the 2026-10-16 runs cost nothing on a free model, and the
per-run token counts above are what to expect if you are paying.

## 8. What would falsify the claims

1. **The moved-page gap is not real.** Show a recording or a scripted baseline
   that survives `relayout-nostid` without understanding the task.
2. **Selection is not the moat.** Every failure across two baselines and five
   methods collapsed to target selection; show a task family where the failures
   are elsewhere.
3. **The verifier is decorative.** Find a case where its gate passes work a
   human would call undone — §1.4 is one, and it was found, not mitigated.
4. **The numbers are an artifact of this app.** The third-party results are one
   workflow each on two public sites; a third site that behaves differently is
   a result.
5. **The comparison is unfair.** The executor is given the same page view the
   macro baseline resolves against; if that view is doing work the macro does
   not get, say which step.

If you re-run this and get different numbers, that is the most useful thing you
can send.
