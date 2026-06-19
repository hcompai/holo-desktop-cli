---
id: chat-widget
url: http://localhost:5173/dashboard
timeout_s: 240
viewport: { width: 1280, height: 900 }
backend: command
credentials: demo@nimbus.test / holo-qa-1
---

# Chat widget: ask a question and get an answer

## Setup

The Nimbus Desk dev server is running at `http://localhost:5173`. Sign in with the
credentials above if presented with the login page. You land on the Dashboard; a
round blue chat bubble sits in the bottom-right corner.

## Task

1. Click the chat bubble to open the assistant panel.
2. Confirm a greeting message from the assistant is visible.
3. Type "How do refunds work?" into the input and send it.
4. Wait for the assistant's reply.

## Expected Result

Within a few seconds of sending, the assistant replies with refund policy details
(mentions refunds being processed within 5 business days). The reply offers a
"Talk to a human" option. Your own message appears right-aligned above the reply.

## Verification

- FAIL if the panel does not open when the bubble is clicked.
- FAIL if no greeting is shown when the panel opens.
- FAIL if the typing indicator appears but no reply ever renders (wait at least 15 seconds).
- FAIL if the reply does not mention the refund timeline.
- PASS only if the full ask → reply exchange is visible in the chat log.
