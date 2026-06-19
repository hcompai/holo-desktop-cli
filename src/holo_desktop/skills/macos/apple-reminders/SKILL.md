---
name: Apple Reminders
description: Creating, editing, completing, and organizing reminders, sublists, and tags in the Apple Reminders desktop app.
publisher: H Company
version: "1.0.0"
source_url: https://github.com/lucaperret/agent-skills
license: MIT
bundle_id: com.apple.reminders
---

Reminders is a two-pane layout: a left sidebar with smart lists (Today, Scheduled, All, Flagged, Completed), user lists, and shared lists; a main pane showing the selected list as a vertical checklist. Each item is a row with a circle checkbox on the left, the title, optional details (date, time, location, notes, tags), and a small `i` info button on the right that opens the inspector. The compose row at the bottom of the main pane creates new items inline.

## Shortcuts

Navigation: `Cmd+1` Today, `Cmd+2` Scheduled, `Cmd+3` All, `Cmd+4` Flagged, `Cmd+5` Completed. `Cmd+L` jumps to "All Lists". `Cmd+F` opens search across all lists. `Tab` / `Shift+Tab` cycle between sidebar and main pane.

Items: `Cmd+N` new reminder in the current list. `Cmd+Shift+N` new list. `Cmd+I` open inspector for the selected item. `Return` to edit the title inline; `Esc` to commit. `Space` toggles the checkbox on the selected item. `Cmd+Delete` deletes the selected item (no undo dialog — gone instantly).

Organization: `Tab` while editing indents an item into a sublist of the row above; `Shift+Tab` outdents. Drag items up/down or use `Cmd+Up` / `Cmd+Down` to reorder. `Cmd+Shift+F` flags an item (or `Shift+click` the circle to flag without completing).

## Creating reminders

The fastest path is `Cmd+N`, then type in natural language: "Pay rent tomorrow at 9am". Reminders parses date, time, and recurrence into the right fields. The "Remind me on a day" / "Remind me at a location" suggestions appear above the keyboard as small chips — `Tab` to accept the highlighted one, `Return` to commit without dates.

For absolute dates the safest input is `YYYY-MM-DD` form ("2026-07-15"); for relative dates the natural-language form is reliable ("tomorrow", "in 3 days", "next Monday at 9am"). Avoid month names in non-English locales — they may not parse.

For recurring reminders, set the Repeat field in the inspector (`Cmd+I`). Common patterns: daily, weekly on weekdays, monthly on the 1st, custom (every 2 weeks on Tuesday). Recurrence stays on the item until completed or removed; completing a recurring reminder generates the next instance automatically.

## Lists and tags

The "List:" dropdown in the inspector defaults to the currently-selected list. Verify before saving any reminder the user didn't explicitly attribute to a list — adding "buy milk" while focused on a Work list silently pollutes it. Use `Cmd+Shift+N` to create a new list if none of the existing ones fit; default to the user's "Reminders" list otherwise.

Tags (`#tagname` in the title or notes) work across lists. Click a tag in the sidebar's "Tags" section to filter all reminders system-wide. Tags can't be created from the inspector — type them inline in the title for them to register.

Shared lists (cloud icon next to the list name in the sidebar) notify other members on every change. Adding an item to a shared list is Irreversible in the social sense: collaborators see the notification immediately. Confirm with the user before adding to a shared list they didn't explicitly name.

## The completion boundary

Completing a one-off reminder moves it to the Completed smart list — recoverable, but it disappears from the user's daily view immediately. Completing a recurring reminder advances the schedule and the previous instance is permanently gone. Don't complete reminders the user hasn't explicitly said are done; "I'll do it later" is not "mark as done".

Deletions (`Cmd+Delete` or right-click → Delete) are instant with no undo dialog. Reminders has a 30-day Recently Deleted recovery via the sidebar, but a deleted recurring reminder takes its whole schedule with it. Confirm with `answer` before any delete.

## Verification

After saving, the item appears in the chosen list with the expected date/time chip below the title. If it doesn't: the wrong list may be focused, the date may have parsed differently than expected (Reminders silently drops mis-parsed dates rather than erroring), or the item may have landed in a sublist of whatever was above it.

## Sources

Apple's keyboard shortcuts for Reminders: https://support.apple.com/guide/reminders/keyboard-shortcuts-rmddff8babb6/mac. Natural-language→field mapping pattern adapted from lucaperret/agent-skills (MIT): https://github.com/lucaperret/agent-skills/tree/main/skills/macos-reminders
