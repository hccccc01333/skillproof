---
name: submit-expense-claim-approval-queue
description: Submit a drafted expense claim in ExpenseDesk so it leaves Draft and lands in the approval queue (shown as "Pending approval"). Use whenever the user asks to get a claim into the approval queue, file a reimbursement, or submit an expense claim for approval, including cases where the first submission attempt is rejected and a claim field must be corrected first.
---

# Submit an ExpenseDesk claim into the approval queue

## Goal

A claim in ExpenseDesk starts as **Draft**. Get it submitted so it reads
**Pending approval** in MY CLAIMS, meaning an approver now owns it.

Two claims define the run:

- **Target claim** — the reimbursement claim the user names for the requested
  billing period (for example "the March 2026 travel reimbursement"). It is the
  only claim you edit.
- **Period** — the `YYYY-MM` period the claim covers. Only receipts dated in
  that period belong on the claim.

ExpenseDesk is a single page that does not scroll: controls below the fold are
off-screen with negative `y` and must be scrolled into view before use.

## 1. Open the claim

In MY CLAIMS, click the claim button whose title matches the target claim name
**and** whose status reads **Draft**. Open the matching Draft claim — never a
claim already marked Pending approval or Submitted.

## 2. Attach the receipts that belong to the period

Each receipt in RECEIPT INBOX shows:

- a title (what it was for)
- a vendor · `YYYY-MM-DD` · amount line
- an **Attach** button once unattached; it reads **Attached** after attaching.

Attach every receipt whose date falls in the claim's period. Click the **Attach**
button on each matching receipt row, one receipt per attach action — there is no
bulk attach.

**Verify each attach landed:** the row's button must flip from **Attach** to
**Attached** (a transient "Attached <title>" toast also appears, but the row
state is the check that counts).

Do **not** attach receipts dated outside the claim's period, and do not attach
receipts that are not part of the claim (for example a team dinner or another
expense purpose). Leave those rows showing **Attach**.

## 3. Build one expense line per attached receipt

Under EXPENSE LINES there is one add-row with a **Description** textbox, an
**Amount** textbox (placeholder `0.00`) and an **Add line** button.

For each attached receipt, in receipt order:

1. Type the receipt's title into **Description**.
2. Type the receipt's amount into **Amount**, matching the receipt's currency
   format (two decimal places, as shown on the receipt row — e.g. `412.80`).
3. Click **Add line**.

The line then appears as a row in the table with its amount in the AMOUNT
column and a dash in the RECEIPT column. The add-row resets (both fields clear,
amount back to `0.00`). **Total** is the sum of the lines and updates after each
**Add line** — confirm it equals the sum of the amounts you entered.

Stop adding lines once every attached receipt has its own line. There is no
claim-level total to enter; the total is derived.

## 4. Set the required fields

- **Category** (select under CLAIM DETAILS): pick the category that matches the
  claim's nature. For a travel reimbursement this is a travel option
  (**Travel - International** for travel between countries, **Travel - Domestic**
  for travel within one country). The placeholder reads **Select a category**
  until a value is chosen.
- **Cost center** (textbox under CLAIM DETAILS, placeholder `e.g. CC-0000`): fill
  this from the department shown in the ExpenseDesk header (top right, formatted
  `Department · CC-####`). It is required for some claims before they can be
  submitted, so fill it even when the page does not complain yet.
- **Note for approver**: optional. Leave it empty unless the user asked for a note.

## 5. Submit

1. Scroll the **Submit for approval** button into view and click it.
2. A confirmation dialog appears: **Submit this claim for approval?** — "The
   claim becomes read-only and is routed to your approver." Click
   **Confirm submission** (not **Cancel**).

### If the submission is rejected

A banner **"This claim cannot be submitted yet:"** appears with a bulleted
reason, and the claim stays Draft. Resolve exactly the named reason:

- **"Claims over 500 require a cost center."** (the cost-center threshold is 500,
  compared against the claim total) — type the department cost center into
  **Cost center**, then submit again.
- **"Select a category."** — choose a category in **Category**, then submit
  again.

Do not change anything else. Then repeat step 5 from **Submit for approval**.

## 6. Confirm the claim is in the approval queue

Read MY CLAIMS and confirm the target claim's status is **Pending approval**.

**This status change is the completion check and it must be verified in a
fresh view.** Click the claim back open (or reload) and confirm it still reads
**Pending approval** rather than Draft — the claim is now read-only, the
EXPENSE LINES table is unchanged, and the footer shows a
"Submitted to <approver> · total <amount>" line. Only then is the claim in the
approval queue.

## Recovery notes

- **Off-screen controls.** The page is taller than the viewport. If a target's
  position is above the top of the screen (negative offset) or a control such as
  **Submit for approval** is not visible, scroll the page and retry.
- **Misclick on the claim title.** The claim title element is nested inside the
  claim button; click anywhere on the claim button to open it.
- **Stale RECEIPT INBOX state.** If a row still shows **Attach** right after you
  clicked, re-check the row before assuming the attachment was saved.
- **No category chosen yet.** Submit stays blocked while the banner lists
  "Select a category."; pick a travel category and resubmit rather than
  resubmitting unchanged.