---
name: Discord
description: Navigating servers and channels, sending messages, using threads, voice channels, search, and DMs in the Discord desktop app.
publisher: H Company
version: "1.0.0"
source_url: https://support.discord.com/hc/en-us/articles/360045138571-Keyboard-Shortcuts
license: Vendor docs
bundle_id: com.hnc.Discord
icon_url: https://api.iconify.design/skill-icons:discord.svg
---

Discord is a four-pane Electron app: a vertical server list on the far left (each server is a circular icon, plus Friends/Library/Nitro pinned to the top), a channel/DM sidebar to the right of it (text/voice/forum channels grouped under categories, with Inbox and Friends at the top for DMs), the message pane in the middle, and a contextual right pane that opens for member list, threads, pins, search results, and inbox previews. The composer sits at the bottom of the message pane.

## Shortcuts

Jump: `Cmd+K` opens the quick switcher — type a server name, channel name (`#general`), DM target (`@alice`), or query, then `Return` navigates. This is the single most-used shortcut; prefer it over scrolling the sidebar. `Cmd+/` opens the searchable keyboard-shortcuts overlay; point Holo here when a shortcut isn't documented below.

Navigation: `Cmd+Alt+Up` / `Cmd+Alt+Down` cycle through channels in the current server (skipping unreads with `Shift+Cmd+Alt+Up/Down`). `Cmd+Alt+Left` / `Cmd+Alt+Right` cycle through servers. `Esc` marks the current channel as read; `Shift+Esc` marks the whole server as read. `Cmd+B` toggles the "Activities" sidebar; `Cmd+U` toggles the member list.

Composer: `Return` sends. `Shift+Return` newline. `Up` (with composer empty) edits your last message; `Esc` cancels. `Tab` autocompletes `@mention`, `#channel`, or `:emoji:`. `Cmd+E` opens the emoji picker. `Cmd+G` opens GIF picker, `Cmd+P` opens stickers. Markdown works inline: `**bold**`, `*italic*`, ``` `code` ```, ``` ```block ```, `||spoiler||`, `> quote`.

Voice/video (while connected to a voice channel): `Cmd+Shift+M` toggle mute, `Cmd+Shift+D` toggle deafen, `Cmd+Shift+V` start/stop video, `Cmd+Enter` answer incoming call, `Esc` decline.

Search and discovery: `Cmd+F` opens search scoped to the current channel/server with filters (`from:`, `mentions:`, `has:link`, `before:`, `after:`, `in:#channel`). `Cmd+I` opens Inbox (mentions, unreads, scheduled). `Cmd+J` jumps to the next unread channel; `Cmd+Shift+J` jumps to the next unread mention.

## Servers, channels, and DMs

The server list on the far left is the workspace switcher: each circle is a server, click to jump. The home icon (top) is DMs + Friends + Library. Servers can be reordered by drag; folders group them.

Channels are scoped to a server. Text channels show messages chronologically with threads opening in the right pane. Voice channels are clickable to join, no ring — others see you've joined. Forum channels show posts as a list; click one to enter the post. Stage channels are voice-with-speakers + audience.

DMs are scoped to the user, not a server. `Cmd+K` finds DMs by name. Group DMs (up to 10) live in the same DM sidebar with a multi-avatar icon.

## Threads

Hover a message → "Create Thread" or right-click → "Create Thread" opens a side panel. Threads are scoped to a parent message but live in the right sidebar of the message pane, not a separate channel. Posting in a thread doesn't ping the main channel. Useful for long subdiscussions where the user wants to keep the main channel clean.

## The send and edit boundaries

`Return` sends immediately — no preview, no confirmation. Discord messages are editable for the original sender (no time limit) and deletable, but the audit trail (edit history) is visible to anyone via the "edited" tag. Delete is final after a 14-day grace period for moderators. Confirm with `answer` before sending anything substantive in a server the user doesn't own — communities have tone norms that the agent doesn't see.

`@everyone`, `@here`, and role mentions (`@moderators`) push notifications to everyone in scope and are often rate-limited or restricted. Never use them in agent-drafted content without explicit user instruction; they're the Discord equivalent of a fire alarm.

Voice channels: joining one announces presence to every member of the server who's online. Leave by clicking "Disconnect" or `Cmd+W` on the call. Don't join voice channels speculatively; they're social presence, not exploration.

## Server permissions

A server's channel list is filtered by your role. Channels you can't see don't exist from your perspective — agent should not assume a channel is missing if a `#staff` or `#mods` reference comes up. If the user expects a channel and it's not visible, the user's role doesn't grant access; surface that rather than searching for a different channel.

Posting requires the "Send Messages" permission, which most users have in most channels but lose in announcement channels (`#announcements`-style). A failed post shows a small red "Slowmode" or "You don't have permission" tooltip; check before retrying.

## Verification

After sending, the message appears in the channel with a timestamp and a sending-state spinner that resolves to a delivered checkmark. If it doesn't: check for a slowmode warning, a permission error, or a connection drop (top bar shows "Reconnecting").

## Sources

Discord's official keyboard shortcuts page: https://support.discord.com/hc/en-us/articles/360045138571-Keyboard-Shortcuts. The in-app `Cmd+/` overlay is the most current reference.
