---
name: Finder
description: Searching, opening, moving, copying, renaming, and deleting files and folders in Finder.
publisher: H Company
version: "1.0.0"
bundle_id: com.apple.finder
---

Finder is a single-window-per-view file browser with a left sidebar (Favorites, iCloud, Locations, Tags) and a main pane that shifts shape based on the view. The toolbar at the top has back/forward, view switcher, group/sort, share, edit-tags, and search. The path bar (`View → Show Path Bar`, or `Opt+Cmd+P`) at the bottom shows the current directory; click any segment to navigate up. The status bar shows item count and free space.

## Shortcuts

Views: `Cmd+1` icon, `Cmd+2` list, `Cmd+3` column (best for navigating deep trees), `Cmd+4` gallery. `Cmd+J` opens View Options for the current window.

Navigation: `Cmd+↑` jumps to the parent folder, `Cmd+↓` opens the selected item (folder or file). `Cmd+[` / `Cmd+]` step back/forward through visited folders. `Cmd+Shift+G` opens "Go to Folder" — type or paste an absolute path (`~/Downloads`, `/usr/local`) and `Return` to navigate. `Cmd+Shift+.` toggles hidden files (dot-files).

Windows and tabs: `Cmd+N` new window, `Cmd+T` new tab in current window, `Cmd+W` close tab, `Cmd+Shift+N` new folder in the current directory.

Selection and inspection: arrow keys navigate within a view. `Cmd+A` select all, `Cmd+Shift+A` deselect. `Space` opens Quick Look (preview without launching the file's app); `Opt+Space` opens full-screen Quick Look. `Cmd+I` shows Get Info for the selection.

Renaming: `Return` renames the selected item (do not press `Cmd+O`, which opens it — `Return` and `Enter` mean "rename" in Finder, opposite of most other macOS apps). `Esc` cancels rename.

Search: `Cmd+F` opens search in the current window; scope chips appear under the toolbar (This Mac / Current Folder / Specific tag).

## Destructive operations

`Cmd+Delete` moves the selection to the Trash. Reversible: items in Trash can be dragged back or `Cmd+Z` (immediately after) restores. **Empty Trash (`Cmd+Shift+Delete`) is Irreversible.** `Opt+Cmd+Delete` deletes immediately, bypassing the Trash — **also Irreversible**.

Drag-to-move within the same volume is a move (reversible with `Cmd+Z` immediately after). Drag-to-move across volumes is a copy by default (hold `Cmd` while dragging to force move). Paste over a file with the same name shows a "Replace / Keep Both / Stop" prompt — never click Replace without confirming with the user.

Rename is reversible only if `Cmd+Z` is pressed immediately after; once focus moves away, the old name is gone unless tracked via Time Machine or Versions. For rename operations the user might want to undo later, confirm via `answer` first.

## Forbidden paths

Some places are off-limits regardless of the task. If the user's request points at one of these, explain the boundary and ask them to handle it directly:

- `~/.ssh/` — SSH keys and known_hosts
- `~/.aws/`, `~/.config/gcloud/`, `~/.kube/` — cloud credentials
- `~/Library/Keychains/` — system and user keychains
- Anywhere under `/System/`, `/Library/LaunchDaemons/`, `/private/etc/` — system files
- Password-manager databases (1Password.app data, Bitwarden vault files)
- Browser cookie stores and Local State files

Reading anything under these paths is also off-limits unless the user explicitly asked for it and Holo can name a concrete, benign reason.

## Verification

After a move/copy/rename, the file actually appears at the new location, opens in the expected app, or shows the new name. A successful drag without visible confirmation has lied to agents before — check the destination folder reflects the change before reporting success.

## Sources

Apple's macOS keyboard shortcuts reference: https://support.apple.com/guide/mac-help/keyboard-shortcuts-mh40543/mac
