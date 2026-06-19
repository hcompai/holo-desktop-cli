---
id: chat-escalation
url: http://localhost:5173/dashboard
timeout_s: 300
viewport: { width: 1280, height: 900 }
backend: command
credentials: demo@nimbus.test / holo-qa-1
---

# Chat widget: escalate to a human and receive a ticket number

## Setup

The Nimbus Desk dev server is running at `http://localhost:5173`. Sign in with the
credentials above if presented with the login page.

## Task

1. Open the chat widget from the bottom-right bubble.
2. Send the message "How do refunds work?" and wait for the reply.
3. Click "Talk to a human" under the assistant's reply.
4. Fill the escalation form: email `qa@nimbus.test`, summary `Refund for annual plan`.
5. Submit the form via "Open ticket".

## Expected Result

The form disappears and the assistant posts a confirmation message containing a
ticket number of the form `ND-<number>` (the first ticket in a session is
`ND-1042`), echoing the summary text and the email address.

## Verification

- FAIL if "Talk to a human" is not offered under the refund reply.
- FAIL if the escalation form does not appear, or rejects valid input.
- FAIL if no confirmation message with an `ND-` ticket number is posted after submit.
- PASS only if the confirmation references both the ticket number and the email provided.
