---
name: submit-expense-claim
description: Submit a draft ExpenseDesk travel reimbursement claim for approval. Use when asked to get a travel reimbursement claim into the approval queue — for example "Get my March 2026 travel reimbursement claim into the approval queue." Covers opening the draft claim, attaching the period's travel receipts while excluding non-travel ones, entering the matching expense lines, setting the travel category, supplying the cost center when the claim is rejected for one, and confirming the submission.
---

# Submit a travel reimbursement claim in ExpenseDesk

## Goal and inputs

The goal is a submitted claim, not a filled-in form. End the task only when the
claim shows **Pending approval**.

Inputs that change per task (treat as given, not as fixed values):

- `claim_id` — the claim to open, e.g. `clm_2001`
- `period` — the reporting period the claim covers, e.g. `2026-03`
- `cost_center` — the cost center code to use when the form demands one, e.g.
  `CC-4471`

Work entirely in the ExpenseDesk web application. Make every change through the
visible page controls.

## Phase 1 — Open the draft claim

On the **MY CLAIMS** list, click the draft claim link whose label is the travel
reimbursement for the target period (accessible name reads like
`<period> travel reimbursement` with a `Draft` tag). Do not open a claim whose
status is not Draft. Verify the claim detail page loaded and still shows `Draft`.

## Phase 2 — Attach the travel receipts only

The claim page has a **RECEIPT INBOX** list of receipts, each with a merchant, a
date, an amount, and an `Attach` button; attached receipts show an `Attached`
label instead of the button.

1. Read the receipts one at a time.
2. Attach a receipt only when it is a **travel** expense **and** its date falls
   inside the target `period`. For each match, click that receipt's `Attach`
   button and confirm the row now reads `Attached`.
3. Leave every other receipt unattached — in particular non-travel charges such
   as a team dinner, and anything dated outside `period` (for example a
   "Personal hotel upgrade" receipt dated in the previous month).
4. Attach receipts in inbox order. The receipt rows move up as earlier ones are
   attached, so re-read the row under the next `Attach` button rather than
   relying on a row's earlier position.

Stop condition: every travel receipt dated within `period` is marked `Attached`
and no `Attach` button remains on a receipt that meets both criteria.

## Phase 3 — Enter one expense line per attached receipt

The claim has an **EXPENSE LINES** table showing DESCRIPTION / AMOUNT / RECEIPT
columns, a `Total` row, and an empty input row with `Description` and `Amount`
textboxes plus an `Add line` button.

For each attached receipt, in the same order:

1. Type the receipt's description into the `Description` textbox.
2. Type the receipt's amount into the `Amount` textbox, exactly as printed on
   the receipt (e.g. `412.80`).
3. Click `Add line`. The line appears in the table with its receipt marked
   `—` in the RECEIPT column, the empty input row is cleared, and `Total`
   increases by that amount.

Do not type the amount with a currency symbol. Do not add a line for any receipt
left unattached in Phase 2 — that is what keeps non-travel charges off the claim.

Stop condition: the number of expense lines equals the number of attached
receipts, and `Total` equals the sum of the attached receipt amounts.

## Phase 4 — Set the category

In **CLAIM DETAILS**, open the `Category` combobox and choose **Travel -
International** for an overseas trip (use **Travel - Domestic** when the claim is
domestic). The combobox lists `Travel - Domestic`, `Travel - International`,
`Lodging`, `Meals & Entertainment`, and `Office Supplies`; pick the one that
matches where the trip happened.

Selecting the category clears the "Select a category" validation message and
reveals any remaining requirement (see Phase 5).

## Phase 5 — Submit, then satisfy the cost-center requirement

1. Click `Submit for approval`.
2. A dialog titled **Submit this claim for approval?** appears saying the claim
   becomes read-only and is routed to the approver, with `Cancel` and
   `Confirm submission` buttons. Click `Confirm submission`.
3. Watch the red **"This claim cannot be submitted yet:"** banner. It lists the
   outstanding requirements, one bullet each. Act on every bullet:
   - `Select a category.` — go back to Phase 4.
   - `Claims over 500 require a cost center.` — focus the `Cost center` textbox
     (placeholder `e.g. CC-0000`) and type the `cost_center` input.
4. When the banner no longer lists anything that can be fixed, click
   `Submit for approval` again and confirm the submission dialog again.

Do not read the banner as a generic failure: a rejected submission is the normal
path to discovering the cost-center rule. Re-submit only after every listed
requirement is actually satisfied — the claim is routed on the first submission
that passes.

## Phase 6 — Verify the claim is in the approval queue

Two visible checks, both required:

1. The page shows the confirmation `Claim submitted for approval` together with
   the submitter and the total (for example `Submitted to M. Okonkwo · total
   $712.50`). The total must match the `Total` from Phase 3.
2. The claim's status reads **Pending approval** — shown next to the claim title
   on the detail page and in the **MY CLAIMS** list. The banner reading `This
   claim cannot be submitted yet:` must be gone.

Re-open the claim from the **MY CLAIMS** list rather than trusting the on-screen
confirmation: the status field is the persistent record, and `Pending approval`
there means the claim is genuinely in the queue. `Draft` afterwards means the
submission did not land — return to Phase 5.

While the claim is Pending approval its content is read-only; the fields that
were editable before the submission are not editable now.

## Recovery notes

- If a receipt shows `Attached` before you clicked it, the attachment already
  exists — do not re-add it.
- If a line you added does not appear in the table, click `Add line` again after
  re-checking that both `Description` and `Amount` are filled; an incomplete row
  is not added.
- If `Submit for approval` does nothing, the red banner is still listing a
  requirement. Read it and address the listed items; do not assume the click was
  ignored.