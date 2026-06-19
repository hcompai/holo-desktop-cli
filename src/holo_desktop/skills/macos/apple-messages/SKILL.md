---
name: Apple Messages
description: Sending iMessages, SMS, and replies, plus reactions and search, in the Apple Messages desktop app.
publisher: H Company
version: "1.0.0"
bundle_id: com.apple.MobileSMS
---

Messages is a two-pane layout: conversation list on the left (newest at top), message thread on the right, composer at the bottom of the thread. iMessages render in blue bubbles, SMS/RCS in green — the color is the only persistent visual cue of which network is in use, which matters because SMS doesn't support read receipts, typing indicators, or rich reactions.

## Shortcuts

`Cmd+N` starts a new conversation; the To field autocompletes from Contacts and recent senders. `Cmd+F` searches inside the open conversation; `Cmd+Opt+F` searches across all conversations. `Cmd+↑` / `Cmd+↓` step through conversations in the sidebar. `Cmd+1` through `Cmd+9` jump to a pinned conversation. `Cmd+Delete` deletes the selected conversation (with confirmation).

In the composer: typing into the field starts a draft; `Return` sends, `Opt+Return` inserts a newline. This is the central gotcha — there is no Send button in the bare composer, the moment any text exists in the field a single `Return` keystroke makes it live.

## Composing

Get the recipient right before typing anything. When the named person matches multiple contacts (common with first-name-only searches), the autocomplete picks the first match — verify the right one is selected by checking the To chip's expanded view before typing the body. SMS-only recipients (no Apple device) show a green-tinted chip and the composer says "Text Message" instead of "iMessage"; this is the user's signal that there are no read receipts and the message is going over the carrier.

Type the message in the composer, not in the answer. Match the tone of the thread if there's prior context: short replies in short threads, no greeting/sign-off mid-conversation, mirror emoji and language. A colleague who always responds in three words doesn't want a paragraph back.

## Sending

`Return` sends immediately. **Send is Irreversible.** Apple's Undo Send (macOS Ventura+) gives a ~2-minute window via right-click → Undo Send on a just-sent message, but treat that as a safety net for typos, not as license to send before confirming. Stop after drafting, summarize recipient (and SMS-vs-iMessage if relevant) plus a one-line intent via `answer`, and wait for go-ahead. Don't repeat the body in the answer — the user can read it in the composer.

The composer also auto-sends on `Return` from any focus state inside it, including immediately after typing. If a draft is still being edited, leave the composer focused but don't press `Return` until confirmed.

## Reactions (Tapbacks)

Right-click (or two-finger click) on a message bubble opens the Tapback menu: heart, thumbs up, thumbs down, haha, !!, ?. Pick by clicking; the reaction posts immediately to everyone in the thread. Reactions are reversible (right-click and re-pick removes it) but the recipients have already seen the notification, so treat as semi-Irreversible.

## Group chats and edits

In group chats, replies thread under a specific message via right-click → Reply. Without that, replies post to the whole group. Editing a sent message (right-click → Edit) is allowed for ~15 minutes; both the original and the edit show in the recipient's thread with an "Edited" badge.

## Sources

Apple's Messages User Guide: https://support.apple.com/guide/messages/welcome/mac
