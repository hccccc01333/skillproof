# Superseded runs

Runs kept for the record, whose **referent has been withdrawn**. The numbers
they produced are still cited in `docs/results.md`; the induced skill that
produced them is no longer in the tree.

They live here rather than in `results/` so that `tests/test_artifacts.py` can
hold a simple invariant over the live evidence set: *every run in `results/`
names a skill that is still on disk.* A number whose skill is gone cannot be
re-derived, and a document full of those is a document of anecdotes.

The distinction from `results/_invalid/`:

| directory | meaning |
|---|---|
| `_invalid/` | the run is **not evidence** — it aborted, the instruction mismatched the page, the endpoint refused the account |
| `_superseded/` | the run **was evidence**, and a later run overturned it or replaced the skill it used |

## What is in here

| files | cites | referent | why it is here |
|---|---|---|---|
| `exec-skill-{default,relayout-nostid}-r*.json` (4) | Addendum 3 of `docs/results.md` — the 70/70/70 condition, "procedure transfers, judgement does not" | `induced/run3/expense-submit-default--concise` | the skill was dropped as superseded in `d385b36`; the finding was later overturned by `v3`, which derives the selection rule and scores 100/100 ×3 on the same variant |
| `exec-skill+verifier-reports-r*-report-ask.json` (3) | Addenda 7–10 of `docs/results.md` — the ask-mode condition | `induced/report-ask/expense-report-reports--concise` | same commit; `report-nohuman` and `report-casual` supersede it |

The last column is the important one: **both groups were overturned by later
work, not invalidated by a fault.** Addendum 3's conclusion — that induction
carries procedure across a page revision and does not carry judgement — was
true of `run3` and false of `v3`. Keeping those runs next to their successors is
the point of the record; keeping them in the live set would imply the numbers
are still what the pipeline does.

Recoverable in full from `d385b36^`:

```bash
git checkout d385b36^ -- induced/run3 induced/report-ask
```
