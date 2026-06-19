"""Smoke test: every demo module loads, registers a well-formed Demo, and has
its hooks/verifier wired. Catches breakage where someone adds a demo to
`demos/` but forgets to put it in `registry.REGISTRY`, or strips its hooks."""

from __future__ import annotations

import pytest

from expense_report_demo.demos.registry import HOOKS, REGISTRY, VERIFIERS, get, get_hooks, get_verifier
from expense_report_demo.demos.runner import Demo

_EXPECTED_SLUGS = {"expense_report"}


def test_expected_demos_present_in_registry() -> None:
    assert set(REGISTRY) >= _EXPECTED_SLUGS, f"missing: {_EXPECTED_SLUGS - set(REGISTRY)}"


def test_every_demo_has_non_empty_pre_launch_and_metadata() -> None:
    """Pydantic enforces min_length=1 at construction; the assertions document intent
    and catch a future weakening of the schema."""
    for slug, demo in REGISTRY.items():
        assert isinstance(demo, Demo)
        assert demo.slug == slug, f"slug mismatch in registry key: {slug!r} vs demo.slug={demo.slug!r}"
        assert demo.pre_launch, f"{slug}: empty pre_launch"
        assert demo.task, f"{slug}: empty task"
        assert demo.focus_bundle_id, f"{slug}: empty focus_bundle_id"


def test_every_demo_has_hooks_registered() -> None:
    for slug in REGISTRY:
        hooks = get_hooks(slug)
        assert hooks is not None, f"{slug}: no setup/teardown registered"
        setup_fn, teardown_fn = hooks
        assert callable(setup_fn), f"{slug}: setup is not callable"
        assert callable(teardown_fn), f"{slug}: teardown is not callable"


def test_expense_report_has_verifier() -> None:
    verifier = get_verifier("expense_report")
    assert verifier is not None
    assert callable(verifier)


def test_get_returns_demo_for_known_slug() -> None:
    demo = get("expense_report")
    assert demo.slug == "expense_report"


def test_get_raises_for_unknown_slug() -> None:
    with pytest.raises(KeyError, match="unknown demo"):
        get("does_not_exist")


def test_hooks_and_verifiers_keys_subset_of_registry() -> None:
    """HOOKS must mirror REGISTRY; VERIFIERS may be sparse but never dangling."""
    assert set(HOOKS) == set(REGISTRY)
    assert set(VERIFIERS) <= set(REGISTRY)
