"""Demo lookup + per-demo setup/teardown/verify hook registry.

REGISTRY, HOOKS, and VERIFIERS live here, keyed by the same slug. Demo modules
are purely declarative — they expose `DEMO`, `setup`, `teardown` (and
optionally `verify`) at module scope, and this file collects them. No side
effects at demo-module import time.
"""

from __future__ import annotations

from expense_report_demo.demos import expense_report
from expense_report_demo.demos.runner import Demo, DemoHook, DemoVerifier

REGISTRY: dict[str, Demo] = {
    expense_report.DEMO.slug: expense_report.DEMO,
}

HOOKS: dict[str, tuple[DemoHook, DemoHook]] = {
    expense_report.DEMO.slug: (expense_report.setup, expense_report.teardown),
}

VERIFIERS: dict[str, DemoVerifier] = {
    expense_report.DEMO.slug: expense_report.verify,
}


def get(slug: str) -> Demo:
    """Resolve `slug` to a Demo. Raises with a useful message on miss."""
    if slug not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown demo {slug!r}; known: {known}")
    return REGISTRY[slug]


def get_hooks(slug: str) -> tuple[DemoHook, DemoHook] | None:
    """Return the (setup, teardown) tuple for `slug`, or None if not registered."""
    return HOOKS.get(slug)


def get_verifier(slug: str) -> DemoVerifier | None:
    """Return the post-run verifier for `slug`, or None if the demo is unverified."""
    return VERIFIERS.get(slug)
