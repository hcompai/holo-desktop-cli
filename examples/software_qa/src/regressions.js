// Regression switchboard. The QA demo flips these flags to simulate a developer
// shipping a bug, then shows the QA agent catching it.
//
// Activate via query param (?regression=chat-no-reply) or env (VITE_REGRESSION=...).
// The query param is stashed in sessionStorage so the flag survives SPA navigation
// and reloads within the tab. Pass ?regression= (empty) to clear it.

export const KNOWN_REGRESSIONS = [
  "chat-no-reply",
  "chat-badge-stuck",
  "auth-silent-fail",
  "auth-redirect-loop",
];

const params = new URLSearchParams(window.location.search);
const fromQuery = params.get("regression");
if (fromQuery !== null) {
  sessionStorage.setItem("regression", fromQuery);
}

const active = sessionStorage.getItem("regression") ?? import.meta.env.VITE_REGRESSION ?? "";

export function isBroken(flag) {
  return active.split(",").includes(flag);
}

export function activeRegressions() {
  return active.split(",").filter((f) => KNOWN_REGRESSIONS.includes(f));
}
