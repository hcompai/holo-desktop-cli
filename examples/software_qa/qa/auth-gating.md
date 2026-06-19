---
id: auth-gating
url: http://localhost:5173/dashboard
timeout_s: 240
viewport: { width: 1280, height: 900 }
backend: command
credentials: demo@nimbus.test / holo-qa-1
---

# Auth: protected pages redirect when logged out, logout ends the session

## Setup

The Nimbus Desk dev server is running at `http://localhost:5173`. Start logged out.

## Task

1. Navigate directly to `http://localhost:5173/dashboard` while logged out.
2. Sign in with the credentials from the frontmatter.
3. Navigate to the Tickets page, then to Settings, via the top navigation.
4. Click "Log out" in the top bar.
5. Navigate directly to `http://localhost:5173/tickets`.

## Expected Result

Step 1 redirects to the login page without flashing dashboard content. After
sign-in, Tickets shows a table of support tickets and Settings shows the profile
panel — no re-login is asked between pages. After logout, step 5 redirects back to
the login page.

## Verification

- FAIL if any protected page (`/dashboard`, `/tickets`, `/settings`) renders its
  content while logged out.
- FAIL if the session is lost while navigating between protected pages.
- FAIL if "Log out" does not return to the login page, or the session survives it.
- PASS only if gating holds before login, navigation holds during the session, and
  gating holds again after logout.
