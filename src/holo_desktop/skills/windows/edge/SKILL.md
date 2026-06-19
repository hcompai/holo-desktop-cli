---
name: Microsoft Edge
description: Navigating, managing tabs and windows, using profiles, collections, immersive reader, downloads, and the address bar in Microsoft Edge on Windows.
publisher: H Company
version: "1.0.0"
source_url: https://support.microsoft.com/en-us/microsoft-edge/keyboard-shortcuts-in-microsoft-edge-50d3edab-30d9-c7e4-21ce-37fe2713cfac
license: Vendor docs
icon_url: https://api.iconify.design/logos:microsoft-edge.svg
---

Edge is the default Windows browser, built on Chromium: a tab-strip browser with the address bar (combined URL + search field) below the tab strip, an optional favorites bar below that, and the page area filling the rest. The right edge of the toolbar holds Collections, the Copilot/sidebar buttons, and the three-dot menu (settings, history, downloads, extensions). Because Edge is Chromium, its accessibility tree is partial — address bar, tabs, and toolbar buttons are reachable, but page DOM content is best driven via `browser_exec` (selectors, JS) when available, falling back to pixel clicks.

## Shortcuts

Address bar: `Ctrl+L` (or `Alt+D`, or `F6`) focuses the address bar; `Ctrl+T` opens a new tab with focus already there. Type a URL or query and `Enter` navigates. `Esc` while typing restores the original URL.

Tabs: `Ctrl+T` new tab, `Ctrl+W` close current tab, `Ctrl+Shift+T` reopen the last closed tab. `Ctrl+1` through `Ctrl+8` jump to the first eight tabs; `Ctrl+9` jumps to the last tab. `Ctrl+Tab` / `Ctrl+Shift+Tab` cycle next/previous tab. `Ctrl+Shift+,` (comma) toggles vertical tabs — useful when the user keeps many tabs open.

Windows: `Ctrl+N` new window, `Ctrl+Shift+N` new InPrivate window (no history, no extensions, separate cookies). `Alt+F4` closes the current window. `Ctrl+Shift+W` closes the current window with all its tabs.

Navigation: `Alt+Left` / `Alt+Right` back/forward. `Ctrl+R` (or `F5`) reload, `Ctrl+Shift+R` (or `Ctrl+F5`) hard reload. `Ctrl+F` find on page, `Ctrl+G` / `Ctrl+Shift+G` next/previous match. `Home` / `End` jump to top/bottom of the page.

Edge features: `Ctrl+Shift+Y` opens Collections (Edge's clip-and-organize panel). `F9` toggles Immersive Reader on supported article pages (strips chrome, ads, and clutter — best for long reads). The Copilot/sidebar button on the toolbar opens the side pane; there's no stable default key, so click it.

Favorites, history, downloads: `Ctrl+D` add the current page to Favorites, `Ctrl+Shift+D` add all open tabs to a new folder. `Ctrl+Shift+O` opens the Favorites manager. `Ctrl+H` opens History. `Ctrl+J` opens Downloads.

Developer tools: `F12` (or `Ctrl+Shift+I`) opens DevTools, `Ctrl+Shift+J` opens the Console, `Ctrl+U` views page source.

## Profiles and accounts

The profile chip is at the top-left of the title bar. Click it to switch profiles or open a new window in a different profile. Each profile has separate cookies, history, favorites, extensions, and signed-in Microsoft/work account — this is the boundary that matters most. Many Windows users have a personal profile and a work (Entra ID / Microsoft 365) profile that reach entirely different mailboxes, OneDrive/SharePoint, and stored payment methods. Confirm which profile is active before signing in, posting, or paying.

InPrivate windows (`Ctrl+Shift+N`) carry no profile, no extensions, no stored cookies. Good for verifying what a logged-out visitor sees, or for sensitive lookups the user doesn't want in history. Sites still see the request and the IP; InPrivate is local-only privacy, not network privacy.

## The form-submit and tab-close boundaries

Forms with no draft-save (checkout flows, comment boxes, internal tools) lose their content on tab close or accidental navigation. Before closing any tab with unsaved input, confirm with `answer`. Closing the wrong tab is recoverable via `Ctrl+Shift+T`, but submitted forms — checkout, "Post comment", "Send" — are Irreversible. Treat the submit button with the same care as an email's Send.

Edge autofill happily fills real card numbers, addresses, and passwords on lookalike pages. Verify the URL in the address bar before submitting any form with payment or credential data — the page title and visible content are insufficient signals.

## Verification

After navigation, the address bar URL and the page content should match the target. After tab close, the tab count reflects the change. For form submissions, look for the success page, a toast/banner, or the URL change — silent failure usually means a validation error elsewhere on the form, which `Ctrl+F` for "required" or "error" can often surface.

## Sources

Microsoft's official Edge keyboard shortcuts: https://support.microsoft.com/en-us/microsoft-edge/keyboard-shortcuts-in-microsoft-edge-50d3edab-30d9-c7e4-21ce-37fe2713cfac
