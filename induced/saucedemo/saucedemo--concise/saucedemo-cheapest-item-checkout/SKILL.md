---
name: saucedemo-cheapest-item-checkout
description: Log into the SauceDemo / Swag Labs storefront at saucedemo.com, buy the lowest-priced product in the catalog, and complete the checkout flow with the customer name and postal code supplied by the task. Use when a task asks for a purchase or checkout on saucedemo.com (Swag Labs) that involves the cheapest, lowest-priced, or least expensive item.
---

# Buy the cheapest Swag Labs item and complete checkout

All state changes must be made through the site's own visible controls (text boxes,
buttons, links) and verified from the rendered page. Do not call the site's internals,
edit storage, or script the flow.

## Task inputs

- **username** — supplied with the task (for example `standard_user`).
- **customer full name** — supplied with the task (for example `Dana Whitfield`).
- **postal / zip code** — supplied with the task.
- **password** — *not* an input. The login page prints it in its footer under
  **"Password for all users"**; read it there and use it. Do not guess it.

The site serves live data and no reset endpoint exists: whatever is already in the
cart or session is part of the starting state, so check the cart before assuming it
is empty.

## 1. Log in

1. Open `https://www.saucedemo.com/`. The page shows a **Username** text box, a
   **Password** text box, and a **Login** button.
2. Type the task's username into **Username** and the password published under
   "Password for all users" into **Password**.
3. Click **Login**.
4. Confirm the Products page loaded: the URL is `/inventory.html`, the header shows
   the **Swag Labs** brand and a cart icon, and the body is titled **Products** with
   the product grid and a sort dropdown.

**Recovery:** if the login form returns instead of the Products page, the
credentials were rejected. The page prints both the list of accepted usernames and
the shared password in its footer — re-read them, retype the username **exactly as
the task supplies it** (do not substitute a name copied from the site's list), type
the published password, and click **Login** again. Do not proceed until the
Products page is showing.

## 2. Identify the cheapest product

1. The grid lists every catalog product as a card containing the product name, its
   price, and an **Add to cart** button. Read the **price shown on every card**.
2. The grid's default order is **Name (A to Z)**, which has nothing to do with
   price — never assume the first card, or any particular card, is the cheapest.
3. Scroll the product list to its end so that every card is visible before deciding;
   the grid can be taller than the viewport and the last row is easily missed.
4. Compare all prices and choose the **single lowest** one. If two products tie at
   the lowest price, either satisfies "cheapest" — pick one of them only.

Optional aid: the Products toolbar's sort dropdown (default **Name (A to Z)**)
offers **Price (low to high)**, which moves the cheapest product to the front of the
grid. If you use it, still read the price off the card you are about to add.

## 3. Add exactly that one item

1. In the chosen product's own card, click its **Add to cart** button once.
2. The button in that card changes to **Remove**, and the header cart icon gains a
   count badge of **1** (its accessible name becomes "Cart, 1 items").
3. Verify the badge reads exactly one. If the cart already held items, remove the
   others later on the cart page so that only the cheapest product, in quantity 1,
   remains.

## 4. Open the cart and check it

1. Click the header cart icon (accessible name "Cart, N items").
2. On **Your Cart** (`/cart.html`) confirm a single row: the cheapest product's name,
   **QTY 1**, and its unit price. If the cart holds a different product, an extra
   product, or a quantity above 1, remove the offending entries (the **Remove**
   button on each row) and add the correct item from the Products page.
3. Click **Checkout**.

## 5. Enter the customer information

The **Checkout: Your Information** page (`/checkout-step-one.html`) has three text
boxes, identified by their placeholders **First Name**, **Last Name**, **Zip/Postal
Code**, plus **Cancel** and **Continue**.

1. Split the task's full name at the space: the text before the first space goes in
   **First Name**, the remainder in **Last Name** (`Dana Whitfield` → `Dana` /
   `Whitfield`).
2. Type the task's postal code into **Zip/Postal Code**. Use the value exactly as
   supplied, without altering its length or adding characters.
3. Click **Continue**.

**Recovery:** if the same form comes back instead of the overview, at least one field
was empty. Read the values actually typed into the three boxes — placeholder text can
look like a value — retype whichever field is blank, and click **Continue** again.

## 6. Verify the order before committing

**Checkout: Overview** (`/checkout-step-two.html`) is the last checkpoint before the
purchase is placed. Confirm:

- exactly one line item is listed, with **QTY 1**;
- its unit price and the **Item total** both equal the cheapest product's price you
  selected in step 2;
- payment and shipping lines are the site's own defaults, which need no change.

Tax and Total are computed by the site from the item total; they are not part of the
selection rule, so do not treat them as something to enter.

If anything is wrong, click **Cancel** to leave the overview, fix the cart on the
cart page, and run Checkout again. Click **Finish** only when the overview is
correct — **Finish** places the order and is not reversible.

## 7. Confirm completion

Click **Finish**. The **Checkout: Complete!** page (`/checkout-complete.html`) appears
with a green check mark, the message **"Thank you for your order!"**, and the
**Back Home** / **Generate PDF order** buttons. The header cart icon no longer shows a
count badge, because placing the order emptied the cart.

That confirmation page is the state the task must end in. Do not click **Finish**
again, do not add further items, and make no other change on the site.

## Stop condition and scope

The task is complete when the order confirmation page is displayed for exactly one
unit of the single cheapest catalog product, checked out with the supplied customer
name and postal code. Add no extra products, place no additional order, and touch
nothing else in the storefront.

## Limitations

- The site's prices and catalog are live and can differ between runs; the cheapest
  product must be re-derived from the page every time rather than assumed.
- Neither the Checkout: Overview page nor the confirmation page restates the
  customer name or postal code, and the confirmation page does not list the ordered
  line item. Those details are only observable on the surfaces where they are entered
  or summarized (the information form and the overview), so verify them there before
  clicking **Continue** and **Finish**.
