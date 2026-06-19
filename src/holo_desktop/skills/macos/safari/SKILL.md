---
name: Safari
description: Navigating, searching, managing tabs and bookmarks, and using Reader Mode in the Safari browser.
publisher: H Company
version: "1.0.0"
icon_url: https://api.iconify.design/logos:safari.svg
bundle_id: com.apple.Safari
---

Safari is a single-tab-per-pane browser with the Smart Search Field (combined URL + search box) at the top, the tab bar below or above it depending on settings, and an optional sidebar for Bookmarks (`Ctrl+Cmd+1`) or Reading List (`Ctrl+Cmd+2`). Unlike Chromium browsers, Safari has a native AX tree so most page-level interactions can be driven via clicks or `browser_exec`.

## Shortcuts

Address bar and navigation: `Cmd+L` focuses the Smart Search Field — type a URL or query and `Return` navigates. `Cmd+[` / `Cmd+]` go back/forward. `Cmd+R` reloads; `Cmd+Shift+R` reloads from origin (bypasses cache). `Cmd+F` find on page. `Esc` while typing in the address bar restores the original URL.

Tabs: `Cmd+T` new tab, `Cmd+W` close tab, `Cmd+Shift+T` reopen last closed. `Cmd+1` through `Cmd+8` jump to the first 8 tabs; `Cmd+9` jumps to the last tab. `Ctrl+Tab` / `Ctrl+Shift+Tab` cycle tabs. `Cmd+Shift+\` opens the tab overview grid.

Windows: `` Cmd+` `` (backtick) switches between Safari windows. `Cmd+N` new window. `Shift+Cmd+H` returns to the home page.

Reader and reading list: `Shift+Cmd+R` toggles Reader Mode (strips chrome, ads, and most JS — best for long articles). `Shift+Cmd+D` adds the current page to Reading List. `Ctrl+Cmd+2` toggles the Reading List sidebar.

Zoom: `Cmd++` / `Cmd+-` zoom in/out; `Cmd+0` resets to default.

## Driving Safari with browser_exec

Safari supports `browser_exec` for JavaScript execution, text extraction, and DOM queries — but the first call may fail with an AppleScript permission error until "Allow JavaScript from Apple Events" is enabled in `Develop → Allow JavaScript from Apple Events`. The `browser_exec` tool handles this with the `enable_javascript_apple_events` action plus `user_has_confirmed_enabling=true`; the call quits and relaunches Safari and drops the current window binding, so the next step must re-`launch_app` or `focus_window`.

For long pages, `browser_exec` with `action="get_text"` is much cheaper than scroll-and-OCR — use it whenever the goal is "read what's on this page" rather than visual inspection. For structured data, `action="query_dom"` returns specific elements without the full page text.

Unlike Chromium browsers, **right-click in Safari web content works correctly** and surfaces the standard context menu (Inspect, Open Link in New Tab, etc.). No need to fall back to keyboard shortcuts or `browser_exec`.

## Address bar focus and the bound-window contract

`Cmd+L` focuses the Smart Search Field inside the bound Safari window without stealing user focus from whatever app the user has frontmost. Subsequent typing routes to that field. This is the canonical pattern for navigating to a known URL — prefer it over clicking links inside the page when the destination URL is already known.

## Reading List and bookmarks

Reading List is per-iCloud-account and syncs to the user's other Apple devices. `Shift+Cmd+D` saves the current page; the side effect is visible on iPhone/iPad too, so confirm before bulk-saving. Bookmarks are organized in folders accessible via the sidebar (`Ctrl+Cmd+1`); adding a bookmark requires `Cmd+D` and a folder choice in the dialog.

## Sources

Apple's keyboard shortcuts for Safari: https://support.apple.com/guide/safari/keyboard-shortcuts-cpsh003/mac
