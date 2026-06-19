---
name: File Explorer
description: Searching, opening, moving, copying, renaming, and deleting files and folders in Windows File Explorer.
publisher: H Company
version: "1.0.0"
source_url: https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec
license: Vendor docs
---

File Explorer is a tabbed file browser with a left navigation pane (Home, Gallery, OneDrive, This PC, Network, and pinned Quick access folders), a main pane that shows the current folder, a command bar / ribbon at the top (New, Cut, Copy, Paste, Rename, Share, Delete, Sort, View), and the address bar (breadcrumb) showing the current path — click any segment to navigate up, or click the empty area to edit the raw path. The optional details/preview pane sits on the right. The status bar at the bottom shows item count and selection size.

## Shortcuts

Open and windows: `Win+E` opens a new File Explorer window from anywhere. `Ctrl+N` opens a new window of the current folder, `Ctrl+W` closes the current tab/window, `Ctrl+T` opens a new tab. `Ctrl+Shift+N` creates a new folder in the current directory.

Navigation: `Alt+Up` jumps to the parent folder. `Alt+Left` / `Alt+Right` step back/forward through visited folders. `Ctrl+L` (or `Alt+D`, or `F4`) focuses the address bar — type or paste an absolute path (`%USERPROFILE%\Downloads`, `C:\Temp`, a UNC path like `\\server\share`) and `Enter` to navigate. `Backspace` goes to the previously viewed folder. `Num Lock + *` expands all subfolders of the selection in the nav pane.

Views: the View menu switches between Extra large/Large/Medium/Small icons, List, Details, Tiles, and Content. `Ctrl+Shift+1` through `Ctrl+Shift+8` set those views directly; `Ctrl+Mouse wheel` scales icon size. Hidden items and file-name extensions are toggled under View → Show (no default key) — be careful, the user's machine may hide extensions by default.

Selection and inspection: arrow keys navigate within a view. `Ctrl+A` select all. `Ctrl+Click` toggles individual items into the selection; `Shift+Click` selects a range. `Space` (in the preview pane) or `Alt+P` toggles the preview pane; `Alt+Enter` opens Properties for the selection. `Enter` opens the selected item.

Renaming: `F2` renames the selected item (`Enter` commits, `Esc` cancels). `Tab` while renaming moves to the next item to rename it too. Note this differs from many macOS habits — in File Explorer `Enter`/double-click *opens*, and `F2` *renames*.

Search: `Ctrl+F` (or `F3`) focuses the search box scoped to the current folder and its subfolders. Search supports filters like `kind:`, `date:`, `size:`, and `*` wildcards.

## Clipboard and destructive operations

`Ctrl+C` copy, `Ctrl+X` cut, `Ctrl+V` paste, `Ctrl+Z` undo the last file operation (move/rename/delete), `Ctrl+Y` redo. Unlike some platforms, `Ctrl+X` is a real cut — the source is removed once you paste.

`Delete` moves the selection to the Recycle Bin (reversible: open the Recycle Bin and Restore, or `Ctrl+Z` immediately after). **`Shift+Delete` deletes immediately, bypassing the Recycle Bin — Irreversible.** Files on network drives, USB sticks, and OneDrive "online-only" items often bypass the Recycle Bin too — treat `Delete` on those as Irreversible and confirm first.

Drag-to-move within the same drive is a move (reversible with `Ctrl+Z` immediately after); drag-to-move across drives is a copy by default (hold `Shift` while dragging to force a move). Paste over a file with the same name shows a "Replace / Skip / Keep both" prompt — never click "Replace the file in the destination" without confirming with the user.

Rename is reversible only with `Ctrl+Z` immediately after; once focus moves away, the old name is gone unless tracked by File History or a Previous Version. For rename operations the user might want to undo later, confirm via `answer` first.

## Forbidden paths

Some places are off-limits regardless of the task. If the user's request points at one of these, explain the boundary and ask them to handle it directly:

- `%USERPROFILE%\.ssh\` — SSH keys and known_hosts
- `%USERPROFILE%\.aws\`, `%APPDATA%\gcloud\`, `%USERPROFILE%\.kube\` — cloud credentials
- `C:\Windows\`, `C:\Windows\System32\`, `C:\Windows\SysWOW64\` — system files
- `%LOCALAPPDATA%\Microsoft\Credentials\`, `%APPDATA%\Microsoft\Crypto\` — Windows credential and key stores
- Password-manager databases (1Password, KeePass `.kdbx`, Bitwarden vault files)
- Browser cookie stores, "Login Data", and "Local State" files under `%LOCALAPPDATA%\...\User Data\`

Reading anything under these paths is also off-limits unless the user explicitly asked for it and Holo can name a concrete, benign reason.

## Verification

After a move/copy/rename, the file actually appears at the new location, opens in the expected app, or shows the new name. A successful drag without visible confirmation has lied to agents before — refresh with `F5` and check the destination folder reflects the change before reporting success. For OneDrive folders, the per-file status icon (green check vs syncing arrows vs cloud) tells you whether the change has actually synced.

## Sources

Microsoft's Windows keyboard shortcuts reference: https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec
