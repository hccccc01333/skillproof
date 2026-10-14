"""Generated completion verifiers.

The paper's `finalize_extraction` states plainly that it checks output structure
and tool use, and does *not* verify that a skill is correct or that a task
succeeded. Nothing in that pipeline can tell a claim that succeeded from a
claim that looked like it did, which is why 67% of the completed runs measured
in this project declared success while scoring 70-85.

A verifier is the missing artifact: a small set of machine-checkable assertions
that travel with the skill, that the execution agent must run before it is
allowed to declare completion.

The hard constraint is that a verifier may only inspect what the agent can
observe for itself. Reading the application's own state endpoint would be an
oracle -- it would turn "verify your work" into "ask the grader", and a skill
carrying one would be cheating rather than verifying. Every predicate below
therefore evaluates against the rendered page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Assertion kinds. Deliberately few and deliberately observable.
KINDS = {
    "text_present": "a given string appears in the page's visible text",
    "text_absent": "a given string does not appear in the page's visible text",
    "text_count_at_least": "a given string appears at least N times in visible text",
    "element_present": "an interactive element with the given accessible name exists",
    # Not a check. A declared blind spot: something the task requires that this
    # assertion language cannot bind to the page. It never fails the verifier,
    # and it is reported separately, because "I cannot check this" and "this is
    # broken" are different claims, and conflating them has teeth.
    #
    # The first verifier generated here expressed its gap as a `text_present`
    # looking for the literal string "UNVERIFIED: ...", which made the task
    # permanently unfinishable: the gate could never pass, so the agent could
    # never stop, no matter how correct its work was.
    "unverifiable": "the task requires something this verifier cannot check",
    # File predicates. A task whose deliverable is a file cannot be verified by
    # reading the page, and a verifier that tries is not merely weak -- it can
    # never pass. The fourth generated verifier here did exactly that: sixteen
    # assertions looking for `claim_count`, `clm_3001` and `1002.1` in the
    # page's visible text, all of which live in `report.json`. Six of them
    # "passed" vacuously, because the strings were absent from the page for the
    # same reason the task was correct.
    "file_exists": "a file exists in the workspace",
    "json_field_equals": "a JSON file in the workspace has a top-level field equal to a value",
}

# Evaluated in the page. Returns the visible text of the document body plus a
# list of interactive elements by accessible name, so every predicate is a
# lookup rather than another round of DOM queries.
OBSERVE_JS = """
() => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const text = norm(document.body ? document.body.innerText : '');
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link]';
  const names = [];
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || st.visibility === 'hidden' || st.display === 'none') continue;
    const label = el.labels && el.labels.length ? el.labels[0].textContent : null;
    const name = norm(el.getAttribute('aria-label') || label || el.getAttribute('placeholder') || el.innerText || el.textContent || '');
    if (name) names.push(name);
  }
  return { text, names };
}
"""


@dataclass
class Assertion:
    id: str
    kind: str
    description: str
    value: str | None = None
    count: int | None = None
    role_hint: str | None = None
    expected: object | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Assertion":
        return cls(
            id=str(d.get("id") or ""),
            kind=str(d.get("type") or d.get("kind") or ""),
            description=str(d.get("description") or ""),
            value=d.get("value"),
            count=d.get("count"),
            role_hint=d.get("role"),
            expected=d.get("expected"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.kind,
            "description": self.description,
            "value": self.value,
            "count": self.count,
            "role": self.role_hint,
            "expected": self.expected,
        }

    def problems(self) -> list[str]:
        out = []
        if not self.id:
            out.append("assertion has no id")
        if self.kind not in KINDS:
            out.append(f"assertion {self.id!r} has unknown type {self.kind!r}")
        if self.kind in ("text_present", "text_absent", "text_count_at_least",
                         "element_present", "file_exists", "json_field_equals"):
            if not self.value:
                out.append(f"assertion {self.id!r} of type {self.kind} needs a value")
        if self.kind == "json_field_equals" and ":" not in (self.value or ""):
            out.append(
                f"assertion {self.id!r} of type json_field_equals needs value "
                f"'<path>:<field>'"
            )
        if self.kind == "unverifiable" and self.value:
            out.append(
                f"assertion {self.id!r} is marked unverifiable and must not carry a value; "
                f"a gap written as a check can never pass"
            )
        # A model that has seen "UNVERIFIED: ..." as prose tends to keep writing
        # it as prose, inside a normal checkable assertion. That is the single
        # most damaging malformation available here, because the resulting
        # verifier can never pass and the agent can therefore never finish, so
        # it is rejected rather than tolerated.
        #
        # Checked on both fields, because the real artifact that prompted this
        # put the marker in `value` and ordinary prose in `description`.
        marker = ("UNVERIFIED", "NOT VERIFIABLE", "CANNOT BE VERIFIED")
        blob = f"{self.description or ''} {self.value or ''}".strip().upper()
        if self.kind != "unverifiable" and any(m in blob for m in marker):
            out.append(
                f"assertion {self.id!r} describes an unverifiable gap but has type "
                f"{self.kind!r}; use type 'unverifiable' with no value"
            )
        if self.kind == "text_count_at_least":
            if not isinstance(self.count, int) or self.count < 1:
                out.append(f"assertion {self.id!r} needs a positive integer count")
        if not self.description:
            out.append(f"assertion {self.id!r} has no description")
        return out

    def evaluate(self, observation: dict) -> tuple[bool, str]:
        text: str = observation.get("text", "")
        names: list[str] = observation.get("names", [])
        needle = (self.value or "").strip()
        low = text.lower()

        if self.kind == "text_present":
            ok = needle.lower() in low
            return ok, f"searched visible text for {needle!r}: {'found' if ok else 'not found'}"
        if self.kind == "text_absent":
            ok = needle.lower() not in low
            return ok, f"{needle!r} {'absent' if ok else 'still present'}"
        if self.kind == "text_count_at_least":
            n = low.count(needle.lower())
            want = int(self.count or 1)
            return n >= want, f"found {n} occurrence(s) of {needle!r}, need >= {want}"
        if self.kind == "element_present":
            hits = [n for n in names if needle.lower() in n.lower()]
            return bool(hits), f"matching controls: {hits[:4] or 'none'}"
        if self.kind == "unverifiable":
            return True, f"declared gap: {self.description}"
        if self.kind == "file_exists":
            return self._check_file_exists(observation)
        if self.kind == "json_field_equals":
            return self._check_json_field(observation)
        return False, f"unknown assertion type {self.kind!r}"

    # ---- file predicates -------------------------------------------------

    def _check_file_exists(self, observation: dict) -> tuple[bool, str]:
        ws = observation.get("workspace")
        if ws is None:
            return False, "no workspace is attached, so a file cannot be checked"
        target = Path(ws) / (self.value or "")
        return target.is_file(), f"{self.value} {'exists' if target.is_file() else 'is missing'}"

    def _check_json_field(self, observation: dict) -> tuple[bool, str]:
        ws = observation.get("workspace")
        if ws is None:
            return False, "no workspace is attached, so a file cannot be checked"
        parts = (self.value or "").split(":", 1)
        if len(parts) != 2:
            return False, f"value must be '<path>:<field>', got {self.value!r}"
        rel, field = parts[0].strip(), parts[1].strip()
        target = Path(ws) / rel
        if not target.is_file():
            return False, f"{rel} is missing"
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return False, f"{rel} could not be read as JSON: {exc}"
        if not isinstance(data, dict) or field not in data:
            return False, f"{rel} has no field {field!r}"
        got = data[field]
        expected = self.expected if self.expected is not None else self.count
        if expected is None:
            return True, f"{field} present with value {got!r} (presence only)"
        ok = _loose_equal(got, expected)
        return ok, f"{field} is {got!r}, expected {expected!r}"


@dataclass
class VerifierReport:
    passed: bool
    results: list[dict] = field(default_factory=list)

    @property
    def gaps(self) -> list[dict]:
        """Assertions that declare a blind spot rather than checking anything."""
        return [r for r in self.results if r["type"] == "unverifiable"]

    @property
    def checks(self) -> list[dict]:
        return [r for r in self.results if r["type"] != "unverifiable"]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": self.results,
            "gaps": [g["description"] for g in self.gaps],
        }

    def summary(self) -> str:
        lines = []
        for r in self.checks:
            lines.append(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['id']}: {r['description']} -- {r['detail']}")
        for g in self.gaps:
            lines.append(f"  [GAP ] {g['id']}: {g['description']}")
        if not self.results:
            lines.append("  (no assertions)")
        return "\n".join(lines)


class Verifier:
    """A set of assertions loaded from a generated `verify.json`."""

    def __init__(self, assertions: list[Assertion], source: str = "") -> None:
        self.assertions = assertions
        self.source = source

    @classmethod
    def load(cls, path: Path) -> "Verifier":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        raw = data.get("assertions") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            raise ValueError(f"{path}: expected an 'assertions' list")
        return cls([Assertion.from_dict(a) for a in raw], source=str(path))

    @classmethod
    def find(cls, skill_root: Path) -> "Verifier | None":
        """Locate a generated verifier next to the final skills.

        Only files listed in the extraction manifest are considered, so an
        abandoned draft's verifier cannot be picked up by accident.
        """
        manifest_path = Path(skill_root) / "extraction-manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for skill in manifest.get("skills", []):
                candidate = Path(skill_root) / Path(skill["path"]).parent / "verify.json"
                if candidate.is_file():
                    return cls.load(candidate)
        for candidate in sorted(Path(skill_root).rglob("verify.json")):
            return cls.load(candidate)
        return None

    def problems(self) -> list[str]:
        out: list[str] = []
        if not self.assertions:
            out.append("verify.json contains no assertions")
        seen: set[str] = set()
        for a in self.assertions:
            out.extend(a.problems())
            if a.id in seen:
                out.append(f"duplicate assertion id {a.id!r}")
            seen.add(a.id)
        return out

    def run(self, page, workspace=None) -> VerifierReport:
        observation: dict[str, Any] = page.evaluate(OBSERVE_JS)
        observation["workspace"] = Path(workspace) if workspace else None
        results = []
        for a in self.assertions:
            ok, detail = a.evaluate(observation)
            results.append({
                "id": a.id, "ok": ok, "description": a.description,
                "type": a.kind, "detail": detail,
            })
        # A declared gap never blocks completion; it is reported, not scored.
        blocking = [r for r in results if r["type"] != "unverifiable"]
        return VerifierReport(passed=all(r["ok"] for r in blocking), results=results)


def _loose_equal(got, expected) -> bool:
    """Compare across the JSON/Python boundary without being fussy about types.

    A model writing {"grand_total": 1002.1} and one writing 1002.10 mean the
    same thing, and a verifier that fails one of them is failing on formatting
    rather than on substance.
    """
    if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        return abs(float(got) - float(expected)) < 0.01
    if isinstance(expected, str) and isinstance(got, str):
        return got.strip() == expected.strip()
    return got == expected
