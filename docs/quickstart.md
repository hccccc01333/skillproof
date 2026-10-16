# Your first ten minutes

You have a web task you do by hand, on a page that changes. In ten minutes you
can have a skill that does it and a check that tells you whether it worked. This
is the shortest path, with the parts that will bite you marked.

> **What this is not.** It is not a consumer product: it needs Python, Playwright
> and an OpenAI-compatible model endpoint. And if your page never changes, do
> not use this — a script or a macro recorder is free and beats it. The skill
> earns its cost where the page moves. ([technical report](technical-report.md)
> has the numbers.)

## 0. What you need

- Python 3.12, and `ffmpeg` on your PATH (video evidence).
- A model endpoint with a model that can hold a long context. The induction for
  one demonstration reads traces, frames and video: expect **110k-650k prompt
tokens per induction** and **31k-850k per skill run**. That spread is mostly how
precise the induced skill turned out, not how big the task was.

- About 10 minutes for a short task, and the willingness to watch it fail the
  first time.

## 1. Install

```bash
git clone <this repo> && cd skillproof
bash setup.sh          # or: powershell -File setup.ps1
```

`setup.sh` installs the dependencies and then runs `reproduce.py`, which checks
every deterministic number in the docs against a live ExpenseDesk. If that
passes, the machinery works on your machine. It needs no model and no API key.

## 2. Point it at your endpoint

```bash
export S2S_INDUCT_BASE_URL=https://your-endpoint/v1
export S2S_INDUCT_API_KEY=...
export S2S_INDUCT_MODEL=<a model id your endpoint serves>
# some gateways need a session header; this one takes JSON:
export S2S_INDUCT_EXTRA_HEADERS='{"x-some-gateway-session":"any-stable-id"}'
```

`S2S_INDUCT_MODEL` has no default on purpose: the model is your choice and your
bill, and a wrong id fails at the first call with the error naming the model.

## 3. Record your task — once, by hand

```bash
.venv/Scripts/python.exe record_session.py \
    --url "https://your-intranet/thing" \
    --episode my-task \
    --instruction "Get the March invoice approved and confirm the reference appears in the list."
```

A browser opens. **Do the task once, slowly, the way you would explain it to a
new colleague.** Then close the browser and the episode is written to
`episodes/my-task/`: the actions with the accessible names it saw, the frames
around each action, a video, and your instruction.

What matters, in order:

1. **The instruction is the contract.** A later run gets your instruction and
   the skill, nothing else. Write it as a request ("get X into Y"), not as
   steps.
2. **One demonstration is one task.** Two tasks in one recording produces a
   skill that does both, always.
3. **Type values as they are given to you**, not the ones on the page — the
   induction is supposed to learn "read it from the request". It does not always
   (see §7), and a skill that hardcodes your March invoice will quietly re-submit
   the same invoice in April.
4. **No page can be reset.** Remember where your page starts; a re-run begins
   from whatever state the site is in.

To see what an episode looks like without recording your own, start the
benchmark app in one terminal and drive a real workflow into an episode with no
person at the keyboard:

```bash
# terminal 1: the benchmark app
.venv/Scripts/python.exe bench/site/server.py --port 8099

# terminal 2: drive a real workflow into an episode, no person at the keyboard
.venv/Scripts/python.exe record_session.py --selftest --url http://127.0.0.1:8099 --episode my-selftest
```

Then `run_induct.py --episode my-selftest` on it, and compare what you get with
`induced/human-recorded/` in this repo, which came from the same exercise.

## 4. Induce the skill

```bash
.venv/Scripts/python.exe run_induct.py --episode my-task
```

It reads the recording, looks at frames and video, and writes
`induced/my-task/my-task--concise/<skill-name>/` containing `SKILL.md` and
`verify.json`. Expect 10–20 turns and a few minutes on a free model.

**It may ask you questions**, when the recording shows a decision it cannot
explain from anything visible (an exclusion rule, a threshold you applied from
memory). Add `--interactive` and answer them: answers become statements in the
skill, and a rule with no visible marker becomes a declared gap instead of a
guess. If it asks the same question repeatedly, the answer you gave has no
observable marker — say so, and it will write the rule as a limitation.

## 5. Run it

```bash
.venv/Scripts/python.exe run_skill.py \
    --skill induced/my-task/my-task--concise \
    --url "https://your-intranet/thing" \
    --instruction "Get the March invoice approved and confirm the reference appears in the list."
```

This is the command you would put in a scheduler. It ends with the agent's own
claim *and* the verifier's verdict, and it separates the two kinds of "I could
not check this":

```
steps 12  wall 47s  tokens 41,203
declared done: True
  "Submitted the invoice and confirmed the reference INV-2026-0311 in the list."
verifier: PASSED (2 runs, 0 completion attempt(s) refused)
  [PASS] A1: the reference appears in the approval list
  [GAP ] A4: whether the approver is the one the request named
         cannot be checked: the list does not show approvers
```

**Read the `[GAP]` lines before you trust the `[PASS]` ones.** A gap is where
your automation has told you, unprompted, what it is not checking. Zero gaps on
a task with hidden rules is a warning sign, not good news (§7).

## 6. Prove the point to yourself

Change something on the page — rename a button, move a field — and run it again.
The skill should re-locate the control by meaning. If you want a repeatable
version of that, `--perturb` injects JavaScript on every page load, the way the
third-party tests do:

```bash
# the skill from the walkthrough, against the page it was recorded from, with
# the controls renamed on every load
.venv/Scripts/python.exe run_skill.py \
    --skill induced/theinternet/theinternet--concise \
    --url https://the-internet.herokuapp.com/login \
    --instruction "Log in to the-internet with the username 'tomsmith' and the password 'SuperSecretPassword!', then confirm the secure area is displayed." \
    --perturb "$(cat bench/external/perturb-theinternet.js)"
```

## 7. What will bite you

From this project's own fault list — these are the ones a user meets, not the
ones that only mattered to the author:

- **Pages that navigate.** Until 2026-10-16 the executor died on the first click
  that submitted a form, because every page it had ever run against was a
  single-page app. Fixed, and now tested offline.
- **The step budget is real.** Runs get 30 steps by default and a verbose skill
  can spend all of them and never declare completion. The record will say
  `finished: false` with a good score — believe the `finished`.
- **Your verifier is only as good as its assertions.** The generated ones read
  page text and workspace files. They cannot check *which values* the agent
  used: a run that substituted an input it found on the page passes a clean
  verifier. If your task has that shape, write the gap by hand.
- **Your induction model sets the ceiling.** The same episode and pipeline
  produced the rule "attach the relevant receipts" on one model and an explicit
  two-condition rule on others. If your skill reads vague, that is the model,
  not the prompt.
- **Free tiers refuse for capacity.** The client waits and retries a bounded
  number of times; a long induction can still die at iteration 17.
- **No reset, no state API.** On a site you do not own, a run starts from
  whatever the site serves, and everything is judged from the rendered page.

## 8. When not to use this

- **The page does not change.** Record it and replay it; it is free, instant,
  and scores the same. The 100/100 replay in the docs is a warning, not a
  fixture: it is worth 25 the moment the page moves.
- **A step needs a secret you will not show a model.** Password fields are
  redacted in the recording — the field's value, the keystrokes, and the settled
  value, all three since 2026-10-16 (before that only the value was, and a
  hand-typed password came back out of the keylog one character at a time;
  `tests/test_recorder.py` now fails if that regresses). Redaction covers the
  *recording*, not the run: a credential the task supplies still travels to the
  model in the instruction, and a page that prints a secret in plain text puts
  it in a screenshot. If neither of those is acceptable where you work, the
  induction is not the right tool for that task.
- **You need pixel-level verification** (a chart is correct, a canvas rendered).
  The assertion language cannot see it, and a gap is the honest output.
- **You need unattended trust on the first run.** Watch it work a few times
  first; the record's `finished` and the gaps are what you are watching for.

## 9. Where the numbers live

| | |
|---|---|
| `docs/technical-report.md` | the claims, the setup, the tables, the limits |
| `docs/results.md` | the chronological record, including four published conclusions that were corrected |
| `docs/walkthrough-theinternet.md` | this whole flow run on a public site, mistakes included |
| `results/` | every run behind every number, with quarantined runs kept and labelled |
| `reproduce.py` | re-derives the deterministic numbers: no model, no credentials |

If you re-run this and get different numbers, that is the most useful thing you
can send.
