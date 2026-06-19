# HoloDesktop CLI E2E Coverage

The live foreground suite is organized by desktop capability, not by app name.
Each task should prefer a deterministic system assertion over answer judging.

## Current Coverage

The PR-gated full e2e workflow keeps only task fixtures that passed 3/3 on both
macOS and Windows during initial hosted-runner QA:

- Text input: foreground visible editor witness and type sentinel.
- File manager basics: create folder, copy file, and protected-file no-op.
- Calculator/UI readback: calculator CI smoke.
- Browser: local download.

Task fixtures that did not meet the 3/3 bar on both hosted platforms were
removed from this suite rather than kept as CI coverage.

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
