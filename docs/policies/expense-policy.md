# Expense reimbursement policy

This is the written policy that the ExpenseDesk benchmark tasks implement. It
exists so that the rubrics can be **checked rather than trusted**.

The credibility problem this file addresses: a benchmark whose hidden rules were
invented by the person who also wrote the method has a circularity problem. A
reader cannot tell whether the rules were chosen because they are realistic or
because they happen to favour the method. Publishing the rules does not make
them externally authoritative — they are still authored for this benchmark —
but it does make every rubric item checkable against a stated requirement. If a
rubric says a claim counts, this document says why.

Each rule below is annotated with what it tests.

## 1. Claim submission (`expense-submit`)

### 1.1 Only approved work is spend

A claim is reimbursable once it is **approved**. A `draft` is unfinished and a
`pending_approval` claim is not yet approved; neither is spend and neither
appears in a period report.

*Tests: reading a status field. The most legible rule available.*

### 1.2 Receipts must belong to the trip

A receipt belongs on a travel claim when **both** hold:

- its date falls inside the claim's period, and
- it is a business travel expense of the trip the claim covers — airfare,
  lodging, ground and rail transport to and from the trip.

A receipt does **not** belong when its title or merchant marks it as personal
spending, or when it belongs to a different expense category. A title
containing `Personal` is the clearest case.

*Tests: a rule that requires reading and interpreting receipt titles. No field
states it; it has to be derived from which receipts the demonstration attached
and which it left alone.*

### 1.3 A claim over the threshold needs a cost center

A claim whose total exceeds **500.00** requires a cost center before it can be
submitted. The cost center to use is the submitting user's own, shown in the
application header as `<team> · <cost center>`.

*Tests: a rule that is enforced by the application but not stated in the task.
The demonstration discovers it by being rejected once.*

### 1.4 Submission is confirmed

Submitting opens a confirmation dialog. `Cancel` aborts and leaves the claim in
draft. The claim is submitted only after `Confirm submission`, and the persisted
result is a status of **Pending approval** that survives navigation away and
back.

*Tests: a completion condition that is a persistent state, not the transient
confirmation message that appears and disappears.*

## 2. Period reporting (`expense-report`)

A period report covers exactly one `YYYY-MM` period and totals the spend to be
reimbursed in it.

### 2.1 Period

Only claims whose period equals the requested period are counted. An approved
claim from another month belongs to that month's report.

*Tests: reading a period field.*

### 2.2 Approval

Only approved claims are counted. See 1.1.

*Tests: reading a status field.*

### 2.3 Meals and entertainment are reimbursed separately

**Meals and entertainment are never included in a period expense report.** They
are reimbursed through a separate system, so an approved, in-period meals claim
is still excluded.

*Tests: the rule this benchmark exists to probe. It is not a column, it is not
enforced by the application, and it is not derivable from the exported data —
it is visible only as a difference between the demonstrated input and the
demonstrated output, or by asking the person who gave the demonstration.*

### 2.4 Totals are grouped by the claim's cost center

`by_cost_center` sums each cost center's counted lines. The cost center used is
the one recorded **on the claim**, not the submitting user's own.

*Tests: a rule that is easy to get backwards, because the submitting user's
cost center is the one visible in the header.*

### 2.5 Lines, not claims, carry the amounts

A claim may have several lines. Its amount is the sum of its lines, and it is
counted once regardless of how many lines it has. A missing receipt does not
remove a line from an approved claim — receipts matter at approval time, not at
reporting time.

*Tests: a distinction between counting claims and summing lines that a careless
implementation conflates.*

## What is deliberately not here

- **Where the rules come from.** They are authored for this benchmark, in the
  shape of a real internal policy. They are not an external standard and this
  file does not claim to be one.
- **Anything the tasks do not test.** The policy is scoped to the two tasks so
  that every rule has a rubric item and every rubric item has a rule.

## How to check a rubric against this document

`bench/evaluator.py` is the rubric. Each `RubricItem` has an `id` and a
`requirement`; the sections above are the requirements. If a rubric item cannot
be traced to a rule here, that is a defect in the benchmark and worth an issue.

The mapping is:

| task | rubric item | rule |
|---|---|---|
| `expense-submit` | R1 | 1.4 |
| | R2 | 1.2 (category must be a travel category) |
| | R3 | 1.3 |
| | R4 | 1.2 |
| | R5 | 1.2 |
| | R6 | 2.5 |
| | R7 | 1.3 |
| `expense-report` | R1, R2 | deliverable contract |
| | R3 | 2.5 |
| | R4 | 2.4 |
| | R5 | 2.3 |
| | R6 | 2.1, 2.2 |
