---
name: Apple Notes
description: Creating, reading, searching, editing, and organizing notes into folders and tags in the Apple Notes desktop app.
publisher: H Company
version: "1.0.0"
source_url: https://github.com/lucaperret/agent-skills
license: MIT
bundle_id: com.apple.Notes
---

Notes is a three-pane layout: a left sidebar with accounts (iCloud, On My Mac, Gmail) each expanding into folders and pinned tags; a middle list of notes in the selected folder (sorted by edit time by default); the editor pane on the right with the note's rich text body. The toolbar above the editor has formatting controls and a checklist/table button; `Cmd+K` and the table button are the only ones with predictable keyboard equivalents.

## Shortcuts

Navigation: `Cmd+1` accounts list, `Cmd+2` jumps focus to the notes list, `Cmd+3` focuses the editor. `Cmd+Option+F` searches across all accounts (powerful — searches body text, not just titles). `Cmd+F` finds within the current note. `Cmd+[` / `Cmd+]` move between recently-visited notes.

Notes: `Cmd+N` new note in the selected folder. `Cmd+Shift+N` new folder. `Cmd+T` opens the selected note in its own window (useful for keeping a reference open while editing another). `Cmd+Delete` deletes the selected note (goes to Recently Deleted for 30 days). `Cmd+Shift+K` adds a checklist item; `Tab` indents it.

Formatting: `Cmd+Shift+T` title, `Cmd+Shift+H` heading, `Cmd+Shift+J` subheading, `Cmd+Shift+B` body, `Cmd+Shift+M` monospaced (good for code or fixed-width content). `Cmd+B` bold, `Cmd+I` italic, `Cmd+U` underline. `Cmd+K` insert link.

Lists and tables: `Cmd+Shift+7` numbered list, `Cmd+Shift+8` bulleted list, `Cmd+Shift+9` dashed list. `Cmd+Option+T` inserts a table. Inside a table, `Tab` moves to the next cell, `Shift+Tab` to the previous, `Return` adds a row, `Option+Return` adds a line break within a cell.

## Creating notes

The first line of any note becomes its title — Notes uses it to name the note in the sidebar list. Lead with a short descriptive title, then leave a blank line, then the body. A note saved with no first line shows as "New Note" in the list, which makes it hard to find later.

For meeting notes, the convention is `Title — YYYY-MM-DD` (e.g. "Eng sync — 2026-02-17") which sorts cleanly and is unambiguous in search. For idea-capture, a single descriptive sentence as the title is fine.

Notes uses rich text by default — pasted content brings its formatting. `Cmd+Option+Shift+V` pastes with the surrounding note style (the right choice 90% of the time). `Cmd+Shift+V` pastes as match-style. Plain `Cmd+V` is almost never what the user wants for content from the web or other apps.

## Folders, accounts, and tags

The account boundary is the most common silent failure. Notes lives in three places: iCloud (syncs to all devices, shared with collaborators), On My Mac (local-only, never leaves the machine), and connected email accounts (Gmail/Exchange, syncs as IMAP folders). Adding a private note to a Gmail folder accidentally exposes it to that account's web access. Default to iCloud unless the user explicitly named another account.

Folders nest. The "All iCloud" smart folder shows every note across iCloud folders; "Notes" is the unsorted default folder within an account. New folders go under the currently-selected folder in the sidebar — pay attention to which is selected before `Cmd+Shift+N`.

Tags (`#tagname` anywhere in the body) appear in the sidebar's Tags section and can be combined into Smart Folders. Adding a `#work` tag to a personal-folder note doesn't move it but does surface it in any Smart Folder filtered on `#work`. Useful for the user; can be surprising if the agent adds tags they didn't ask for.

## The deletion boundary

`Cmd+Delete` moves the note to Recently Deleted (30-day recovery) — recoverable but invisible from the user's daily view immediately. Deleting a folder moves all its notes to Recently Deleted simultaneously, which is a much bigger blast radius than the keyboard shortcut suggests. Always confirm with `answer` before deleting anything but a single agent-created scratch note.

Locked notes (notes the user passworded via `Cmd+L`) are visible as titled rows but their bodies are inaccessible without unlocking. Don't attempt to read, edit, or paste into a locked note — the user has to unlock it with their password first.

## Verification

After creating a note, it appears at the top of the selected folder's list with the title showing the first line. After editing, the modification timestamp in the list updates immediately. If a note doesn't appear where expected: the wrong account or folder may be selected, or a Smart Folder filter may be hiding it.

## Sources

Apple's keyboard shortcuts for Notes: https://support.apple.com/guide/notes/keyboard-shortcuts-apdaaca3037f/mac. Account/folder boundary patterns adapted from lucaperret/agent-skills (MIT): https://github.com/lucaperret/agent-skills/tree/main/skills/macos-notes
