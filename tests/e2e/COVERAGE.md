# HoloDesktop CLI E2E Coverage

The live foreground suite is organized by desktop capability, not by app name.
Each task should prefer a deterministic system assertion over answer judging.

## Current Coverage

The PR-gated full e2e workflow runs the same task fixtures on macOS, Windows,
and the Ubuntu 22.04 X11 posture:

- Text input: foreground visible editor witness and type sentinel.
- File manager basics: create folder, copy file, open by double-click, and protected-file no-op.
- Calculator/UI readback: calculator CI smoke.
- Browser: local download.

Any fixture that does not meet the 3/3 bar on all three hosted platforms should
be removed from this suite rather than kept as CI coverage.

The Linux mappings are release-candidate coverage until three independent
hosted workflow runs qualify each task at that same 3/3 bar.

Linux maps the same product contracts to Mousepad, Thunar, KCalc, and Google
Chrome. Filesystem evaluators stay shared; KCalc uses independent AT-SPI
readback and the double-click task uses visible-window title inspection.

## OSWorld-Light Mapping

OSWorld-light has useful task families, but most are Ubuntu-app-specific
(LibreOffice, GIMP, VLC, Thunderbird, VS Code, Chromium). For native
HoloDesktop CLI release QA, we port the capability rather than the exact task:

- Chrome -> local browser download task.
- OS/files -> Finder/Explorer create, copy, protected no-op.
- LibreOffice Writer/Calc/Impress -> future native productivity tasks once a stable Mac/Windows document/spreadsheet app target is chosen.
- GIMP -> future image-edit task once it meets the hosted-runner stability bar.
- VLC/Thunderbird/VS Code -> future optional app-pack suites, not release smoke gates.

## Next Useful Additions

- Clipboard transfer between apps.
- Calendar/Reminders creation with OS-level readback.
- System Settings read-only state check with before/after assertion.
- Small spreadsheet/document edit tasks if the required apps are available on both platforms.
