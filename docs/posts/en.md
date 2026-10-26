# Show HN draft (English)

## Titles (pick one, ≤80 chars)

1. **Show HN: I measured the GUI-agent baseline nobody runs — replaying the demo** (77)
2. **Show HN: The cheapest GUI-agent baseline wins, until the page moves** (68)
3. **Show HN: skillproof — a recorded demo scores 100 until the page changes** (75)

Recommendation: 1. It names the finding, and the finding is the only reason to
click. "GUI-agent" is the searchable term; "nobody runs" is the hook.

## Body

I built a tool, but the post is about a measurement, so I'll lead with that.

Every GUI-agent paper compares against *doing nothing*. None of them compare
against the free alternative: **replaying the demonstration verbatim**. On the
page the demonstration came from, a replay scores 100/100 — better than every
method I know of — and it costs no model and no tokens.

Then the page moves. On the same task, after a UI revision that also removes the
test hooks, that replay scores **25/100**. A re-parameterized replay — the
"strong version of just script it", re-reading every value from the live page —
also scores **25**. A skill induced from the same one demonstration scores
**100/100**, three times, on both pages.

Three more things the measurements say, all of them uncomfortable:

1. **Self-reported success is worthless without a gate.** Across 28 agent runs
   that declared the task finished: every unaided declaration was false (10 of
   10, scoring 20–75), every declaration gated on a completion check was true
   (18 of 18). A results table without a `finished` column reports unfinished
   runs as successes.
2. **The score and the run disagree.** In one ablation, nine runs scored 100
   except one at 85 — and only five of nine ever declared completion. The middle
   arm did the work correctly three times, spent its whole step budget, and
   never said it was done; the rubric, which reads end state, called all three
   100.
3. **Page-state verification has a boundary, and it is not the obvious one.**
   Handed a password one character short, an agent read the real one off the
   page, logged in, and declared success. The verifier passed — correctly, the
   page was right — and declared no gaps. Completion checks close "did the page
   end up right", not "did you do it the way I asked".

What is in the repo: record → induce (skill + a machine-checkable verifier) →
run, against any web page; the perturbation ladder; ten documented harness
faults; five verifier failure modes; every run file, including the quarantined
ones. `python reproduce.py` checks every deterministic number on the page in
11 seconds, with no model and no credentials — that's the part I'd most like
someone to break.

What it is not: a general automation product. Two tasks on my own app, two
public sites, N=3, one induction model for most cells. A recording still ties a
skill on a page that never moves, so if your page is stable, use a script.

Repo: https://github.com/hccccc01333/skillproof
Report: https://github.com/hccccc01333/skillproof/blob/master/docs/technical-report.md

## First comment (HN convention: post this yourself, right after)

Two things I'd flag as the weakest points, so the thread doesn't have to:

- **N=3, and one app for most of the numbers.** The third-party results are one
  workflow each on saucedemo and the-internet — enough to show the pipeline runs
  on pages I don't own, not enough to generalise. `docs/technical-report.md` §6
  lists all seven threats to validity rather than waiting to be asked.
- **The 100/100 depends on the model on both ends.** The skill is what your
  induction model can write; the score is a *(skill, executor model)* pair. On a
  second executor the same skill reads 100 · 100 · 85, one run having spent its
  step budget without finishing. Addendum 14 in `docs/results.md` has that
  measurement and the confound I could not resolve (one variable, N=1).

If you want the 11-second version: open a codespace from the repo and run
`python reproduce.py`.

## Notes

- Don't say "general-purpose". The post's credibility *is* the limits section.
- Don't lead with the tool. The finding is the story; the tool is the artifact
  that lets someone check it.
- If you want to name the paper this is adjacent to: it fits in one clause after
  "None of them compare against the free alternative", e.g. "including the
  demonstration-to-skill papers". Naming the arXiv adds reach and adds an
  adversary; the claim stands without it.
