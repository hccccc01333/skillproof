# dsh-show2skill

Record a GUI demonstration once, induce a reusable skill from it, install the
skill into the harness.

```bash
dsh plugin --profile web add github:<you>/show2skill#<sha>
# or from a local checkout:
dsh plugin --profile web add ./show2skill
```

## What it actually claims

This plugin is written to the measurements, not to the pitch. The measurements
say two things that shape it:

**A recording is very strong on the page it was recorded from.** Replay the
recorded actions verbatim and you score 100/100 on the demonstrated page. No
method that learns from the recording can beat that there — at best it ties.
So a plugin that said "record once, automate anything" would be overselling
something the numbers contradict on the first page.

**A skill is very strong on a page that moved.** On the same application after a
UI revision that also drops the test hooks, the recording scores 25/100. An
induced skill with a completion verifier scores 100/100, three runs out of
three.

**And a skill cannot learn a rule that is not legible in the data.** On a task
whose decisive rule existed only as a difference between the demonstration's
input and its output, the induced skill scored exactly what no skill at all
scored — 35/100, identical wrong output.

**So the plugin asks.** The induction reconciles what the demonstration produced
against what it consumed and must name any difference its own rules cannot
explain. It then puts that to you. On that task, one answered question took the
score from 35 to 100. The question is specific — not "how does this work" but
"these two rows were excluded, the only field distinguishing them is X, is the
rule about X or something broader?" — and it does not require you to phrase
anything carefully; a rambling spoken answer works as well as a written one.

The value here is not unattended automation. It is that the induction tells you
precisely where it is stuck, and your answer becomes reusable.

## Tools

| tool | what it does |
|---|---|
| `show2skill_record` | Record a demonstration and package it as an episode |
| `show2skill_induce` | Induce a skill + completion verifier, and install it |
| `show2skill_replay` | Replay the recording as a macro baseline and report its score |

## Configuration

Set under the plugin's config key in your profile:

```yaml
show2skill:
  projectRoot: /path/to/show2skill   # the Python pipeline
  python: python                      # interpreter with the deps installed
  episodesDir: ''                     # default <projectRoot>/episodes
  skillsDir: ''                       # default ~/.dsh/skills
  askHuman: true                      # ask when the induction cannot tell
```

`show2skill` shells out to a Python pipeline. That is a real dependency and it
is worth stating plainly: this is a front end, not a reimplementation.

## The skill format

The induced artifact is a plain `SKILL.md` with YAML frontmatter, which the
harness already reads natively, so installation is a file copy. The completion
verifier travels beside it as `verify.json` — a small set of machine-checkable
assertions the execution agent must pass before it may declare the task
finished.

## Status

**The pipeline is tested end to end; this wrapper is not.**

`python reproduce.py` verifies the headline result in 11 seconds with no model
and no credentials. The plugin wrapper is written against the documented plugin
API and its contract is checked (it loads, exports `name`/`inject`/`Config`, and
registers its three tools against a stub context) — but it has not been run
inside a live harness. Treat it as a starting point that needs a real
installation to shake out.

## What is not here

No marketplace listing, no icon, no UI panel. The question the induction asks is
surfaced through `ctx.ui.notify` if the harness provides one; a real UI for
answering it is the obvious next piece of work and the piece this plugin most
needs.
