# Results: 5-day validation

**Verdict: the pipeline works end to end, and the headline claim does not
survive contact with a cheap baseline.** A recorded macro scores a perfect 100
on the demonstrated task, which is the only condition where the induced skill
was actually measured. The experiment that would decide the question — a
correctly perturbed page — was not completed, for two reasons, one of which is
a design bug I introduced.

Everything below distinguishes what was measured from what was not.

## What is measured, and what was thrown away

| data | status |
|---|---|
| Agent conditions on `default` (2 conditions × 3 reps) | **clean, used** |
| Macro replay, all variants (deterministic, no model) | **clean, used** |
| Agent conditions on `jitter` (2 × 3) | **discarded** — instruction/page mismatch |
| Agent conditions on `jitter-remap` (3) | **discarded** — API account overdrawn mid-run |

Quarantined results are in `results/_invalid/` with the reason in the filename,
not deleted, so the exclusion can be audited.

The `jitter-remap` runs initially looked like a spectacular result — 15.00 three
times, exactly the do-nothing floor. They were not a result at all: the model
endpoint returned `AccountOverdueError` on step 2, the harness recorded the
abort, and the agent's inaction scored the floor. Three identical numbers from a
stochastic agent should always be checked before they are believed.

## Results

Deterministic baselines, no model involved:

| condition | Score | SR | note |
|---|---|---|---|
| macro on `default` (demonstrated page) | **100.00** | **100** | replaying the recording verbatim |
| macro on `jitter` (values changed) | 70.00 | 0 | |
| macro on `jitter-remap` (receipt ids reissued) | 35.00 | 0 | |
| macro on `jitter-nostid` (no stable hooks) | 35.00 | 0 | |
| *do-nothing floor* | 15.00 | 0 | |

Agent conditions, `default` only, N=3:

| condition | scores | mean | SR | tokens | steps |
|---|---|---|---|---|---|
| original agent (no skill) | 70, 85, 85 | 80.0 | 0 % | 174,581 | 19.3 |
| agent + induced skill | 85, 100, 100 | **95.0** | **67 %** | 165,782 | 18.3 |

## Findings

### 1. The induced skill works on the page it was recorded from

+15.0 mean points and success rate 0 % → 67 %. The gain is concentrated in
exactly two criteria, both about completeness rather than cleverness:

| criterion | no-skill | skill |
|---|---|---|
| R3 cost center correct | 1 / 3 | **3 / 3** |
| R6 line total matches the receipts | 2 / 3 | **3 / 3** |
| R4 all three trip receipts attached | 3 / 3 | 3 / 3 |
| R5 no non-trip receipt attached | 2 / 3 | 2 / 3 |

The skill made the agent enumerate all three receipts and all three lines
instead of stopping after the first. That is a real effect and it is the effect
the paper reports.

### 2. But the recording already gets 100, and it costs nothing

This is the finding that matters. A fixed macro replaying the recorded action
sequence scores **100.00 with SR 100** on the demonstrated page — better than
the skill-equipped agent's 95.0 mean, at zero inference cost and zero tokens.

So on the demonstrated task, induction loses. Not narrowly: it is beaten by the
cheapest possible alternative. The paper's headline comparison is against No
Skill, which scores 80 here, and against that baseline the result looks like a
win. Adding the macro shows the win is against the wrong opponent.

The case for induction therefore rests entirely on conditions where the macro
fails, and those conditions were not successfully measured.

### 3. No cost penalty at this scale — contrary to the paper

The paper reports induction token usage roughly twice its baselines (334.5k vs
170.7k on GPT-5.5/MyPCBench) and more execution steps than No Skill for one of
four models. Here the skill condition used *fewer* tokens (165.8k vs 174.6k) and
*fewer* steps (18.3 vs 19.3) than the baseline.

This is one task and N=3, so it is not a refutation; it is a reason to keep
measuring cost rather than assuming the paper's direction. Induction cost on
this episode was 158k prompt tokens and 91 seconds, in 13 turns.

### 4. The induction captured the procedure and missed the judgement

The generated skill is genuinely good. It has semantic targets and no
coordinates, it preserves the phase order, it carries the cost-center recovery
branch, and — importantly for perturbation — it says "enter the amount **from
the receipt**" rather than hardcoding 412.80. It was written in 13 turns.

What it does not contain is the rule for deciding **which receipts belong**:

> In the "RECEIPT INBOX" section, find the receipts relevant to the travel
> claim. For each relevant receipt, click the "Attach" button next to it.
> Leave non-travel-related receipts unattached.

"Relevant" is doing all the work and none of it is explained. The demonstration
plainly showed the answer — three receipts attached, two deliberately left
alone, with an explicit `observe` action recording the exclusion — but the
policy's instruction to retain "selection rules" was not enough to make the
model write one down.

This is the single most valuable piece of procedural knowledge in the task, and
it is the one that got dropped. It is also why the perturbation experiment
matters: on the demonstrated page, the executor can pattern-match against a
page it has effectively seen. Only a changed page forces the selection rule to
be explicit.

### 5. Two design bugs in my own setup, both found and fixed

**The perturbation made the task impossible.** `jitter` renamed the claim to
"April 2026" but left the instruction asking for the "March 2026" claim. One
agent correctly reported that no March claim existed and stopped — and scored
the do-nothing floor for being right. The paper revises task instructions
alongside the data ("All 64 task instructions are revised"); skipping that step
turns a perturbation into an impossibility. Fixed: instructions are now
per-variant. All six affected runs are discarded.

**The perturbation flattered the macro.** `jitter` changed amounts and dates but
left receipt identifiers stable, so the macro satisfied the two
receipt-selection criteria (R4 and R5, 35 points of its 70) simply by replaying
recorded ids. Adding `jitter-remap`, which reissues the identifiers while
leaving every visible label, vendor and amount untouched, drops the macro from
70.00 to 35.00. The 35-point gap was an artifact.

That second bug is the more instructive one, because it is the direction of
error a reproduction is most likely to miss: it made the *baseline* look good,
which is exactly the failure a project motivated by "is this method actually
worth it" should be least willing to accept. The rubric no longer references
receipt identifiers at all; it classifies by role in the task, read from the
variant seed.

## Addendum: a re-parameterizing macro beats the induced skill

Added after the main writeup. This is the strongest result in the project and it
changes the conclusion.

The verbatim macro loses 30 points on `jitter` for one reason: it writes values
that were correct during recording and are stale now. That is mechanical. So I
built the cheapest thing that fixes it — replay the recorded *structure*, but
re-read field values from the live page — and measured how far it gets.

The readers are nine lines of JavaScript: one reads the cost center out of the
header readout, one reads a receipt's amount from the receipt row. Values with
no reader fall back to the recorded literal, and target *selection* is still
taken from the recording. Nothing here understands the task.

| condition | `default` | `jitter` | `jitter-remap` | `jitter-nostid` |
|---|---|---|---|---|
| macro, verbatim replay | 100.00 · SR 100 | 70.00 · SR 0 | 35.00 · SR 0 | 35.00 · SR 0 |
| **macro, re-parameterized** | **100.00 · SR 100** | **100.00 · SR 100** | 65.00 · SR 0 | 50.00 · SR 0 |
| original agent (N=3) | 80.0 · SR 0 % | not measured | not measured | not measured |
| agent + induced skill (N=3) | 95.0 · SR 67 % | not measured | not measured | not measured |

The re-parameterized macro **fully recovers the changed-page loss** — 70 → 100,
SR 0 → 100 — and it beats the induced skill everywhere both were measured,
including on the demonstrated page (100 vs 95.0). It uses no model, no tokens,
and runs in seconds.

Verified by inspection of the replayed values rather than by the score alone:
on `jitter`, step 6 typed `538.20` where the recording says `412.80`, and step
18 typed `CC-5120` where the recording says `CC-4471`, both read from the live
page. The claim total came out at 837.90, matching the changed receipts exactly.

### What this locates precisely

The re-parameterized macro fails in exactly one place, and it fails there on
every variant where the question is actually asked:

| variant | what it scores | what it loses |
|---|---|---|
| `jitter` | 100.00 · SR 100 | nothing — receipt ids are stable, so replay satisfies selection |
| `jitter-remap` | 65.00 | R4: three buttons named "Attach", no way to tell which receipt is which |
| `jitter-nostid` | 50.00 | R1 + R4: same ambiguity, without test hooks |

Every failure, in every method, on every variant, is the same failure:
**choosing which target to act on when the choice requires understanding the
task.** Not structure, not ordering, not values, not completion checks — those
are all mechanical, and a script gets them for free.

The scope of that residual is narrow and worth stating plainly. The
re-parameterized macro is ~90 lines with two hand-written readers that a person
wrote after looking at the page. The induced skill cost 158k prompt tokens and
13 agent turns, and lost to it. Whatever induction is buying, it is not the
mechanical part of the problem, and the paper's evaluations never separate the
two because they never measure a non-inductive alternative that does the
mechanical part.

### The honest caveat about this baseline

The two readers were hand-written by someone who had already seen the page. That
is a real limitation and it does not generalize: a new application needs new
readers, and writing them requires exactly the task understanding that induction
is supposed to supply.

But that cuts both ways, and it is the point of the measurement. If
hand-writing two rules for one application beats an LLM induction pipeline,
then the pipeline is not competing on the mechanical work — it can only be
competing on the judgement work, which it demonstrably failed to capture here
(the skill's rule for which receipts belong is the word "relevant"). The
project's question is therefore no longer "does induction beat no-skill" but
**"can induction learn a selection rule"**, and that question is now measurable.

## Addendum 2: the full perturbation ladder, and where the moat actually is

Six variants, both deterministic baselines, no model involved:

| condition | what changed | macro, verbatim | macro, re-parameterized |
|---|---|---|---|
| `default` | nothing — the demonstrated page | 100.00 · SR 100 | **100.00 · SR 100** |
| `jitter` | values (amounts, dates, cost center) | 70.00 · SR 0 | **100.00 · SR 100** |
| `relayout` | values + UI revision, hooks kept | 70.00 · SR 0 | **100.00 · SR 100** |
| `jitter-remap` | values + receipt identity reissued | 35.00 · SR 0 | 65.00 · SR 0 |
| `jitter-nostid` | values + no test hooks | 35.00 · SR 0 | 50.00 · SR 0 |
| `relayout-nostid` | values + UI revision + no hooks | 25.00 · SR 0 | **25.00 · SR 0** |
| *do-nothing floor* | — | 15.00 · SR 0 | 15.00 · SR 0 |

Three findings, in order of how much they change the picture.

### 1. A UI revision alone is survivable; losing the hooks with it is not

`relayout` changes section order, relabels every control, and regroups the
fields — and the re-parameterized macro still scores 100.00 with SR 100. It
falls through to CSS paths 9 times, and those paths encode the test hooks, so
it lands on the right elements without understanding anything.

`relayout-nostid` removes the hooks as well, and both baselines collapse to
25.00 with 11 of 19 resolutions failing. That is barely above doing nothing at
all (15.00).

This is the honest version of "the page changed". A site you do not control
does not promise you `data-testid` attributes through a revision, so a
recording that depends on them is a recording with a shelf life. The number to
beat is **25.00**, and it is beatable: the executor sees a list of the current
page's controls by role and accessible name, so an agent that reads "Add to
claim" and concludes that is what used to be "Attach" can act where a CSS path
cannot.

### 2. Every failure in every method is the same failure

Across six variants and two baselines, there is exactly one failure mode:
**choosing which target to act on, when choosing requires understanding the
task.**

- `jitter-remap`: three buttons, no way to tell which receipt is which.
- `jitter-nostid`, `relayout-nostid`: same, plus relabelled controls the
  recorder's vocabulary no longer matches.
- The induced skill: captured the whole procedure and reduced the actual
  decision to the word "relevant".

Structure, ordering, values, and completion checks are all mechanical, and a
script gets them for free. Target selection is not, and nothing here does it.

### 3. Self-reported completion is mostly wrong

Across all six executed runs in the clean `default` cells, every agent declared
the task finished. Four of the six were wrong:

| run | declared | score | verdict |
|---|---|---|---|
| no-skill r1 | done | 70 | false confidence |
| no-skill r2 | done | 85 | false confidence |
| no-skill r3 | done | 85 | false confidence |
| skill r1 | done | 100 | correct |
| skill r2 | done | 85 | false confidence |
| skill r3 | done | 100 | correct |

**4 of 6 declarations (67%) were wrong**, including one run with the induced
skill. Every false one used language like "successfully submitted" and
"pending approval" — the one check the skill does generate, and the one that
happens to pass while the claim is missing two receipts.

This is not captured by any score in the paper's tables, and it is the most
commercially and scientifically useful thing in this document: a skill that
carries its own completion check is worth more than a skill that carries a
better procedure, because the procedure can be verified after the fact and the
false claim cannot.

## Addendum 3: the decisive cell, and the thesis holds

The single most important measurement in this project, and the one that was
blocked the longest. `relayout-nostid` is the honest version of the product
demo's "换新数据、调整页面布局": the data is different, every control has been
relabelled, the sections have been reordered, and the test hooks a recording
would have leaned on are gone. It is the condition where a recorded macro has
nothing left to hold onto.

Endpoint: OpenCode Go (`deepseek-v4.1-flash`), graphical executor with a
DOM-derived element list, 25-step budget, 3 repetitions per condition.

| condition | scores | mean | SR |
|---|---|---|---|
| original agent (no skill) | 45, 60, 60 | 55.0 | 0 % |
| **agent + induced skill** | **70, 70, 70** | **70.0** | 0 % |
| fixed macro, re-parameterized | 25.0 | 25.0 | 0 % |
| *do-nothing floor* | 15.0 | 15.0 | 0 % |

All six agent runs completed with zero endpoint errors.

**The induced skill transfers.** On a page whose vocabulary no longer matches the
recording, it beats the original agent by 15.0 points and the best non-inductive
baseline by 45.0. It also cuts variance sharply — 70.0 three times, against
45/60/60 for the unguided agent. Whatever else is true, a skill induced from one
demonstration does carry something across a UI revision that neither a recording
nor an unaided agent carries.

Per criterion, the gain is concentrated in exactly two places:

| criterion | no-skill | skill |
|---|---|---|
| R1 reached the approval queue | 3 / 3 | 3 / 3 |
| R2 category is a travel category | 3 / 3 | 3 / 3 |
| R3 cost center correct | 2 / 3 | **3 / 3** |
| R4 all three trip receipts attached | 3 / 3 | 3 / 3 |
| R5 no non-trip receipt attached | 0 / 3 | **0 / 3** |
| R6 line total matches the receipts | 0 / 3 | **0 / 3** |
| R7 total exceeds the threshold | 0 / 3 | **3 / 3** |

### What the skill fixed, and what it did not

It fixed **completeness**: the cost center gets filled, the total ends up over
the threshold, the required steps all happen. That is the bulk of the value and
it is exactly what the paper reports.

It did not fix **selection**. R5 is 0 of 3 in both conditions — neither the
skilled nor the unskilled agent ever correctly excluded the non-trip receipts,
and R6 fails for the same reason. Nobody reaches full credit. The skill's
instruction here is still "find the receipts relevant to the travel claim",
which is the word "relevant" doing all the work, as it has been throughout.

So the honest summary of the whole project:

> Induction transfers procedure across a UI revision, and does not transfer
> judgement. On this task, procedure is worth 15 points over an unaided agent
> and 45 over a recording; judgement is worth the remaining 30 and is currently
> worth zero from every method.

That is a much better position than "induction loses to a script", which is what
the earlier addenda concluded and what would have been reported had the
experiment stayed blocked. It is also still not a result that supports shipping
a general-purpose "record once, automate anything" plugin.

## A third harness bug, found by the same trap twice

The three runs of the skill condition that first came back at exactly 20.00 were
invalid — all three died at step 5 on an endpoint 400. The cause was mine: the
executor is a one-action-per-turn loop, but the model sometimes emits several
tool calls in a single message, and a loop that executes only `calls[0]` leaves
the other `tool_call_id`s unanswered. The API rejects that on the *next*
request, so the failure surfaces mid-episode and looks like the agent quitting.

Twice now, three identical scores from a stochastic agent turned out to be an
aborted run rather than a result. The first time it was an overdrawn account;
this time it was a transcript-validation error. Both were caught only because
identical numbers prompted a check. That check should be automatic: any run
whose `errors` list is non-empty, or which produces a suspiciously round and
identical score, should be quarantined before it reaches a table.

Fixed with `parallel_tool_calls=False` plus defensive tool messages for any
extra calls, and the three invalid runs are in `results/_invalid/`.

## Addendum 4: generated completion verifiers

The paper's `finalize_extraction` states plainly that it validates output
structure and tool use, and does **not** verify that a skill is correct or that
a task succeeded. Nothing in that pipeline can distinguish a finished task from
one that merely looks finished — which is how 67% of the completed runs measured
here came to declare success while scoring 70-85.

A verifier is the missing artifact: assertions that travel with the skill and
that the execution agent must pass before it may declare completion.

### Design

Assertions are deliberately few and deliberately observable:

| type | meaning |
|---|---|
| `text_present` | a string appears in the page's visible text |
| `text_absent` | a string does not appear |
| `text_count_at_least` | a string appears at least N times |
| `element_present` | an interactive control with a matching accessible name exists |
| `unverifiable` | declares a gap; never fails, reported separately |

The hard constraint is that a verifier may only inspect what the agent can see
for itself. Reading the application's own state endpoint would be an oracle: it
would turn "verify your work" into "ask the grader", and a skill carrying one
would be cheating rather than verifying.

The gate is real. `done` is rejected while the verifier fails, and the rejection
counts as a `done_rejection`, which is the direct measure of how much false
confidence was removed.

### Three ways a generated verifier fails, measured not hypothesised

The first generated verifier for this task had four assertions:

```json
{"id":"A1","type":"text_present","value":"Pending approval"}
{"id":"A2","type":"text_present","value":"Claim submitted for approval"}
{"id":"A3","type":"text_present","value":"March 2026"}
{"id":"A4","type":"unverifiable","description":"cannot bind the status to a claim row"}
```

It looks reasonable and it is broken three separate ways. Only the first was
caught by the validator.

**1. A gap written as a check makes the task impossible.** Earlier drafts
expressed the blind spot as `{"type":"text_present","value":"UNVERIFIED: ..."}`
— a check for the literal string `UNVERIFIED: ...`. That can never pass, so the
gate could never open and the agent could never stop, however correct its work
was. Fixed by giving gaps their own type that carries no value and never blocks,
and by rejecting the prose form in *both* validators. The generator now repairs
itself: attempt 1 was rejected for exactly this, attempt 2 was accepted.

**2. The verifier hardcodes the episode.** `A3` asserts `"March 2026"`, the
demonstrated claim's period. Correct on the demonstrated page; a *correct* run
on the revised page reads "April 2026" and fails. Not caught by anything — no
validator can tell a legitimate string from a stale one.

**3. It asserts transient feedback as a completion condition.** `A2` looks for
`"Claim submitted for approval"`, which is the confirmation *toast*. The toast
hides itself after 3.2 seconds. So A2 is true at the instant of submission and
false forever after, and any verifier that gates on it makes the task
unfinishable **on the demonstrated page, with no perturbation at all**.

### What mode 3 did to the runs

| run | score | SR | declared done | verifier runs | done rejected | failing |
|---|---|---|---|---|---|---|
| `default` r1 | **100** | **100** | no | 4 | 1 | A2 |
| `default` r2 | **100** | **100** | no | 2 | 0 | A2 |
| `default` r3 | 70 | 0 | no | 1 | 0 | A2 |

Both r1 and r2 completed the task perfectly — 100/100, full credit — and could
not finish, because `done` was gated on an assertion that had already become
false. Trajectory r1 shows the agent correctly running the verifier four times,
watching A1 flip from FAIL to PASS as its work landed, and then being stopped by
A2 until the step budget ran out.

**The score says the task succeeded while the agent was unable to finish.** A
score-only analysis misses this entirely; only `finished` and `done_rejections`
show it. It is the exact inverse of the false-confidence problem the verifier
was built to solve: bad verification does not make an agent lie, it makes an
agent unable to stop.

### The product consequence

A completion verifier is useful only if its assertions are about **persistent,
meaningful** state. Otherwise it is worse than no verifier, because an agent
with no verifier stops when it thinks it is done and an agent with a broken one
never stops at all.

That gives three requirements, all of which the current generator violates at
least once:

1. **Persistent, not transient.** Assert durable state, never a notification,
   toast, or animation.
2. **Task-derived, not episode-derived.** Assert what the task requires, never
   the values the demonstration happened to carry.
3. **Honest about its gaps.** Anything unchecked must be declared as unmatched,
   not approximated by a weaker check.

None of the three is enforced by the assertion language as written, and the
practical fix is probably to shrink what a verifier may claim rather than to
grow the language: fewer assertion types, each one only able to reference
*persistent* observable state, would have made A2 inexpressible and A3 awkward.

### The verifier's net effect on the two measured variants

Matched step budget (25), three repetitions, same model throughout.

| condition | `default` | `relayout-nostid` | declared done |
|---|---|---|---|
| original agent | 58.3 (2 / 3) | 55.0 (3 / 3) | mostly yes |
| agent + skill | 70.0 (1 / 1) | 70.0 (3 / 3) | yes |
| **agent + skill + verifier** | **90.0** | **75.0** | **0 / 3 and 0 / 3** |
| macro, re-parameterized | 100.00 | 25.0 | n/a |

Two things are true at once and pull in opposite directions.

**The verifier improves the work.** On the revised page it lifts the score from
70.0 to 75.0, because `done` is refused and the agent goes back to look for what
it missed. Refusing a premature completion is exactly the behaviour the artifact
exists to produce, and it works.

**The verifier prevents completion.** Every one of the six runs ended with
`finished = False`. On `default` the blocker is A2's transient toast; on
`relayout-nostid` it is A3's `"March 2026"`, which is simply false on the April
page. The agent is told, correctly by its own instructions, that the task is not
finished, and it is right to keep going until the budget runs out.

So the honest summary is that the verifier machinery is sound and the verifiers
are not. A gate that cannot open is worse than no gate: an agent with no
verifier at least stops.

### Why this is the hard part, and therefore the interesting one

It would be easy to read the table above as "verifiers don't work". The
opposite is closer to the truth: **verification is the only part of this
pipeline where getting it wrong does not degrade gracefully.**

- A weak skill still helps. The induced skill here is vague about which
  receipts belong and still moves the score 15 points over the unaided agent.
- A weak verifier makes the task unfinishable. Two runs completed the task to
  full credit and could not stop.

That asymmetry is the argument for doing this properly rather than shipping
"skill plus a few string checks". The three requirements — persistent not
transient, task-derived not episode-derived, honest about its gaps — are
enforceable in principle and were violated by the first artifact produced here
in three separate ways. Getting them enforced is a real piece of work, and it
is work the paper does not attempt at all.

## Addendum 5: the result

A second induction, after the evidence pipeline was fixed, produced a materially
better skill. Measured against every other condition, on the condition that
matters:

| condition | `default` | `relayout-nostid` | declared done |
|---|---|---|---|
| original agent | 58.3 (2/3) | 55.0 (3/3) | mostly yes |
| agent + skill (first induction) | 70.0 | 70.0 (3/3) | yes |
| agent + skill + verifier (broken verifier) | 90.0 | 75.0 | **0/3, 0/3** |
| **agent + skill + verifier (this induction)** | **100.0 · SR 100 (3/3)** | **100.0 · SR 100** | **yes** |
| macro, re-parameterized | 100.00 | 25.0 | n/a |
| do-nothing floor | 15.00 | 15.00 | n/a |

Full credit on both the demonstrated page and the revised page with the hooks
removed. On the demonstrated page that ties the recording, which was already
perfect; on the revised page it beats the best non-inductive baseline by 75
points.

### The criterion that changed

R5 asks whether the non-trip receipts were left off. Across every condition
measured before this induction — seven conditions, eleven runs — it passed
exactly once, by luck:

| condition | `default` | `relayout-nostid` |
|---|---|---|
| original agent | 1 / 3 | 0 / 3 |
| agent + skill (first induction) | 0 / 1 | 0 / 3 |
| agent + skill + verifier (broken) | — | 0 / 1 |
| **agent + skill + verifier (this induction)** | **3 / 3** | **2 / 2** |

The first skill reduced the whole decision to the word "relevant" and every run
that used it attached the personal hotel upgrade or the team dinner. This skill
states the rule:

> attach it when both conditions hold: its date falls inside the claim period,
> and it is a business travel expense of the trip this claim covers (airfare,
> lodging, ground/rail transport). Leave a receipt unattached when its title or
> merchant marks it as personal spending (a title containing `Personal`) or when
> it belongs to a different expense category such as meals and entertainment.

That is the judgement, written down, and it is the difference between 70 and
100. It also parameterizes the claim period rather than hardcoding "March 2026",
and says explicitly to read receipt titles and amounts off the page rather than
reuse recorded ones — which is why it survives the revised page at all.

### The verifier that made it finishable

The second generated verifier has seven assertions and none of the three
failure modes:

| | assertion | type |
|---|---|---|
| A1 | `Pending approval` present | persistent state |
| A2 | `Submitted to` present | persistent post-submission footer |
| A3 | `This claim cannot be submitted yet` absent | no blocker remaining |
| A4 | `Confirm submission` absent | no dialog left open |
| A5 | receipts and lines exactly correct | **declared gap** |
| A6 | total equals the attached receipts | **declared gap** |
| A7 | cost center matches the signed-in user | **declared gap** |

No transient toast, no episode-specific value, and the three gaps it declares
are precisely the three things every earlier condition got wrong. It is honest
about exactly the part it cannot check, which is the property the first verifier
lacked and the reason that one made the task unfinishable.

### What can and cannot be attributed

Between the first induction and this one, two things changed: the authoring
policy gained the verifier requirement, and the evidence pipeline gained image
downscaling so the induction could actually finish and inspect the video. **Both
changed at once and this experiment does not separate them.** The plausible
reading — that being forced to write completion conditions made the model reason
harder about what "correct" means, and so notice the receipt rule — is a
hypothesis, not a result.

What is a result: a skill induced from one demonstration, with a verifier,
reaches full credit on a page whose data, labels, section order and test hooks
have all changed, where the recording it was induced from scores 25.

### The project's answer

> Induction transfers procedure **and** judgement, when the authoring policy
> forces the judgement to be stated and a verifier forces the result to be
> checked. A recording transfers neither, and loses 75 points the moment the
> page moves.

That is the claim the paper does not make, because it never measures the
recording, and it is the claim this project can now support with numbers.

## Addendum 6: a second task, and the boundary of the method

Task 1's result was strong enough to be suspicious: one task, designed by the
person running the experiment, whose judgement happened to be derivable from
receipt titles. So a second task was built with a different *shape* of
judgement, to ask whether the method transfers or whether it had learned one
task's rule.

**Task 2 — the reporting pipeline.** Open the Reports section, select a period,
download the period's expense lines as CSV, decide which rows count, aggregate
them by cost center, and write `report.json`. The judgement is a selection rule
over a table rather than a per-item decision.

Three rules decide which claims count, and none is stated in the instruction:

| rule | how it is visible |
|---|---|
| `status` must be `approved` | an explicit CSV column |
| `period` must match | an explicit CSV column |
| **`Meals & Entertainment` is reimbursed elsewhere** | **only as a difference between the input and the output** |

The demonstration names the five claims it leaves out and does not say why. The
report it produced is in the episode, next to the CSV it came from.

### Result

| condition | scores | mean | SR | R5 meals |
|---|---|---|---|---|
| original agent | 35.0, 35.0, 35.0 | 35.0 | 0 % | 0 / 3 |
| agent + induced skill + verifier | 35.0, 35.0, 35.0 | 35.0 | 0 % | 0 / 3 |
| *the demonstrated answer* | — | — | — | — |

**The skill changed nothing.** Both conditions produced the identical wrong
report — the same five claim ids, the same total of 1117.25, against the
demonstrated 1002.10 with three claims.

The induced skill is otherwise good work. It states the workflow, the export
schema, the recovery path, the output contract, and a verification procedure. It
also says this, in its own words:

> The task never states which claims count; that is the whole job. Decide it
> from the export's `status` column (rule in step 4), never from guesswork.

It saw that a judgement was required, correctly identified that `status` was
part of it, and stopped there.

### What this establishes

**The method transfers a rule that is legible as a column, and does not transfer
one that is only visible as a difference between the demonstration's input and
its output.** The evidence for the meals rule was present, unambiguous, and read
by the induction — the report file is in the episode and the agent opened it —
and it was still not used, because `status` was available and sufficient to
explain most of the difference.

That is a sharper boundary than "induction transfers procedure and not
judgement", which is what the previous addendum concluded. The distinction is
not procedure versus judgement. Task 1's rule was judgement too — "a title
containing `Personal`" is not a column — and it transferred. The distinction is
**whether the rule can be read off a field, or has to be inferred by
reconciling two artifacts**.

There is a second difference worth recording, because it may be the operative
one. Task 1's demonstration carried an observation caption reading "non-travel
receipts left unattached" — a hint about the *kind* of rule, with the specifics
left to be derived. Task 2's caption lists excluded ids and nothing else. The
induction that had a hint expanded it; the induction that had only ids took the
easiest rule that fit. **A demonstration that records what was done but not why
may not be enough, and the human's narration is load-bearing rather than
decorative.**

### The fix, implemented and not yet measured

The authoring policy now requires an explicit reconciliation step: read the
demonstrated output as carefully as the input, find which items were dropped,
identify what distinguishes them, and check that the stated rules account for
the *whole* difference — with the failure named, because a recorded run hit it:

> A recorded run of this harness produced a skill for a reporting task that
> decided which rows counted purely from the export's `status` column — correct
> as far as it went, and silent about the second rule the demonstration applied,
> because `status` was the most legible column in the file.

**This has not been measured.** The re-induction that would test it stalled on
the same provider flakiness that blocked earlier runs, and was stopped after
thirty-five minutes at iteration 10. Until it runs, the fix is a hypothesis with
a plausible mechanism and no evidence — which is exactly the standard this
document has been holding everything else to, so it is labelled as such rather
than counted as a result.

## Addendum 7: asking, and the fourth verifier failure

Addendum 6 ended with a rule the induction could not derive, a fix that was
implemented and unmeasured, and a note that the reconciliation fix was a
hypothesis. Both are now measured, and both work.

### The question

The authoring policy now requires reconciling the demonstrated output against
its input and accounting for the whole difference. Given that instruction, the
induction asked this, unprompted:

> In the demonstrated May 2026 report, the approved claims clm_3003 (client
> dinner) and clm_3006 (team coffee) were left out of claim_ids, while other
> approved claims were included. The only field that separates them is
> `category = "Meals & Entertainment"`. Is the counting rule "exclude the Meals
> & Entertainment category specifically", or is there a broader
> non-reimbursable-category policy in ExpenseDesk (and where is it stated) that
> I should encode instead?

It performed the diff, isolated the unexplained exclusion, identified the field
that distinguishes it, asked about the **rule** rather than the instance, and
asked whether the rule generalises beyond this episode. That is the question the
experiment was designed to elicit, and it was not scripted.

`ask_human` is the affordance behind it: a tool the induction may call, backed
by a person when one is attached and by a plain refusal when one is not — so a
run with no human must declare a gap rather than invent a rule.

### The result

| condition | scores | mean | SR | declared done |
|---|---|---|---|---|
| original agent | 35.0 ×3 | 35.0 | 0 % | yes |
| agent + skill (no human) | 35.0 ×3 | 35.0 | 0 % | yes |
| **agent + skill (one question answered) + verifier** | **100.0 ×3** | **100.0** | **100 %** | **yes** |

**One answered question takes the task from 35 to 100.** The assisted skill
states all three counting rules and adds a warning against the exact mistake the
unassisted induction made:

> Do not look for a single column that decides everything. `status` is the most
> legible field, but it is not sufficient: approved meals claims are still
> excluded, and period must be applied on top of it.

### The fourth verifier failure mode

The first verifier generated for the assisted skill had sixteen assertions and
could never pass. It looked for `claim_count`, `clm_3001` and `1002.1` in the
page's visible text — all of which live in `report.json`, a file. Six of them
"passed" vacuously, because the strings were absent from the page for the same
reason the task was correct.

That is the same error as the earlier three, in a new costume: **the verifier was
wrong about what it could see.** The assertion language only read the DOM, and
the deliverable of this task is a file.

Fixed by adding two file predicates — `file_exists` and `json_field_equals` —
and, more importantly, by telling the generator that there are **two surfaces**:
the page and the workspace. The model did not know a workspace existed; the
first attempt to fix this added the predicates but left the prompt saying "in
the workspace" without ever explaining what that was, and the verifier came back
just as broken. Naming the two surfaces explicitly fixed it in one pass.

### The four modes together

Every verifier failure in this project has been a variant of one error — the
verifier being wrong about its own reach:

| # | failure | consequence | caught by |
|---|---|---|---|
| 1 | a gap written as a check | gate can never open | validator, then self-repair |
| 2 | an episode value hardcoded | fails a correct run on changed data | nothing |
| 3 | transient feedback as a condition | unfinishable on the demonstrated page | nothing |
| 4 | a file asserted against page text | unfinishable, with vacuous passes | nothing |

Two of the four were found only by running the thing and reading the trajectory,
and both of those scored **100** while being unable to finish. A results table
without a `finished` column would have reported all of them as successes.

The practical conclusion is the one from Addendum 4, now with evidence: the
verifier is the part of this pipeline that fails silently and expensively, and
the fix is to narrow what it may claim rather than to grow the language.

### A fifth harness fault: two batches writing the same filenames

The first measurement of this cell was contaminated. Two batches were running
against the same output paths — one from before the verifier was corrected, one
from after — and the slower batch overwrote the faster one's results. The cell
read `100, 100, 100` while one of the three files had in fact used the old,
sixteen-assertion verifier and only reached full credit because the *evaluator*
scores the artifact, not the verifier.

It was caught by checking which assertions each run had actually used, not by
looking at the scores, which were identical. Re-run cleanly, the cell is
`100, 100, 100` with the four-assertion verifier and `finished = True` in all
three.

The lesson is the same one that has recurred throughout: **the score is not the
evidence.** Five distinct harness faults have now produced plausible-looking
numbers — an overdrawn account, a transcript-validation error, a step-budget
mismatch, a silent truncation, and this filename collision — and every one was
caught by reading the run rather than the score.

## Addendum 8: does the interaction survive a real person

Addendum 7 measured the question with a curated answer: a clean, structured
sentence stating the rule. A real user does not talk like that. So the
interaction was made real — `ask_human` now reads stdin — and the experiment was
repeated with a demonstrator who answers the way people actually answer.

### The question, again, unprompted

> The demonstrated report counted clm_3001, clm_3002 and clm_3004, and excluded
> the two approved claims whose category is "Meals & Entertainment"... What rule
> excludes a category — is there a fixed set of non-reimbursable categories
> (with Meals & Entertainment as the only one in this period), or is the
> category filter decided some other way (a per-category cap, a claim title, an
> approval field not in the export)?

Different wording from Addendum 7's, same substance, and this time probing the
*shape* of the rule rather than its content — is this a fixed set, or a
mechanism? That is a better question than the one the previous run asked.

### The answer it got

> oh, a few different reasons there. the ones that aren't approved yet obviously
> don't count, we don't count anything until it's actually approved. the april
> one's just a different month, it'll be in its own report. and the food ones...
> yeah we never put those in the period report, they get handled somewhere else
> entirely. has been like that for as long as i've been here.

Unstructured, out of order, no category name quoted back, one trailing anecdote.
The skill it produced states all three rules precisely and in the right order,
and adds a warning the answer did not contain:

> Filtering on `status` alone (the most obvious column) still keeps approved
> meals claims in and inflates `claim_count`, `by_cost_center` and `grand_total`.
> Filtering on `status` and `category` alone still pulls in another month's
> claims if the export carries them.

| condition | scores | mean | SR | declared done |
|---|---|---|---|---|
| original agent | 35.0 ×3 | 35.0 | 0 % | 3/3 |
| + skill, no question | 35.0 ×3 | 35.0 | 0 % | 3/3 |
| + skill, curated answer | 100.0 ×3 | 100.0 | 100 % | 3/3 |
| **+ skill, casual answer** | **100.0 ×3** | **100.0** | **100 %** | **3/3** |

**A rambling answer works as well as a curated one.** The interaction does not
require the user to phrase anything carefully, which is the property a shipped
plugin needs — if it only worked on well-formed answers it would fail on
contact with a real person.

The generated verifier was also correct on the first attempt this time, using
file predicates throughout: the two-surfaces fix from Addendum 7 held.

### Known limitation in this verifier

`json_field_equals` for `claim_count` and `grand_total` carries the expected
values `3` and `1002.1` — correct for the May 2026 task as stated, and stale for
any other period. That is failure mode 2 from Addendum 7 in mild form, and it is
untested here because the report task has no period-perturbed variant. A report
task variant with a different period would settle it, and until then this
verifier is correct for exactly one instance.

### Not measured: what happens with nobody there

The degraded path — the induction asks, no person is attached, and it must
declare the gap instead of inventing a rule — was started and **not completed**.
It reached `ask_human` at iteration 7, received the refusal, and then stalled on
the provider at iteration 8 until it was stopped.

What is known is that it asks. Whether it then declares the gap honestly or
invents a rule to cover it is the open question, and it is the one that matters
most for a plugin that will often run unattended.

## Addendum 9: the verifier that made the agent write the wrong file

The plugin's flow was validated end to end for the first time — record by hand,
induce, install, run — and it worked, scoring 100/100 three times. It worked for
a reason that should not have been true.

The generated verifier asserted `file_exists` on **`workspace/report.json`**.
The task asks for `report.json`. The execution agent, being obedient, wrote the
file in **both** places: the path the task named and the path the verifier
named. It scored full marks and the verifier passed.

Had it written only the path the verifier named, the task would have failed
**while its own completion check reported success** — the exact inversion of the
problem the verifier exists to prevent, and strictly worse than having no
verifier at all.

### Where the prefix came from

`workspace/` was the directory the recorder packages a demonstration's saved
files into. It is a *packaging* detail of the episode. The induction read
`workspace/report.json`, concluded that was the deliverable path, and wrote it
into the verifier.

The name was the whole problem. Renamed to `produced/`, with the distinction
stated in the episode schema and in the authoring policy:

> That prefix is the episode's packaging, not part of the task's path. A task
> that writes `report.json` shows up as `produced/report.json`, and the
> deliverable is still `report.json`.

Re-recorded, re-induced, re-run: the verifier now names `report.json`, the agent
writes only `report.json`, and the three runs are unchanged at 100/100.

### Why this one is worth recording separately

The previous seven harness faults produced *wrong numbers*. This one produced
**right numbers from a wrong reason**, and it is the only one that could have
made a task fail while every check said it passed.

That is the failure mode a completion verifier is supposed to eliminate, and it
was introduced by the verifier itself. The lesson is not "be careful with paths"
— it is that **an execution agent obeys the verifier it is given**, so a
verifier is not a passive check. It is an instruction. Anything wrong in it
becomes part of the task, and the agent will bend its work to satisfy it.

This is the strongest argument yet for the position this document has taken
throughout: narrow what a verifier may claim. A verifier that could not name a
path would not have been able to make this mistake.

## Addendum 10: how many questions does it ask

The question that decides whether this is a product or a prototype. A user will
answer one or two questions. Nobody answers ten. Every measurement so far had
exactly one rule that a recording could not carry, so every run asked one
question — which says nothing about what happens when there are more.

So a second non-legible rule was added to the reporting task: a claim that is
approved, in period and in an ordinary category, and is excluded because it was
bought on a company card and never needed reimbursing. Nothing in the export
says so. The expected answer does not change, because the claim was never
counted — only the number of unexplained exclusions does.

### Result

| task | non-legible rules | original agent | skill + verifier | questions asked |
|---|---|---|---|---|
| `expense-report` | 1 (meals) | 35.0 | **100.0** | **1** |
| `expense-report-hard` | 2 (meals, already paid) | **20.0** | **100.0** | **2** |

**Two answered questions take the task from 20 to 100.** The count tracks the
number of rules the recording cannot carry, and nothing else.

### But the first run asked eight

Before anything was concluded, the same task was run once and asked **eight
questions across 25 turns**. That looks like a scaling failure and is not one.
Reading them:

- **Q1** was the right question: it identified both unexplained exclusions and
  asked about both at once.
- **Q2 through Q8 were the same question seven times**, in seven phrasings —
  "where in the app is that visible?", "which element shows it?", "does the UI
  display it?", "is there a payment-method field?".

The induction was looking for an **observable marker** for "already paid",
because a rule an agent can apply needs one. There is no such marker. The
person's answer said so without saying so — "i put that on the company card" —
and nothing told the induction that *no marker exists* is a complete answer, so
it kept asking.

That is a missing termination condition, not a scaling problem, and it is the
worst failure this interaction can have: seven questions that produced nothing
the first answer had not already given.

### The fix

The authoring policy now says it directly: a rule an agent can use needs an
observable test; some have none; **ask once**, and if the answer describes a
rule but names no visible marker, write the rule into the skill as a stated
limitation and stop.

Re-run: **two questions, fourteen turns, 100/100 three times.** The skill states
both rules, including

> **Not already paid** — the claim was not already settled outside this
> reimbursement run, for example a purchase paid on a company card.

and the verifier declares the gap rather than pretending to check it:

> `A7 unverifiable`: whether each excluded claim was excluded for the correct
> reason

### What this settles, and what it does not

**Settled:** the interaction scales with the work a recording cannot carry. Two
such rules cost two questions. That is inside what a person will tolerate.

**Not settled:** how many such rules a real workflow has. Two is what this
benchmark was built with. If an office workflow has eight — and the pattern of
this task suggests it easily could — then eight questions is the cost, and
whether that is acceptable is a question about the workflow, not about the
mechanism.

The honest summary is that the mechanism is not the bottleneck. **Finding out
how many judgement calls a real recurring task contains is**, and that needs a
real task rather than a designed one.

## What the corrected experiment requires

The decisive comparison is unmeasured. It needs:

1. Agent conditions re-run on `jitter` and `jitter-remap` with corrected
   per-variant instructions. **Blocked:** the API account used for these runs
   is overdrawn. Roughly 6 runs × ~5 minutes.
2. The macro re-measured on the same variants, which already works and needs no
   model.
3. More repetitions. N=3 gives a spread of 70–85 for the baseline on one cell;
   N=3 is not enough to separate conditions that differ by 15 points.

Until then, the honest statement is: **the pipeline is validated, the skill
helps on the demonstrated page, and the recording beats it there — so nothing
here yet justifies using induction over replaying a macro.**

## Reproducing

```bash
.venv/Scripts/python.exe tests/test_tools.py          # 21 tool-surface contracts
.venv/Scripts/python.exe run_sample.py                # record a demonstration
.venv/Scripts/python.exe run_macro.py --variant default
.venv/Scripts/python.exe run_macro.py --variant jitter
.venv/Scripts/python.exe run_macro.py --variant jitter-remap

# agent conditions (requires a model endpoint)
export S2S_INDUCT_BASE_URL=... S2S_INDUCT_API_KEY=... S2S_INDUCT_MODEL=...
.venv/Scripts/python.exe run_induct.py --episode expense-submit-default
.venv/Scripts/python.exe run_exec.py --condition no-skill --variant default --rep 1
.venv/Scripts/python.exe run_exec.py --condition skill    --variant default --rep 1
```
