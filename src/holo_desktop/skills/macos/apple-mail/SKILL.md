---
name: Apple Mail
description: Composing, sending, replying, searching, and triaging messages in the Apple Mail desktop app.
publisher: H Company
version: "1.0.0"
bundle_id: com.apple.mail
---

Mail is a three-pane layout by default: mailbox sidebar on the left (toggleable with `Ctrl+Cmd+S`), message list in the middle, message body on the right. The toolbar carries the most common actions but every one of them has a keyboard shortcut, so prefer keys for speed.

## Shortcuts

Compose and send: `Cmd+N` new message, `Shift+Cmd+D` send. `Cmd+R` reply to selected, `Shift+Cmd+R` reply all, `Shift+Cmd+F` forward, `Shift+Cmd+E` redirect (preserves the original sender). `Shift+Cmd+A` attach file. `Shift+Cmd+V` paste as quote. `Opt+Cmd+B` show Bcc; `Opt+Cmd+R` show Reply-To.

Navigation: arrow keys move through the message list. `Shift+Cmd+U` toggles read/unread on the selection. `Shift+Cmd+J` marks as junk. `Ctrl+Cmd+M` moves to the predicted mailbox (Mail's ML guess).

Search: type into the search field at the top right of the viewer, or `Cmd+Option+F`. `Cmd+L` toggles the filter bar for the current mailbox (Unread, Flagged, Attachments).

## Composing

Hit `Cmd+N`, then fill To / Subject / body in that order. Recipient autocomplete pulls from Contacts and recent senders — the first match is auto-selected on Tab, which is the single most common silent-send-to-wrong-person trap. When a name has two contacts, verify the email address in the chip before continuing. For external recipients, the address chip has no visual distinction from internal ones; if the user named a colleague by first name only, expand the chip and confirm the domain.

Type the message in the compose window, not in the answer. Match the formality of the thread: replies to existing threads should mirror the prior tone; new threads default to the user's normal voice. Signatures auto-insert from Mail settings — leave them as is unless the user asked to strip them.

## Sending

`Shift+Cmd+D` sends immediately. **Send is Irreversible.** Apple's Undo Send (introduced in macOS Ventura) gives a 10–30 second window via the "Undo Send" link at the bottom of the sidebar, but treat that as a safety net for typos discovered instantly, not as license to send before confirming. Stop after drafting, summarize recipient, subject, and one-line intent via `answer`, and wait for go-ahead. Do not repeat the body content in the answer; the user can read it in the compose window.

For external sends, the cost of a wrong send dwarfs any number of confirmation pings. If the user said "draft" or "write" rather than "send", stop after drafting regardless and do not propose sending until they ask.

## Triaging

When asked to summarize unread mail: read each thread top-down in the list, skip newsletters/calendar invites/automated notifications unless the user said otherwise, and reply with three bullet groups — asks needing reply today (one line per ask with sender), heads-ups for the day, and an aggregate count of low-signal items ("12 newsletters, 4 GitHub notifications"). Don't draft replies unless asked.

## Sources

Apple's keyboard shortcuts for Mail: https://support.apple.com/guide/mail/keyboard-shortcuts-mlhlb94f262b/mac
