---
name: Apple System Settings
description: Navigating macOS preferences for Wi-Fi, Bluetooth, displays, sound, focus, network, accessibility, privacy, and more in the System Settings app (macOS Ventura and later).
publisher: H Company
version: "1.0.0"
source_url: https://support.apple.com/guide/system-settings/welcome/mac
license: Vendor docs
bundle_id: com.apple.systempreferences
---

System Settings is a two-pane app modeled after iOS Settings: a left sidebar listing categories (Wi-Fi, Bluetooth, Network, Notifications, Sound, Focus, Screen Time, General, Appearance, Accessibility, Control Center, Siri & Spotlight, Privacy & Security, Desktop & Dock, Displays, Wallpaper, Screen Saver, Battery, Lock Screen, Touch ID & Password, Users & Groups, Passwords, Internet Accounts, Keyboard, Trackpad, Mouse, Printers & Scanners, Game Center, ...), and the detail pane on the right showing the selected category's controls. The search field at the top of the sidebar is the single most useful entry point — almost everything is faster to find by search than by browsing.

## Shortcuts

Navigation: `Cmd+L` (or `Cmd+F`) focuses the sidebar search field — type any setting name ("Wi-Fi", "Night Shift", "Trackpad speed") and the matching panes filter live. `Return` jumps to the first match. `Cmd+[` / `Cmd+]` navigate back/forward through sub-panes (useful when a category drills several levels deep, like General → Sharing → File Sharing → Options...). `Esc` exits the current sub-pane.

Window: `Cmd+W` closes the window. `Cmd+Q` quits System Settings entirely (rare — usually leave it running). `Cmd+,` opens the General category specifically (vestigial — most apps use `Cmd+,` to open *their* preferences, but System Settings already *is* preferences).

## Layout per category

Each category is a vertical stack of grouped controls: toggles for boolean settings, dropdowns for enums, sliders for ranges, and "..." or chevron-disclosure cells that open sub-panes. A button at the bottom often opens an Advanced... or Options... modal with additional rarely-used controls. The visible controls are a curated subset; if a setting isn't in the visible pane, check Advanced or scroll down (some panes have a long tail).

For network settings (Wi-Fi, VPN, DNS, Proxies), the path is Network → click the active service → Details... button → modal with TCP/IP, DNS, Proxies, Hardware tabs. Wi-Fi-specific settings (network priority, ask to join networks, captive portals) are under Wi-Fi at the top level.

For display and screen settings, Displays handles resolution/refresh/arrangement; Wallpaper handles the desktop image; Screen Saver handles the idle saver; Appearance handles light/dark mode and accent color; Control Center handles which icons appear in the menu bar.

## Search-first workflow

Because the sidebar is long and category names are sometimes opaque ("Privacy & Security" houses both microphone/camera permissions AND FileVault AND firewall AND Gatekeeper), default to `Cmd+L` and type. Examples:

- "trackpad speed" → Trackpad → Tracking speed slider
- "night shift" → Displays → Night Shift… button
- "firewall" → Network → Firewall section
- "wi-fi password" → Wi-Fi → Details on saved network → Password reveal
- "battery percent" → Control Center → Battery → "Show Percentage" toggle
- "do not disturb" → Focus → Do Not Disturb
- "screenshot" → Keyboard → Keyboard Shortcuts → Screenshots

If the user names a setting and search returns no matches, the setting may be in third-party Preference Pane (legacy) reachable only via the old System Preferences app, or it may have been removed/renamed in the current macOS version. Surface what you found instead of guessing.

## Authentication boundary

Many settings require an admin password before they apply: enabling FileVault, adding a user, changing the firewall, joining a domain, installing certificates, allowing a kernel extension. The lock icon at the bottom-left of the pane (in older macOS versions) or an in-line "Authenticate" button (current) gates these. After clicking, the system shows a password modal. Don't supply the password on the user's behalf — surface the prompt and let them type it.

Some settings require admin password AND a restart (FileVault, certain security toggles). The restart is announced explicitly via a "You'll need to restart" prompt. Defer to the user on restart timing — it interrupts whatever they're working on.

## The privacy and permissions tier

Privacy & Security → individual permission categories (Camera, Microphone, Screen Recording, Accessibility, Full Disk Access, Files and Folders, Location Services, etc.) gate which apps can use each capability. Toggling an app's access often requires the user to authenticate and may require quitting and relaunching the affected app for the change to take effect. Never toggle a permission on an app's behalf without the user confirming — granting Accessibility access to a malicious app is a system-wide compromise.

For Holo specifically: Privacy & Security → Screen Recording (for screenshots) and Accessibility (for synthesizing clicks/keys) are the permissions Holo itself needs. These are usually granted at install time, but if Holo isn't working, this is the first place to look.

## Verification

After toggling a setting, the change usually takes effect immediately (Wi-Fi join, display brightness, sound volume) — verify in the pane that the new state is shown, or check the menu bar / Control Center for the relevant indicator. For settings that require restart (FileVault, kernel extensions), the system shows a "Restart Required" badge; the change isn't live until the user restarts.

If a change doesn't appear to take effect: it may be locked by MDM (work-managed Mac), gated by Screen Time, or require an additional sub-pane confirmation. The pane usually shows a small warning text if so.

## Sources

Apple's System Settings User Guide: https://support.apple.com/guide/system-settings/welcome/mac. macOS Ventura introduced the iOS-style layout replacing the legacy System Preferences app.
