# Superseded runs

Runs kept for the record, whose **induction is no longer what the pipeline
would produce**. The numbers they produced are still cited in `docs/results.md`
— that is why they are kept — and they are here rather than in `results/` so
the live aggregates (the README's means, the cost table) do not mix generations.

The distinction from `results/_invalid/`:

| directory | meaning |
|---|---|
| `_invalid/` | the run is **not evidence** — it aborted, the instruction mismatched the page, the endpoint refused the account |
| `_superseded/` | the run **was evidence**, and a later run overturned it or replaced the skill it used |

The skills these runs name are still on disk, on purpose: `induced/run3` and
`induced/report-ask` were briefly deleted as a tidy-up, which left seven run
files citing nothing, and `tests/test_artifacts.py` now refuses that. Deleting a
generation does not delete the numbers that were published from it.

| files | cites | skill | why it is here |
|---|---|---|---|
| `exec-skill-{default,relayout-nostid}-r*.json` (4) | Addendum 3 of `docs/results.md` — the 70/70/70 condition, "procedure transfers, judgement does not" | `induced/run3/expense-submit-default--concise` | the induction cannot write down the selection rule; `v3` can, and scores 100/100 ×3 on the same variant |
| `exec-skill+verifier-reports-r*-report-ask.json` (3) | Addenda 7–10 of `docs/results.md` — the ask-mode condition | `induced/report-ask/expense-report-reports--concise` | `report-nohuman` supersedes it: the question turned out to be a fallback, not a requirement |

The last column is the important one: **both groups were overturned by later
work, not invalidated by a fault.** Addendum 3's conclusion — that induction
carries procedure across a page revision and does not carry judgement — was true
of `run3` and false of `v3`. Keeping those runs next to their successors is the
point of the record; counting them in the live set would imply the numbers are
still what the pipeline does.
