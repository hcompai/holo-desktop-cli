---
name: Microsoft Outlook
description: Composing and sending mail, managing the calendar and meeting invites, and editing contacts in the classic Outlook desktop app on Windows.
publisher: H Company
version: "1.0.0"
source_url: https://support.microsoft.com/en-us/office/keyboard-shortcuts-for-outlook-3cdeb221-7ae5-4c1d-8c1d-9e63216c1efd
license: Vendor docs
icon_url: https://api.iconify.design/logos:microsoft-icon.svg
---

Classic Outlook for Windows is one app that holds Mail, Calendar, People (Contacts), and Tasks/To Do — switch modules from the navigation bar at the bottom-left (or the icon rail). Each module is a three-pane layout: the folder/navigation pane on the left, the item list in the middle, the reading pane on the right, with the ribbon across the top. The instant-search box sits above the item list. This skill targets **classic Outlook**; the "new Outlook" and Outlook on the web have a thinner, partly different shortcut set.

> Gotcha worth memorizing: in Outlook `Ctrl+F` means **Forward**, not Find. To search, focus the instant-search box with `Ctrl+E` (or `F3`).

## Switching modules

`Ctrl+1` Mail, `Ctrl+2` Calendar, `Ctrl+3` People/Contacts, `Ctrl+4` Tasks/To Do. `Ctrl+6` opens the Folder list, `Ctrl+Y` opens the folder picker to jump to any folder. `F6` / `Shift+F6` cycle focus between the panes.

## Mail

Compose and send: `Ctrl+N` new message (when in Mail), or `Ctrl+Shift+M` from anywhere in Outlook. `Ctrl+R` reply, `Ctrl+Shift+R` reply all, `Ctrl+F` forward, `Ctrl+Alt+F` forward as attachment. `Ctrl+Enter` (or `Alt+S`) sends. `Ctrl+Shift+B` opens the Address Book; `Alt+K` (or `Ctrl+K`) checks names against the directory.

Triage: arrow keys move through the list. `Ctrl+Q` marks read, `Ctrl+U` marks unread. `Insert` adds/clears a follow-up flag. `Delete` moves to Deleted Items; `Shift+Delete` deletes permanently. `Ctrl+Shift+V` moves the selected message to a folder (opens the move picker). `F9` runs Send/Receive for all accounts.

Composing: hit `Ctrl+Shift+M`, then fill To / Subject / body. Recipient autocomplete pulls from the Auto-Complete List and the directory — the first match is auto-selected, which is the single most common silent-send-to-wrong-person trap. When a name resolves to multiple people, expand the recipient chip and verify the address (especially the domain) before continuing. Signatures auto-insert from Outlook settings — leave them unless the user asked to strip them.

Sending: `Ctrl+Enter` sends immediately. **Send is Irreversible** unless the user has configured a "delay delivery" rule (not on by default). Stop after drafting, summarize recipient, subject, and one-line intent via `answer`, and wait for go-ahead. Don't repeat the body in the answer — the user can read it in the compose window. If the user said "draft" rather than "send", stop after drafting and don't propose sending until they ask.

The account/from boundary: in a profile with multiple mailboxes, the From field selects which account sends. Verify it before sending — a personal reply going out from a shared/work mailbox (or vice versa) is its own kind of wrong-recipient error. Replies default to the account the original arrived on.

## Calendar

Navigation: `Ctrl+2` to enter, then `Ctrl+Alt+1` day view, `Ctrl+Alt+2` work-week, `Ctrl+Alt+3` week, `Ctrl+Alt+4` month. `Ctrl+G` "Go to Date". `Ctrl+Left` / `Ctrl+Right` move to the previous/next day; `Alt+Up` / `Alt+Down` previous/next week.

Events: `Ctrl+Shift+A` new appointment (no attendees), `Ctrl+Shift+Q` new meeting request (with attendees). Fill subject, location, start/end, and — for meetings — the To/attendees field, then send or save.

The invite boundary: an appointment with no attendees is a private block — saving it is just a save. A **meeting request sends invitation emails the moment you click Send** — this is the Irreversible boundary. Always `answer` to confirm the attendee list, time, location, and any Teams/online-meeting link before sending. If the user said "find a time" without committing, deliver candidate slots from their free/busy and let them pick before creating the meeting.

Recurring items: editing or deleting one occurrence of a recurring series prompts "Just this one" vs "The entire series". Picking wrong rewrites the user's history. Default to "Just this one" unless the user explicitly said the change applies to the whole series.

The calendar selection: in a profile with several calendars (personal, work, shared/delegated), confirm which calendar a new event lands on before saving. Shared/delegated calendars may notify the owner or other delegates on every change.

## People (Contacts)

`Ctrl+3` to enter, `Ctrl+Shift+C` new contact (from anywhere). Fill the display name first (required), then phone/email/address. `Ctrl+S` (or `Ctrl+Enter` in the contact form) saves and closes; `Esc` cancels unsaved edits.

The account/store boundary is the most common silent failure: contacts can live in the Outlook/Exchange mailbox, in a connected account, or in the local "Contacts" folder. New contacts default to the focused account — verify before saving so a work contact doesn't land in a personal store. `Delete` removes a contact; deletion syncs to every device on that account within minutes, and removing a contact silently breaks autocomplete elsewhere. Never delete a contact without explicit user instruction.

## Search

`Ctrl+E` (or `F3`) focuses the instant-search box scoped to the current folder; the Search ribbon adds scope chips (Current Folder / Subfolders / All Mailboxes) and refiners (From, Subject, Has Attachments, date range). `Ctrl+Shift+F` opens Advanced Find for complex queries. Remember: `Ctrl+F` is Forward, so never reach for it to search.

## Verification

After sending mail, the message appears in Sent Items. After saving an event, it appears on the grid at the expected time slot — if not, the wrong calendar may be hidden in the pane, or the time may have parsed differently. After a meeting send, attendees appear with tracking status in the event. After a contact edit, the card reflects the new values and the change syncs within ~10 seconds.

## Sources

Microsoft's keyboard shortcuts for Outlook: https://support.microsoft.com/en-us/office/keyboard-shortcuts-for-outlook-3cdeb221-7ae5-4c1d-8c1d-9e63216c1efd
