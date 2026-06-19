---
name: Apple Calendar
description: Creating, editing, and managing events, invites, and recurring schedules in the Apple Calendar desktop app.
publisher: H Company
version: "1.0.0"
source_url: https://github.com/lucaperret/agent-skills
license: MIT
bundle_id: com.apple.iCal
---

Calendar is a four-pane layout: a left sidebar listing calendars (toggleable colored checkboxes), a top toolbar with the view switcher and Today button, a main grid that changes shape with the view, and a mini-month at the bottom-left for jump navigation. The toolbar's `+` button and `Cmd+N` both open the inspector for a new event; the inspector is a floating panel, not a modal, so the grid stays interactive behind it.

## Shortcuts

Navigation: `Cmd+1` day, `Cmd+2` week, `Cmd+3` month, `Cmd+4` year. `Cmd+T` jumps to today. `Shift+Cmd+T` jumps to a specific date. `Cmd+→` / `Cmd+←` moves one unit forward/back in the current view. `Cmd+F` opens search across all calendars.

Events: `Cmd+N` new event at the currently-selected time. `Cmd+E` opens edit; `Opt+Cmd+I` opens the inspector window. `Return` or `Esc` closes the open event editor. `Tab` / `Shift+Tab` cycle through fields while editing. `Cmd+I` shows info on a selected event or calendar.

Moving events without re-typing: `Ctrl+Opt+↑/↓` shifts the selected event 15 minutes earlier/later in Day or Week view (one week in Month view). `Ctrl+Opt+←/→` shifts one day earlier/later in Week or Month view.

## Creating events

The fastest path is `Cmd+N`, then type the event in natural language ("Lunch with Sam Friday at noon for 1h at Sightglass") — Calendar parses date, time, duration, and location into the right fields. Verify the parse in the inspector before committing; mis-parsed times are the most common silent failure. For absolute dates the safest input is `YYYY-MM-DD` form ("2026-07-15"); for relative dates the natural-language form is reliable ("tomorrow", "in 3 days", "next Monday"). Avoid month names in non-English locales — they may not parse.

For recurring events, set the Repeat field in the inspector. Common patterns: every weekday at the same time, every other Friday, every Tuesday for 8 weeks. The RFC 5545 RRULE syntax (`FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`) maps directly to the inspector's options.

## The invite boundary

For events with attendees, the inspector's "Add Invitees" field autocompletes from Contacts. **Once the inspector closes on an event with attendees, invitation emails go out immediately** — this is the Irreversible boundary. Always `answer` to confirm attendee list, time, location, and any video link before closing the inspector. For a private block on the user's own calendar with no attendees, closing the inspector is just a save.

Calendar invites cross the same Irreversible threshold as email: once sent, recipients are notified and the agent can't quietly take it back. If the user said "find a time" without saving, deliver candidate slots from the user's free time and let them pick before creating the event.

## Recurring events

Any edit or delete on a recurring event prompts "This Event / This and Future Events / All Events". Picking wrong here silently rewrites the user's history of past events. Default to "This Event" unless the user explicitly said the change applies to the whole series.

## Calendar selection

The "Calendar:" dropdown in the inspector defaults to the user's primary calendar, which may not be the right one (work vs personal vs shared). Check the dropdown before saving any event the user didn't explicitly attribute to a calendar. Read-only calendars (subscribed iCal feeds, holiday calendars) reject event creation — pick a writable one.

## Verification

After saving, the event appears on the grid at the expected time slot. If it doesn't: the wrong calendar may be hidden in the sidebar, the date may have parsed differently than expected, or the event may be recurring and the grid may be showing a different week.

## Sources

Apple's keyboard shortcuts for Calendar: https://support.apple.com/guide/calendar/keyboard-shortcuts-ical002/mac. Natural-language→field mapping pattern adapted from lucaperret/agent-skills (MIT): https://github.com/lucaperret/agent-skills/tree/main/skills/macos-calendar
