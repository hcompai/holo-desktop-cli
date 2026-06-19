---
name: Google Chrome
description: Navigating, managing tabs and windows, using profiles, downloads, history, and the address bar in Google Chrome.
publisher: H Company
version: "1.0.0"
source_url: https://support.google.com/chrome/answer/157179
license: Vendor docs
bundle_id: com.google.Chrome
icon_url: https://api.iconify.design/logos:chrome.svg
---

Chrome is a tab-strip browser with the omnibox (combined URL + search field) below the tab strip, the bookmarks bar optionally below that, and the page area filling the rest. The three-dot menu at the top-right holds settings, history, downloads, and extensions; almost every entry has a keyboard equivalent. Chrome's accessibility tree is partial: omnibox, tabs, and toolbar buttons are reachable, but page DOM content is best driven via `browser_exec` (selectors, JS) when available, falling back to pixel clicks for in-page interaction.

## Shortcuts

Address bar: `Cmd+L` (or `Cmd+T` for a new tab with focus already in the omnibox) focuses the omnibox. Type a URL or search query and `Return` navigates. `Cmd+Return` opens in a new background tab. Type a partial site name and press `Tab` to switch to that site's custom search. `Esc` while typing restores the original URL.

Tabs: `Cmd+T` new tab, `Cmd+W` close current tab, `Cmd+Shift+T` reopen the last closed tab (works for the last 25). `Cmd+1` through `Cmd+8` jump to the first eight tabs; `Cmd+9` jumps to the last tab regardless of position. `Cmd+Option+Right` / `Cmd+Option+Left` cycle to the next/previous tab. `Cmd+Shift+A` opens the Tab Search overlay — search by title/URL across all open tabs and windows.

Windows: `Cmd+N` new window, `Cmd+Shift+N` new Incognito window (no history, no extensions, separate cookies). `Cmd+M` minimizes, `Cmd+H` hides Chrome entirely. `Cmd+Q` quits — be cautious, this closes every Chrome window across every profile.

Navigation: `Cmd+[` / `Cmd+]` back/forward in history (or `Cmd+Left` / `Cmd+Right`). `Cmd+R` reload, `Cmd+Shift+R` hard reload (bypass cache). `Cmd+F` find in page, `Cmd+G` / `Cmd+Shift+G` next/previous match. `Space` / `Shift+Space` scroll a screenful; `Cmd+Up` / `Cmd+Down` jump to top/bottom of the page.

Bookmarks and history: `Cmd+D` bookmark current page, `Cmd+Shift+D` bookmark all open tabs into a new folder. `Cmd+Option+B` opens the Bookmark Manager. `Cmd+Y` opens the History page. `Cmd+Shift+J` opens Downloads.

Developer tools: `Cmd+Option+I` opens DevTools, `Cmd+Option+J` opens straight to the Console, `Cmd+Option+U` views page source. Useful when `browser_exec` selectors aren't grounding — inspect the live DOM first.

## Profiles and accounts

The profile chip is at the top-right of the title bar, left of the three-dot menu. Click it to switch profiles or open a new window in a different profile. Each profile has separate cookies, history, bookmarks, extensions, and signed-in Google account — this is the boundary that matters most. Confirm which profile is active before signing in, posting, or paying, because the user's "work me" and "personal me" often have access to entirely different inboxes, calendars, drives, and stored payment methods.

Incognito windows (`Cmd+Shift+N`) carry no profile, no extensions, no stored cookies. Good for one-off checks where the user wants to verify what a logged-out visitor sees, or for sensitive lookups they don't want in history. Sites still see the request and the IP; "incognito" is local-only privacy, not network privacy.

## Tab management at scale

Heavy users keep 50+ tabs across multiple windows. `Cmd+Shift+A` (Tab Search) is the single most useful shortcut for these users — never scroll the tab strip looking for one. Tab groups (right-click a tab → "Add tab to new group") collapse a cluster under a colored label, useful for batching related work but invisible from keyboard; use the mouse or skip the feature.

Pinned tabs (right-click → Pin) shrink to favicon-only and live at the leftmost slot. They survive `Cmd+Q` and reopen with the browser — useful for the user's permanent set (Gmail, Calendar) but don't pin pages the user wasn't going to keep, or they'll pollute the strip across restarts.

## The form-submit and tab-close boundaries

Forms with no draft-save (most checkout flows, comment boxes, internal tools) lose their content on tab close or accidental navigation. `Cmd+Z` in some text fields recovers, but most don't. Before closing any tab with unsaved input, confirm with `answer`. Closing the wrong tab is recoverable via `Cmd+Shift+T`, but submitted forms — checkout, "Post comment", "Send" — are Irreversible. Treat the submit button on any form with the same care as Mail's Send.

Browser autofill happily fills in real card numbers, addresses, and passwords on lookalike pages. Verify the URL in the omnibox before submitting any form with payment or credential data — the page title and visible content are insufficient signals.

## Verification

After navigation, the omnibox URL and the page content should match the target. After tab close, the tab count in the title or Tab Search reflects the change. For form submissions, look for the success page, a toast/banner, or the URL change — silent failure (the page just sits there) usually means a validation error elsewhere on the form, which `Cmd+F` for "required" or "error" can often surface.

## Sources

Google's official Chrome keyboard shortcuts: https://support.google.com/chrome/answer/157179
