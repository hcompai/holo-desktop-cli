---
id: auth-login
url: http://localhost:5173/login
timeout_s: 240
viewport: { width: 1280, height: 900 }
backend: command
credentials: demo@nimbus.test / holo-qa-1
---

# Auth: wrong password shows an error, right password signs in

## Setup

The Nimbus Desk dev server is running at `http://localhost:5173`. Start logged out
(the `/login` page shows the sign-in card). If a session exists, log out first via
the "Log out" button in the top bar.

## Task

1. Enter email `demo@nimbus.test` and the wrong password `wrong-password-1`, then submit.
2. Observe the form's response.
3. Now enter the correct credentials from the frontmatter and submit.

## Expected Result

After step 1, an inline error reading "Incorrect email or password." appears under
the form and the user stays on the login page. After step 3, the user is signed in
and lands on the Dashboard (stat cards visible, email shown in the top bar).

## Verification

- FAIL if a wrong password produces no visible error message (a silently cleared
  form is a failure, not a pass).
- FAIL if a wrong password signs the user in.
- FAIL if correct credentials do not land on the Dashboard (e.g. bounced back to
  the login page).
- PASS only if both the negative and positive paths behave as described.
