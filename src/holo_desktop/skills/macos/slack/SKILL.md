---
name: Slack
description: Sending messages, navigating channels and DMs, threading, searching, and reacting in the Slack desktop app.
publisher: H Company
version: "1.0.0"
source_url: https://github.com/azmym/agent-skills
license: MIT
icon_url: https://api.iconify.design/logos:slack-icon.svg
bundle_id: com.tinyspeck.slackmacgap
---

Slack is a three-pane Electron app: workspace switcher on the far left (when multiple workspaces are signed in), channel/DM sidebar next to it (with sections for unreads, threads, DMs, channels, apps), message pane in the middle, and a contextual right pane that opens for threads, profiles, search results, and pins. The composer sits at the bottom of the message pane.

## Shortcuts

Jump: `Cmd+K` opens the universal switcher — type a channel name (`#general`), a DM target (`@alice`), or a query and `Return` navigates. This is the single most-used shortcut; prefer it over clicking in the sidebar. `Cmd+Shift+K` browses DMs only.

Navigate: `Cmd+[` / `Cmd+]` step back/forward through visited channels. `Cmd+1` through `Cmd+9` jump to a starred channel. `Cmd+Shift+A` opens All Unreads.

Compose: `Esc` while in a channel marks it read and clears focus. Click in the composer or hit `Tab` from the channel to start typing. `Cmd+B/I/U` for bold/italic/strike, `Cmd+Shift+C` for inline code, `Cmd+Shift+9` for blockquote, `Cmd+Shift+8` for bulleted list.

Search and discovery: `Cmd+F` searches inside the current channel; `Cmd+G` finds the next match. Workspace-wide search is in the top bar — `Cmd+K` then type or click the magnifier.

Reference: `Cmd+/` opens Slack's full shortcut overlay anytime.

## Composing

The composer formats with markdown-like syntax (asterisks for bold, backticks for code, `>` for quote) plus rich formatting via the toolbar at the bottom-left. `@` triggers user/group mention autocomplete, `#` triggers channel autocomplete, `:` triggers emoji autocomplete. Channel mentions are not just decoration — `@channel` notifies everyone active, `@here` notifies everyone online; treat both as Gated and confirm before posting.

Threads: clicking a message's "Reply in thread" opens the right pane. By default thread replies post only in the thread; check "Also send to #channel" if the user wants the reply visible in the main timeline. New top-level posts go to the main channel — never use a thread when the user said "post in #channel" without thread context.

Match the channel's tone. A channel with all-lowercase one-line messages doesn't want a formatted memo back; a status update channel may want structured bullets. When unsure, mirror the most recent few messages in the thread.

## Sending

`Return` sends; `Shift+Return` inserts a newline. **Slack's default is Enter-sends**, which means the moment a draft exists in the composer, a single keystroke makes it live. This is the central gotcha — never press `Return` until the user has confirmed.

**Confirmation template before any write.** Before sending, editing, deleting, reacting, or pinning, stop and summarize via `answer`:

> **To:** #channel-name (or @user for DM)
> **Action:** Send / Edit / Delete / React / Pin
> **Preview:** (one-line summary, not the full body if it's already visible in the composer)
>
> Send this?

Wait for explicit go-ahead. The composer holds the draft; the user can edit it directly or ask Holo to revise before the second-pass confirmation.

## Reactions, pins, and edits

Hover over a message to reveal the action bar. Reactions post immediately and are visible to the whole channel/thread — reversible (click the reaction again to remove) but everyone saw it. Pinning posts a "pinned this message" system notice in the channel; unpin if it was a mistake but the notice itself stays. Editing your own message shows an "(edited)" badge to readers; deleting removes content but leaves a "This message was deleted" placeholder for ~30 seconds in most workspaces.

## Slash commands and special cases

Slash commands run in the composer: `/remind`, `/dm`, `/poll`, `/away`, etc. They execute on `Return` without a preview — confirm before triggering anything mutating (`/invite`, `/leave`, `/archive`).

Slack is Electron, which means right-click on a message works but right-click in the composer text area is a normal text-edit context menu, not a Slack action menu — use hover-then-click for message actions.

## URL parsing

Slack message URLs follow `https://<workspace>.slack.com/archives/<CHANNEL_ID>/p<TIMESTAMP>`, where the timestamp has the dot removed (e.g. `p1770725748342899` is `1770725748.342899`). To open a thread, the URL adds `?thread_ts=<PARENT_TS>`. If a user pastes a Slack link, navigate via `Cmd+K` and the channel ID rather than relying on link-click behavior.

## Sources

Slack's keyboard shortcuts: https://slack.com/help/articles/201374536. Confirmation-before-write pattern adapted from azmym/agent-skills (MIT): https://github.com/azmym/agent-skills/tree/main/skills/slack
