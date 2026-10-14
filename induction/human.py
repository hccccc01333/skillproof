"""A scripted stand-in for the person who gave the demonstration.

`ask_human` is a product affordance: the induction cannot derive a rule that
lives only in the demonstrator's head, so it asks, and the plugin surfaces the
question. Testing that path needs somebody on the other end, and for a
repeatable experiment that somebody has to be scripted.

This is a keyword-matched knowledge base, deliberately transparent: every
answer is a rule the demonstrator knows, written out, and the match is visible
in the transcript. It is not a model and does not try to be one — the claim
under test is whether an induction can *use* a rule once it is told, not
whether a human can phrase one.

An answerer that silently volunteers more than it was asked would make the
experiment meaningless, so the first matching rule wins and nothing else is
added.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class ScriptedHuman:
    def __init__(self, rules: list[dict], *, verbose: bool = False) -> None:
        self.rules = rules
        self.verbose = verbose
        self.calls: list[dict] = []

    @classmethod
    def load(cls, path: Path, *, verbose: bool = False) -> "ScriptedHuman":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rules = data.get("rules") if isinstance(data, dict) else data
        if not isinstance(rules, list):
            raise ValueError(f"{path}: expected a 'rules' list")
        return cls(rules, verbose=verbose)

    def __call__(self, question: str) -> str:
        q = (question or "").lower()
        for rule in self.rules:
            terms = [t.lower() for t in rule.get("match", [])]
            if any(re.search(rf"\b{re.escape(t)}", q) for t in terms):
                answer = rule["answer"]
                self.calls.append({"question": question, "matched": terms, "answer": answer})
                if self.verbose:
                    print(f"    [human] matched {terms} -> {answer[:90]}")
                return answer
        self.calls.append({"question": question, "matched": None, "answer": None})
        if self.verbose:
            print(f"    [human] no rule matched: {question[:90]}")
        return (
            "I don't have a rule for that. Work from what the demonstration shows "
            "and declare anything you cannot establish."
        )


def interactive(prompt_stream=None, answer_stream=None, *, timeout_s: float | None = None):
    """Put each question to a person on stdin and return what they type.

    This is the plugin's actual interaction, not a test double. It differs from
    `ScriptedHuman` in the way that matters for a product: the answer is whatever
    the person happens to say, in whatever words they happen to use, and the
    induction has to cope with that rather than with a curated sentence.

    Blank input, EOF, or a timeout all mean "no answer", and the induction is
    told so rather than being handed an empty string it might mistake for
    guidance.
    """
    import sys

    out = prompt_stream or sys.stdout
    inp = answer_stream or sys.stdin

    def ask(question: str) -> str:
        print("\n" + "=" * 72, file=out)
        print("The skill induction has a question:", file=out)
        print("=" * 72, file=out)
        print(question.strip(), file=out)
        print("-" * 72, file=out)
        print("Answer in your own words (blank line = skip):", file=out)
        try:
            line = inp.readline()
        except (EOFError, KeyboardInterrupt):
            line = ""
        if not line:
            print("(no answer given)", file=out)
            return (
                "The person did not answer. Do not invent a rule to cover the gap: "
                "state an observable conditional check or declare it as unverifiable."
            )
        answer = line.strip()
        if not answer:
            print("(skipped)", file=out)
            return (
                "The person skipped the question. Do not invent a rule to cover the "
                "gap: state an observable conditional check or declare it as unverifiable."
            )
        return answer

    return ask
