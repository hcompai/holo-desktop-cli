---
name: Notion
description: Creating and editing pages, databases, and blocks, navigating workspaces, and using the slash menu, mentions, and quick find in Notion (web or desktop) on Windows.
publisher: H Company
version: "1.0.0"
source_url: https://www.notion.so/help/keyboard-shortcuts
license: Vendor docs
icon_url: https://api.iconify.design/skill-icons:notion-light.svg
---

Notion is a two-pane workspace: a left sidebar with workspace switcher, Favorites, Shared, Private sections (each a tree of pages); the main pane with the page content as a vertical stack of blocks. The page header has the icon, cover, title, and properties (for database pages); below it, the body is freely composable. Every meaningful interaction goes through one of three entry points: `Ctrl+P` (quick find), `/` (slash menu inside a block), or the six-dot drag handle that appears on hover at the left edge of every block.

## Shortcuts

Global: `Ctrl+P` (or `Ctrl+K`) quick find (search every page in the workspace by title). `Ctrl+N` new page in the current workspace. `Ctrl+Shift+N` new Notion window. `Ctrl+\` toggle the left sidebar. `Ctrl+[` / `Ctrl+]` back/forward in page history. `Ctrl+Shift+L` toggles dark mode.

Page-level: `Ctrl+/` opens the block action menu for the selected block(s) (move, duplicate, delete, turn into, change color). `Ctrl+D` duplicates the selected block. `Ctrl+Shift+H` cycles highlight colors on the selection. `Ctrl+B` bold, `Ctrl+I` italic, `Ctrl+U` underline, `Ctrl+E` inline code, `Ctrl+Shift+S` strikethrough. `Ctrl+K` turn selected text into a link (or paste a URL onto selected text).

Block creation: `/` at the start of an empty line opens the slash menu (most-used: `/h1`, `/h2`, `/h3`, `/todo`, `/bullet`, `/numbered`, `/toggle`, `/code`, `/table`, `/quote`, `/divider`, `/page`, `/database`, `/embed`). Markdown shortcuts also work inline: `# ` heading 1, `## ` heading 2, `- ` bullet, `[] ` checkbox, ``` code block, `> ` toggle. `Ctrl+Shift+0` through `Ctrl+Shift+9` turn the selected block into text/h1/h2/h3/bullet/numbered/todo/toggle/code.

Navigation within a page: `Tab` indents the block; `Shift+Tab` outdents. `Ctrl+A` selects the current block; `Ctrl+A` a second time selects all blocks on the page. `Ctrl+Z` undo (deep history — most operations are undoable across sessions). `Esc` exits the current block's edit mode and selects it; from selected, `Esc` again deselects. `Ctrl+Shift+arrow keys` move the selected block around the page. `Ctrl+Alt+T` expands or collapses all toggles in a toggle list.

Mentions and links: `@` opens the mention menu — type a person's name (notifies them), a page title (links and embeds preview), a date ("@today", "@next Friday"), or a reminder ("@remind tomorrow 9am"). `[[` is a faster page-link shortcut: `[[` then type to autocomplete an existing page or create a new sub-page.

## Blocks, not documents

Notion's mental model is blocks, not paragraphs. Every line is a block (paragraph, heading, list item, toggle, image, embed, database row) that can be dragged, duplicated, nested, toggled, and turned into any other type. The drag handle (six dots at the left edge, visible on hover) is the universal block grip — click to select, click-and-drag to move, click to open the block menu.

`Enter` ends one block and starts a new one of the same type (so a chain of bullets keeps making bullets). `Shift+Enter` adds a line break within the same block (the right choice for multi-line code or quotes). Knowing the difference is the difference between a clean page and a mess of partial blocks.

`Tab` inside a list or bullet indents it as a sub-item; `Shift+Tab` promotes it back. `Tab` on a top-level block does nothing visible — Notion's indent is list-only.

## Pages and databases

A page is a top-level container; sub-pages nest indefinitely. A database is a page whose properties (title, status, date, person, select, etc.) are typed and queryable; rows in a database are themselves pages with that property schema. Confusing the two is the single most common Notion mistake — adding "tasks" as bullets inside a regular page can never be filtered, sorted, or rolled up, while a database of tasks can.

Database views: `Ctrl+P` then "+ Add a view" creates filtered/sorted/grouped slices over the same data. Common patterns: Inbox = unsorted view filtered to "Status is empty", This Week = filtered to date range, By Assignee = grouped by Person property. Views never duplicate data — editing a row in one view updates it in all views. In a database peek (`Space` on a focused row), `Ctrl+Shift+K` / `Ctrl+Shift+J` step to the previous/next row's page.

For collecting structured items (tasks, meetings, ideas, contacts), default to "should this become a database?" before defaulting to bullet points. The user can always promote bullets to a database later but the conversion is lossy.

## Sharing and the publish boundary

The "Share" button at the top-right controls page access. Pages inherit permissions from their parent unless explicitly overridden. Adding a person to a sub-page is reversible; setting a page to "Share to web" makes it publicly indexable and reachable by URL — Irreversible until the user notices and toggles it off. Never enable web sharing without explicit user consent.

Inviting people via email or @-mention triggers a notification. Treat any `@person` mention the same as a Slack DM: the recipient sees it. Avoid `@`-mentioning collaborators in agent-drafted content that hasn't been confirmed.

## Deletes and the trash boundary

`Ctrl+Delete`/`Delete` or block menu → Delete moves a block to the page's history (recoverable via `Ctrl+Z` or the page's "Updates" view). Deleting a page moves it to Trash (recoverable for 30 days via the sidebar). Deleting a database row deletes the row's page, which can take an arbitrarily large attached body with it.

Deleting a database column (property) is much more destructive than it appears: the column's values across every row are wiped, recoverable via undo only if caught within the session. Confirm twice before any property delete.

## Verification

After creating or editing a block, the page renders the change in place. After moving a page, the new location reflects in the sidebar tree. After a database edit, every view that includes the row updates. If a change doesn't appear: the page may have a filter hiding the new row (check view filter chips), or the change may be pending sync (Notion has a brief save indicator at the top-right; wait for it before navigating away).

## Sources

Notion's official keyboard shortcuts reference: https://www.notion.so/help/keyboard-shortcuts. Block model and database patterns from Notion's product documentation: https://www.notion.so/help/category/data-and-databases
