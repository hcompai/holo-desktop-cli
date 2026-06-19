---
name: Google Chrome
description: Navigating, managing tabs and windows, using profiles, downloads, history, and the address bar in Google Chrome on Windows.
publisher: H Company
version: "1.0.0"
source_url: https://support.google.com/chrome/answer/157179
license: Vendor docs
icon_url: https://api.iconify.design/logos:chrome.svg
---

Chrome is a tab-strip browser with the omnibox (combined URL + search field) below the tab strip, the bookmarks bar optionally below that, and the page area filling the rest. The three-dot menu at the top-right holds settings, history, downloads, and extensions; almost every entry has a keyboard equivalent. Chrome's accessibility tree is partial: omnibox, tabs, and toolbar buttons are reachable, but page DOM content is best driven via `browser_exec` (selectors, JS) when available, falling back to pixel clicks for in-page interaction.

## Shortcuts

Address bar: `Ctrl+L` (or `Alt+D`, or `F6`) focuses the omnibox; `Ctrl+T` opens a new tab with focus already there. Type a URL or search query and `Enter` navigates. `Alt+Enter` opens the typed text in a new tab. `Esc` while typing restores the original URL.

Tabs: `Ctrl+T` new tab, `Ctrl+W` close current tab, `Ctrl+Shift+T` reopen the last closed tab (works for the last 25). `Ctrl+1` through `Ctrl+8` jump to the first eight tabs; `Ctrl+9` jumps to the last tab regardless of position. `Ctrl+Tab` / `Ctrl+Shift+Tab` (or `Ctrl+PgDn` / `Ctrl+PgUp`) cycle to the next/previous tab. Tab Search is the dropdown chevron at the right end of the tab strip — click it and type to search titles/URLs across all open tabs and windows.

Windows: `Ctrl+N` new window, `Ctrl+Shift+N` new Incognito window (no history, no extensions, separate cookies). `Alt+F4` closes the current window; the three-dot menu → Exit (or `Ctrl+Shift+W` to close all tabs in the window) quits. Be cautious — Exit closes every Chrome window across every profile.

Navigation: `Alt+Left` / `Alt+Right` back/forward in history. `Ctrl+R` (or `F5`) reload, `Ctrl+Shift+R` (or `Ctrl+F5`) hard reload (bypass cache). `Ctrl+F` find in page, `Ctrl+G` / `Ctrl+Shift+G` (or `F3` / `Shift+F3`) next/previous match. `Space` / `Shift+Space` scroll a screenful; `Home` / `End` jump to top/bottom of the page.

Bookmarks and history: `Ctrl+D` bookmark current page, `Ctrl+Shift+D` bookmark all open tabs into a new folder. `Ctrl+Shift+O` opens the Bookmark Manager. `Ctrl+H` opens History. `Ctrl+J` opens Downloads.

Developer tools: `F12` (or `Ctrl+Shift+I`) opens DevTools, `Ctrl+Shift+J` opens straight to the Console, `Ctrl+U` views page source. Useful when `browser_exec` selectors aren't grounding — inspect the live DOM first.

## Profiles and accounts

The profile chip is at the top-right of the title bar, left of the three-dot menu. Click it to switch profiles or open a new window in a different profile. Each profile has separate cookies, history, bookmarks, extensions, and signed-in Google account — this is the boundary that matters most. Confirm which profile is active before signing in, posting, or paying, because the user's "work me" and "personal me" often have access to entirely different inboxes, calendars, drives, and stored payment methods.

Incognito windows (`Ctrl+Shift+N`) carry no profile, no extensions, no stored cookies. Good for one-off checks where the user wants to verify what a logged-out visitor sees, or for sensitive lookups they don't want in history. Sites still see the request and the IP; "incognito" is local-only privacy, not network privacy.

## Tab management at scale

Heavy users keep 50+ tabs across multiple windows. The Tab Search dropdown (chevron at the right end of the tab strip) is the single most useful tool for these users — never scroll the tab strip looking for one. Tab groups (right-click a tab → "Add tab to new group") collapse a cluster under a colored label, useful for batching related work but invisible from keyboard; use the mouse or skip the feature.

Pinned tabs (right-click → Pin) shrink to favicon-only and live at the leftmost slot. They survive Exit and reopen with the browser — useful for the user's permanent set (Gmail, Calendar) but don't pin pages the user wasn't going to keep, or they'll pollute the strip across restarts.

## The form-submit and tab-close boundaries

Forms with no draft-save (most checkout flows, comment boxes, internal tools) lose their content on tab close or accidental navigation. `Ctrl+Z` in some text fields recovers, but most don't. Before closing any tab with unsaved input, confirm with `answer`. Closing the wrong tab is recoverable via `Ctrl+Shift+T`, but submitted forms — checkout, "Post comment", "Send" — are Irreversible. Treat the submit button on any form with the same care as an email's Send.

Browser autofill happily fills in real card numbers, addresses, and passwords on lookalike pages. Verify the URL in the omnibox before submitting any form with payment or credential data — the page title and visible content are insufficient signals.

## Verification

After navigation, the omnibox URL and the page content should match the target. After tab close, the tab count reflects the change. For form submissions, look for the success page, a toast/banner, or the URL change — silent failure (the page just sits there) usually means a validation error elsewhere on the form, which `Ctrl+F` for "required" or "error" can often surface.

## Sources

Google's official Chrome keyboard shortcuts: https://support.google.com/chrome/answer/157179
