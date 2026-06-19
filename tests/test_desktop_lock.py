"""The machine-wide desktop lock serializes turns and survives separate event loops."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from holo_desktop.agent_client import desktop_lock
from holo_desktop.agent_client.desktop_lock import desktop_turn


def test_desktop_turn_serializes_overlapping_holders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_lock, "LOCK_PATH", tmp_path / "desktop.lock")
    order: list[str] = []

    async def worker(name: str) -> None:
        async with desktop_turn():
            order.append(f"enter-{name}")
            await asyncio.sleep(0.1)
            order.append(f"exit-{name}")

    async def go() -> None:
        await asyncio.gather(worker("a"), worker("b"))

    asyncio.run(go())
    # No interleaving: each holder's enter is immediately followed by its own exit.
    assert [token.split("-")[0] for token in order] == ["enter", "exit", "enter", "exit"]


def test_desktop_turn_reacquirable_across_event_loops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # holo run retries via a second asyncio.run(); the lock must not bind to the first loop.
    monkeypatch.setattr(desktop_lock, "LOCK_PATH", tmp_path / "desktop.lock")

    async def once() -> bool:
        async with desktop_turn():
            return True

    assert asyncio.run(once())
    assert asyncio.run(once())
