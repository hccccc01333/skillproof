---
name: expensedesk-submit-travel-claim
description: Submit an existing draft travel reimbursement claim in the ExpenseDesk web app into the approval queue. Use when the request is to get a travel/expense claim for a named period (for example "March 2026 travel reimbursement" or "April 2026 travel reimbursement") submitted for approval, which requires attaching the receipts that belong to the claim, entering one expense line per receipt, setting the claim category, supplying the cost center when the total crosses the threshold, confirming the submission dialog, and verifying the claim leaves Draft status.
---

# Submit an ExpenseDesk travel claim for approval

The goal is a single persistent state change: the draft travel claim for the requested
period becomes **Pending approval** (in the approval queue). The request names only the
period; the receipts that belong on the claim, the category, the cost center, and the
submit/confirm step are all decided from what the app shows. Work only through the
visible ExpenseDesk UI — never through a console, script, or direct data edit.

## Parameters taken from the request

- **Claim period** — the month and year named in the request (e.g. `March 2026`, period
  value `2026-03`). It selects which claim to open and which receipts date inside the claim.
- **Signed-in user's cost center** — read from the account line in the top-right header
  (it renders as `<team> · <cost center>`, e.g. `Field Operations · CC-4471` → value
  `CC-4471`). Never invent or reuse a cost center from another source.

Read on the fly, never hardcode: receipt titles/amounts, claim total, approver name.

## Procedure

1. **Open the correct draft claim.** In the left **MY CLAIMS** list, click the claim whose
   name contains the requested period and whose status is `Draft`. Do not open a claim for
   a different period, and do not create a new claim. The claim form then shows
   **CLAIM DETAILS** (Category, Cost center, Note for approver), **EXPENSE LINES**
   (Description, Amount, Add line, Total), **RECEIPT INBOX**, and the
   **Submit for approval** button. Scroll the form as needed — the sections are stacked.

2. **Attach the receipts that belong to this claim.** For each receipt row in the
   **RECEIPT INBOX**, attach it when both conditions hold:
   - its date falls inside the claim period, and
   - it is a business travel expense of the trip this claim covers (airfare, lodging,
     ground/rail transport to and from the trip).

   Leave a receipt unattached when its title or merchant marks it as personal spending
   (a title containing `Personal`) or when it belongs to a different expense category such
   as meals and entertainment (for example a team dinner). Attaching a non-travel or
   personal receipt is an error: it inflates the claim total and misfiles the claim.

   Click the row's `Attach` button; the row's status text changes from `Attach` to
   `Attached`. Rows already showing `Attached` need no action. Confirm every intended
   receipt shows `Attached` before continuing.

3. **Add one expense line per attached receipt.** For each attached receipt, in order:
   - type the receipt's short title (its first line, e.g. the item name) into **Description**;
   - type the receipt's amount into **Amount** as a plain number with the same two
     decimals as shown, no currency symbol (e.g. `412.80`);
   - click **Add line**.

   The line appears in the **EXPENSE LINES** table and **Total** updates. Add lines one at
   a time and confirm the new row is listed before typing the next one. Exact rule:
   *each line amount equals the receipt's total, and the claim total equals the sum of the
   line amounts* — after the last line the table's **Total** must equal the sum of the
   attached receipts' amounts. Enter every intended line once; do not duplicate a line.

4. **Set the Category** from the claim's **Category** dropdown (`Select a category`,
   `Travel - Domestic`, `Travel - International`, `Lodging`, `Meals & Entertainment`,
   `Office Supplies`). Choose the Travel option that matches the itinerary's scope:
   `Travel - International` when the trip crosses national borders (an international
   carrier/airport pair or a non-domestic city pair on the receipts/claim), `Travel - Domestic`
   when it stays within the same country.

5. **Read the validation banner before submitting.** The form shows
   `This claim cannot be submitted yet:` followed by bullet reasons (for example
   `Select a category.`). Resolve every bullet first — a claim over `500` in total requires
   a cost center, so when the total exceeds 500 and a cost-center reason is listed, type the
   signed-in user's cost center (from the header account line) into **Cost center**.
   The banner disappears when no blockers remain. `Note for approver` is optional — leave it
   empty unless the request asks for a note.

6. **Submit and confirm.** Click **Submit for approval**. A dialog titled
   `Submit this claim for approval?` appears, stating the claim becomes read-only and is
   routed to your approver, with `Cancel` and `Confirm submission`. Click
   **Confirm submission**. `Cancel` aborts and leaves the claim in Draft, so never treat the
   dialog alone as completion.

7. **If the submission is rejected, fix the named blocker and resubmit.** Validation
   failures keep the claim in Draft, leave the form editable, and show the reason (for
   example `Claims over 500 require a cost center.`). The stored lines, receipts, category,
   and cost center are kept, so do not re-enter them; fill only the field the message names
   (cost center ← the header account line) and then repeat the
   **Submit for approval** → **Confirm submission** sequence.

8. **Verify the persisted result in the UI.** All of the following must be observable:
   - the claim no longer reads `Draft`; its status reads `Pending approval` (visible in the
     claim header and in the **MY CLAIMS** list row for that period);
   - the claim detail footer shows `Submitted to <approver> · total <amount>`, with the total
     equal to the sum of the entered line amounts;
   - the `This claim cannot be submitted yet:` banner is gone;
   - a `Claim submitted for approval.` confirmation appears.

   If the claim still reads `Draft`, or the footer/routing line is absent, the submission did
   not complete — return to the claim, clear any listed blocker, and submit and confirm again.
   Reopen the claim from the **MY CLAIMS** list to confirm the status survived navigation.

Run the bundled `verify.json` assertions against the rendered page before declaring
completion; report any assertion it cannot express as a stated gap rather than assuming
success.
