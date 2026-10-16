---
name: theinternet-login
description: Log in to a the-internet (herokuapp.com) login form using credentials supplied in the request, then confirm the resulting secure area is displayed. Use whenever a task asks you to authenticate on a the-internet login page and verify you reached the protected page.
---

# Log in to the-internet and confirm the secure area

Authenticate against the login form of a `the-internet.herokuapp.com`-style site by typing the credentials supplied in the request, submitting the form, and confirming the protected page appeared. Everything is done through the visible login form: typing into its fields and clicking its submit button.

## Inputs

Take the credentials from the request, not from the page:

- `username` — username to type into the form.
- `password` — password to type into the form. It is masked on screen; that is normal.

The task supplies both. Do not read credentials off the login page, and do not fall back to any credentials printed in page text or example copy.

## Procedure

1. Open the login page. If the page is not already loaded, navigate to its login URL (the site root's login page). Wait until the "Username" and "Password" fields and the "Login" button are visible before typing.
2. Type `username` into the **Username** field. It is a text input (`input#username`, accessible name "Username"). Do not include extra whitespace.
3. Type `password` into the **Password** field. It is a password input (`input#password`, accessible name "Password") whose contents are masked as you type.
4. Click the **Login** button. It is the form's submit button (`form#login > button`, text "Login"), located directly below the two fields.
5. Confirm the secure area is displayed before declaring success.

## Confirming the success state

Success is not the click; it is the resulting page. After submitting, check the page shows:

- A success banner with the text **"You logged into a secure area!"**, and
- The heading **"Secure Area"** on the content panel below it.

Both signals together mean the authentication succeeded. Either one alone is not enough: a failure leaves you on the login page, where the content is a "Login Page" heading and an inline error message instead.

Treat the banner as transient feedback. If it has been dismissed or disappeared, the **"Secure Area"** heading remains visible and still confirms the logged-in state.

## Checking the result you actually got

The secure-area state is confirmed by what is visible on the page after submission, not by the fact that a click happened:

- If the **"Secure Area"** heading and the "You logged into a secure area!" banner are present, the login succeeded.
- If the page still shows the **Login Page** heading with an inline error message, the credentials were rejected. Do not retry blindly: check the typed values against the supplied `username` and `password`, correct any mismatch, and resubmit once.

## Notes

- The login form has no reset control, so a re-run starts from whatever the site currently serves. If you land already logged in, the "Secure Area" page is the expected end state and needs no further action.
- Keep the session after success unless the task asks to log out. Logging out destroys the state the task asked you to produce.