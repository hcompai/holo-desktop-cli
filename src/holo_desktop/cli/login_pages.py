"""HTML responses served on the OAuth loopback after the browser hop."""

from __future__ import annotations

_CSS = """
:root {
  color-scheme: dark;
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Inter", system-ui, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  font-family: var(--font-sans);
  color: #ffffff;
  background:
    radial-gradient(120% 80% at 50% -10%, rgba(255,255,255,0.05) 0%, transparent 55%),
    radial-gradient(80% 60% at 50% 36%, #15151a 0%, #07070a 55%, #000 100%);
  background-color: #000;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  overflow: hidden;
  position: relative;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
body::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.5 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/></svg>");
  opacity: 0.035;
  mix-blend-mode: screen;
}
main {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 28px;
  animation: fade-in 600ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
}
.mark {
  width: 96px;
  height: 96px;
  filter: drop-shadow(0 12px 32px rgba(0,0,0,0.55));
  animation: mark-pop 700ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
h1 { margin: 0; font-size: 2rem; font-weight: 600; letter-spacing: -0.025em; line-height: 1.1; }
p {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.45;
  color: rgba(255,255,255,0.66);
  max-width: 360px;
  letter-spacing: -0.005em;
}
.copy { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--pill-bg);
  border: 1px solid var(--pill-border);
  color: var(--pill-fg);
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
}
.pill svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  fill: none;
}
main[data-status="success"] {
  --pill-bg: rgba(76, 195, 138, 0.18);
  --pill-border: rgba(76, 195, 138, 0.40);
  --pill-fg: #7be8a8;
}
main[data-status="error"] {
  --pill-bg: rgba(229, 72, 77, 0.18);
  --pill-border: rgba(229, 72, 77, 0.40);
  --pill-fg: #ff8a8d;
}
@keyframes fade-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes mark-pop {
  from { opacity: 0; transform: scale(0.85); }
  to   { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  main, .mark { animation: none; }
}
"""

_MARK_SVG = (
    '<svg class="mark" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<path d="M512,0 C708.1,0 798.1,0 866.5,32.5 C924.4,60 964,99.6 991.5,157.5 '
    "C1024,225.9 1024,315.9 1024,512 C1024,708.1 1024,798.1 991.5,866.5 "
    "C964,924.4 924.4,964 866.5,991.5 C798.1,1024 708.1,1024 512,1024 "
    "C315.9,1024 225.9,1024 157.5,991.5 C99.6,964 60,924.4 32.5,866.5 "
    "C0,798.1 0,708.1 0,512 C0,315.9 0,225.9 32.5,157.5 "
    'C60,99.6 99.6,60 157.5,32.5 C225.9,0 315.9,0 512,0 Z" fill="#0d0d11"/>'
    '<g fill="#fafafc" transform="translate(105, 248) scale(22)">'
    '<path d="M24.6374 11.9998C24.6374 18.6272 19.1221 23.9998 12.3186 23.9998'
    "C5.5152 23.9998 -7.62939e-05 18.6272 -7.62939e-05 11.9998C-7.62939e-05 5.37234 "
    "5.5152 -0.000244141 12.3186 -0.000244141C19.1221 -0.000244141 24.6374 5.37234 "
    '24.6374 11.9998Z"/>'
    '<path d="M28.9336 7.42969H31.1255V10.9315H34.808V7.42969H36.9999V16.4831H34.808'
    'V12.8105H31.1255V16.4831H28.9336V7.42969Z"/>'
    "</g></svg>"
)

_ICON_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'
_ICON_X = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'


def _page(*, title: str, status: str, pill: str, headline: str, subtitle: str, icon: str) -> bytes:
    return (
        "<!doctype html>"
        '<html lang="en" data-theme="dark">'
        f'<head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Holo - {title}</title>"
        f"<style>{_CSS}</style></head>"
        f'<body><main data-status="{status}">{_MARK_SVG}'
        f'<div class="copy">'
        f'<span class="pill">{pill}{icon}</span>'
        f"<h1>{headline}</h1><p>{subtitle}</p>"
        f"</div></main></body></html>"
    ).encode()


SUCCESS_HTML = _page(
    title="Signed in",
    status="success",
    pill="Signed in",
    headline="You're connected to Holo.",
    subtitle="You can close this tab and return to your terminal.",
    icon=_ICON_CHECK,
)

ERROR_HTML = _page(
    title="Sign-in failed",
    status="error",
    pill="Sign-in failed",
    headline="Something went wrong",
    subtitle="Return to your terminal for details, then run holo login again.",
    icon=_ICON_X,
)
