---
name: Windows Settings
description: Navigating Windows 11 settings for Wi-Fi, Bluetooth, display, sound, focus, network, accessibility, privacy, accounts, and more in the Settings app (and legacy Control Panel).
publisher: H Company
version: "1.0.0"
source_url: https://support.microsoft.com/en-us/windows/
license: Vendor docs
---

The Settings app is a two-pane layout: a left sidebar listing top-level categories (System, Bluetooth & devices, Network & internet, Personalization, Apps, Accounts, Time & language, Gaming, Accessibility, Privacy & security, Windows Update), and a detail pane on the right that drills into sub-pages. The search box at the top of the sidebar is the single most useful entry point — most settings are faster to find by search than by browsing. Some older controls still live in the legacy **Control Panel**, which Settings deep-links to when needed.

## Opening and navigating

`Win+I` opens Settings from anywhere. `Win+A` opens Quick Settings (the fly-out for Wi-Fi, Bluetooth, volume, brightness, focus — fastest for toggles). `Win+X` opens the power-user menu (Device Manager, Disk Management, Terminal, Settings, shut-down options). The search box at the top accepts plain language ("night light", "default apps", "remove printer"); `Tab`/`Arrow keys`/`Enter` move through and open results. The back arrow at the top-left steps up through sub-pages.

For Control Panel-era settings, `Win+R` then type `control` opens the classic Control Panel; many network and advanced settings (Network Connections via `ncpa.cpl`, Sound via `mmsys.cpl`, Programs and Features via `appwiz.cpl`) are reachable this way.

## Deep links (ms-settings:)

Settings pages have stable URIs you can open from `Win+R` or the address bar — faster and less ambiguous than clicking through the tree:

- `ms-settings:network-wifi` — Wi-Fi
- `ms-settings:bluetooth` — Bluetooth & devices
- `ms-settings:display` — Display (resolution, scale, multiple monitors)
- `ms-settings:sound` — Sound (output/input devices, volume mixer)
- `ms-settings:nightlight` — Night light
- `ms-settings:quietmoments` — Focus / Do Not Disturb
- `ms-settings:windowsupdate` — Windows Update
- `ms-settings:privacy-microphone`, `ms-settings:privacy-webcam`, `ms-settings:privacy-location` — per-capability privacy
- `ms-settings:appsfeatures` — installed apps (uninstall/repair)
- `ms-settings:defaultapps` — default apps / file associations

## Layout per category

Each page is a vertical stack of grouped controls: toggles for booleans, dropdowns for enums, sliders for ranges, and chevron cells that open sub-pages. For network details (DNS, proxy, static IP, metered connection), the path is Network & internet → the active adapter → its properties. Display handles resolution, scale, refresh rate, and monitor arrangement; Personalization handles wallpaper, themes, dark/light mode, taskbar, and Start.

## Search-first workflow

Because category names are sometimes opaque ("Privacy & security" houses app permissions AND Windows Security/Defender AND BitLocker AND Device encryption), default to the search box. Examples:

- "night light" → System → Display → Night light
- "default browser" → Apps → Default apps → pick the browser → Set default
- "add a printer" → Bluetooth & devices → Printers & scanners → Add device
- "uninstall" → Apps → Installed apps → the app → ⋯ → Uninstall
- "focus" → System → Focus (and Do Not Disturb under Notifications)
- "remote desktop" → System → Remote Desktop

If a search returns nothing, the setting may live only in the legacy Control Panel, or it may be hidden/locked by the organization (see below). Surface what you found instead of guessing.

## The admin-elevation (UAC) boundary

Many changes require administrator rights and trigger a User Account Control prompt — a separate, secure dialog that dims the screen and asks to allow the change (and, for a standard account, asks for an admin password). Installing/uninstalling system software, changing the firewall, BitLocker, adding a user, editing system-wide network settings, and most Control Panel system tasks are gated this way. **Don't approve a UAC prompt or type an admin password on the user's behalf — surface the prompt and let them confirm.** Some changes also require a sign-out or restart, which Windows announces explicitly; defer to the user on timing.

## The privacy and permissions tier

Privacy & security → App permissions (Camera, Microphone, Location, etc.) gate which apps can use each capability. Toggling an app's access may require the app to be restarted to take effect. Never grant a capability on an app's behalf without the user confirming. For Holo specifically, the relevant capabilities (screen capture and input synthesis / accessibility) are usually granted at install time; if Holo isn't driving the desktop, this is the first place to check.

## Managed devices

On work or school PCs, settings can be enforced by the organization (Intune/MDM or Group Policy). A managed setting shows a "Some settings are managed by your organization" note and a greyed-out control — it cannot be changed locally. Don't fight it; report that the setting is org-managed.

## Verification

After a toggle, the change usually takes effect immediately (Wi-Fi connect, brightness, volume) — verify the new state in the pane, or check the system tray / Quick Settings indicator. Settings that need a restart show a "Restart required" badge and aren't live until the user restarts. If a change doesn't stick, it may be org-managed, require elevation that was declined, or live in a Control Panel page that overrides it.

## Sources

Microsoft Windows support: https://support.microsoft.com/en-us/windows/. The `ms-settings:` URI scheme is documented at https://learn.microsoft.com/en-us/windows/uwp/launch-resume/launch-settings-app
