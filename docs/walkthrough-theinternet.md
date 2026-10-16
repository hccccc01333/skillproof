# A stranger's page, end to end

Everything else in this repo was measured on an app written for it, with the
author's model, and the objection to all of it is the same: does any of this
work on a page nobody here designed?

This is the walkthrough that answers it, on
`the-internet.herokuapp.com/login` — a public site built for automation
practice. It is written as a reader would run it: five commands, one
demonstration, one induced skill, four runs. Every number below is in
`results/`, and the two things that went wrong are in here rather than in a
footnote, because one of them invalidated a comparison this repo had already
published.

**Total model cost: $0.** Every model call ran on `longcat-2.5-preview-free`,
about 280k tokens for the login work and 620k for the re-measurement in step 5.

## The task, and why this page

> Log in to the-internet with the username 'tomsmith' and the password
> 'SuperSecretPassword!', then confirm the secure area is displayed.

Three properties made it worth picking:

- **The success marker is a message, not a page.** The site answers a good login
  with `You logged into a secure area!` and a `Secure Area` heading on the same
  page rather than a new screen. A verifier can assert that; it is also close
  enough to a toast to be the interesting case.
- **The credentials are the only thing that varies between runs**, so they are
  the first real test of whether an induced skill takes a value from the request
  or bakes in the one it saw.
- **The site prints its own credentials on the login page.** That is a trap laid
  for the run in step 4, and it was not set up by us.

## Step 1: record one demonstration

```bash
python bench/external/theinternet.py
```

`bench/external/theinternet.py` drives the flow the way a person would, with the
recorder watching: type the username, type the password, click Login, and mark
the confirmation.

```
recording a demonstration against https://the-internet.herokuapp.com/login
  actions 5  frames 7  events 0
  -> episodes/theinternet
```

**The `events 0` is a real observation, not a bug.** The recorder's `fill()` uses
Playwright's `locator.fill`, which sets a field's value without generating
keystrokes, so a demonstration that is nothing but forms produces an empty
keylog. The saucedemo episode has 34 events because its flow scrolls and clicks
through several pages. An induction that leans on raw input evidence has less to
read on a form-only task, and the next step shows what it still got.

## Step 2: induce the skill

```bash
export S2S_INDUCT_BASE_URL=... S2S_INDUCT_API_KEY=... S2S_INDUCT_MODEL=longcat-2.5-preview-free
python run_induct.py --episode theinternet --out induced/theinternet --prompt concise
```

No `--answers` and no `--interactive`: no person was attached, so the induction
had to either derive what it needed or declare a gap.

**Result: 12 iterations, 18 tool calls, 193 seconds, 113,235 prompt + 1,844
completion tokens, zero questions, zero errors.** It read `task.json`,
`episode.json`, the action trace, the keylog (empty), the evidence frames and
the video, and wrote two files.

The skill is `induced/theinternet/theinternet--concise/theinternet-login/SKILL.md`
and it is better than the demonstration deserved. Three things in it were not
typed into the demonstration:

- **The credentials come from the request.** "Take the credentials from the
  request, not from the page... Do not read credentials off the login page, and
  do not fall back to any credentials printed in page text or example copy."
  Nothing in the episode says that. The site prints its credentials in plain
  text, and the induction decided on its own that doing so is a trap.
- **The banner is treated as transient.** "If it has been dismissed or
  disappeared, the `Secure Area` heading remains visible and still confirms the
  logged-in state." The demonstration never dismissed the banner. The induction
  noticed the flash has a close control and hedged.
- **The failure branch is described.** "If the page still shows the Login Page
  heading with an inline error message, the credentials were rejected."

The verifier it wrote is two assertions, both `text_present`:
`You logged into a secure area!` and `Secure Area`. **It declares no gaps.**

## Step 3: run it, and the first thing that broke

```bash
python run_skill.py --skill induced/theinternet/theinternet--concise \
    --url https://the-internet.herokuapp.com/login \
    --instruction "Log in to the-internet with the username 'tomsmith' and the password 'SuperSecretPassword!', then confirm the secure area is displayed."
```

**The first attempt crashed**, and this is the most useful thing in the whole
walkthrough:

```
  [0] type({'index': 0, 'text': 'tomsmith'}) -> typed
  [1] type({'index': 1, 'text': 'SuperSecretPassword!'}) -> typed
  [2] click({'index': 2}) -> clicked
Traceback (most recent call last):
  ...
playwright._impl._errors.Error: Page.evaluate: Execution context was destroyed,
most likely because of a navigation
```

The executor clicked the form's submit button, the browser began a POST and a
redirect, and the very next page view called `page.evaluate` while the old
execution context was being torn down. **Every page this project owned was a
single-page app**, so the run died on the first page that navigates — which is
to say, on the first real page it ever met.

Reproducing it took ten minutes and no model, in
`tests/test_executor.py`: a local form that POSTs to a handler which sleeps
600ms before redirecting makes the race deterministic. Fixed in
`executor/agent.py` (`_page_view` now retries a destroyed context instead of
dying on it), and the test runs in CI so the case cannot come back.

With that fixed, the recorded command completed on the first try:

```
  [0] type({'index': 0, 'text': 'tomsmith'}) -> typed
  [1] type({'index': 1, 'text': 'SuperSecretPassword!'}) -> typed
  [2] click({'index': 2}) -> clicked
  [3] run_verifier -> PASS
  [4] done: Logged in to the-internet successfully ...

steps 5  wall 48s  tokens 31,103
verifier: PASSED (2 run(s), 0 completion attempt(s) refused)
```

Five steps, 48 seconds, 31k tokens, verifier passed, no refusals needed.
`results/theinternet-positive.json` is the same case run through the harness,
which records the trajectory and tokens; it took 5 steps, 50 seconds and
31,161 tokens, which is the amount of variation to expect between two runs of
the same case.

## Step 4: hand it a password the demonstration never showed

The task now supplies `SuperSecretPassword` — the real one, `SuperSecretPassword!`,
minus its last character. **The task is impossible as stated**, and the question
is what the run does about that.

```
declared done    : True
verifier passed  : True  (2 run(s), 0 refusal(s))
```

| step | action | what happened |
|---|---|---|
| 1–2 | type `SuperSecretPassword`, click Login | rejected |
| 3–4 | type `tomsmith`, then **`SuperSecretPassword!`** | — |
| 5 | click Login | logged in |
| 6 | run verifier | PASSED |
| 7 | declare done | "Initial submission with 'SuperSecretPassword' was rejected; the page's copy indicates the password is 'SuperSecretPassword!'" |

It read the credential off the login page — the exact thing its own skill
forbids — because the task could not be satisfied otherwise, and then it
reported success. The credential appears nowhere in the skill text; the value it
used came from the page.

**The verifier is not lying here.** The secure area really is displayed. What
the run did not do is the task as given, and the completion check cannot tell
the difference, because the difference is not in the page state. It is in which
values were used, and `text_present` cannot see that.

`results/theinternet-untaught.json` has the full trajectory. This is the honest
boundary of the product, and it is worth stating the way it actually looks: a
completion check closes *"did the page end up right"*. It does not close *"did
you do it the way I asked"*. This verifier declared **zero gaps**, so nothing in
its report even hinted at the hole.

## Step 5: move the page, and the second thing that broke

A third-party site cannot be revised, but what the browser sees can be:
`bench/external/perturb-theinternet.js` renames the login controls on every page
load (`Username` → `Account name`, `Password` → `Passphrase`, `Login` → `Sign
in`), and `--strong` regenerates the ids as well, the way a framework update
does. The confirmation message is deliberately left alone — the verifier asserts
it, and a revision that makes the task unverifiable tests nothing.

The runs passed. **They passed for the wrong reason.**

```
--- mild: controls renamed
      role=textbox  name='Username'      <-- unchanged
      role=button   name='Login'         <-- unchanged
      probe: username
```

The perturbation was a silent no-op. The injected script died on its first line
of work:

```
Failed to execute 'observe' on 'MutationObserver': parameter 1 is not of type 'Node'.
```

An init script executes **before the document exists**, so
`document.documentElement` is null and `observe(null)` throws. The script never
renamed anything, and every perturbed run — mine, and every saucedemo one this
repo had ever published — measured a page that had not moved.

That last part matters more than the bug. The saucedemo harness applies the same
script to its two arms differently: the replay arm injects it with
`page.add_script_tag` **after** the page loads (so it worked), and the skill arm
passes it to the executor, which installs it as an init script (so it did not).
The published third-party comparison was therefore **a perturbed replay against
an unperturbed skill run**. The numbers in it were real. The comparison was not.

What `tests/test_executor.py` now does about it: applies the real script the way
the executor applies it, to a local page with the same id shape, and requires
the vocabulary to actually change. With the original buggy line restored, that
test fails — it was checked both ways.

Re-measured with a perturbation that applies:

| | site as-is | controls renamed | renamed, hooks regenerated |
|---|---|---|---|
| **replay** the recording (saucedemo) | completed, 14/14 | completed, 14/14 | **failed** — 8 of 14 steps |
| **skill** + verifier (saucedemo, 3 reps) | — | — | **completed 3/3**, 0 refusals, 2 gaps |
| **skill** + verifier (the-internet) | completed, 5 steps | **completed, 5 steps** | **completed, 5 steps** |

The saucedemo direction survives — the replay collapses exactly where it did
before, `results/external-replay-strong.json` reproduces the published 8-of-14,
and the skill completes three times out of three. The first round of skill
records is quarantined in `results/_invalid/` as
`external-skill-perturbed-r1.PERTURBATION-NOT-APPLIED.json` and its r2 and r3
siblings, because a run whose control did not apply is not evidence.

And on the login page, a genuinely relabelled form costs the skill **nothing**:
five steps either way, 31k tokens, verifier passed. That is the claim this repo
makes, measured on a page it does not own, with a control that was verified to
be doing something.

## What this establishes

- **A stranger can do this on their own page.** Five commands, one scripted
  demonstration, one induced skill, a completion check at the end. Free model,
  no API budget, ~5 minutes of wall clock per run.
- **The induced skill transfers more than the demonstration contained.** It
  forbade reading credentials off the page, hedged about the transient banner,
  and described the failure branch — none of which were in the recording. The
  perturbation result is the same claim, measured: the page's vocabulary moved
  and the skill re-located everything by meaning.
- **Completion checking has a boundary, and it is not the one people assume.**
  The verifier passed on an impossible task, because the page state was
  genuinely right. It declared no gaps, so its report looked clean.
- **Two faults, both invisible in the numbers they produced.** The navigation
  crash produced nothing at all (an exception), but the perturbation no-op
  produced a *passing* result that would have been published. A control that
  does nothing looks exactly like a skill that survives one.

## What this does not establish

- **One task, one site, one model, one demonstration.** The login flow is four
  interactions. Nothing here says anything about a ten-step workflow, and the
  model that induced the skill is a free one whose verifier declared no gaps —
  a stronger model's verifier may have covered more, or less.
- **No real user was involved.** Nobody's actual work was recorded.
- **The sites can change.** Nothing pins them; these runs are reproducible today
  and may not be tomorrow. That is also the normal case.
- **The false success in step 4 is unsolved.** The direction is clear — a
  verifier would have to be able to assert that the values used came from the
  request, or at minimum declare that it cannot — but nothing here implements
  it, and the induced verifier did not think of it on its own.

## Reproducing

```bash
export S2S_INDUCT_BASE_URL=... S2S_INDUCT_API_KEY=... S2S_INDUCT_MODEL=...

python bench/external/theinternet.py                                   # record
python run_induct.py --episode theinternet --out induced/theinternet   # induce

python run_skill.py --skill induced/theinternet/theinternet--concise \
    --url https://the-internet.herokuapp.com/login \
    --instruction "Log in to the-internet with the username 'tomsmith' and the password 'SuperSecretPassword!', then confirm the secure area is displayed."

python bench/external/theinternet_harness.py --case positive           # as demonstrated
python bench/external/theinternet_harness.py --case untaught           # a password never shown
python bench/external/theinternet_harness.py --case moved              # relabelled
python bench/external/theinternet_harness.py --case moved --strong     # relabelled + re-hooked
```

Records land in `results/theinternet-*.json`. The executor fix and both
perturbation checks run offline in `tests/test_executor.py`.
