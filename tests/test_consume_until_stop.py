"""consume_until_stop streams a turn and reports whether a kill-switch stop interrupted it."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from agp_types import TrajectoryStatus

from holo_desktop.agent_client.session_runner import consume_until_stop


class _FakeStream:
    """Yields a fixed event list, then either finishes (status set) or blocks forever."""

    def __init__(self, events: list[object], *, final_status: TrajectoryStatus | None, blocks: bool) -> None:
        self._events = events
        self._final_status = final_status
        self._blocks = blocks
        self.next_index = 0
        self.answer: str | dict[str, object] | None = None
        self.status: TrajectoryStatus | None = None
        self.error: str | None = None

    async def events(self):
        for event in self._events:
            self.next_index += 1
            yield event
        if self._blocks:
            await asyncio.sleep(3600)
        self.status = self._final_status


def _event() -> object:
    return SimpleNamespace(type="AgentEvent", data={"kind": "policy_event"})


async def _noop(event: object) -> None:
    return None


async def _never_fires() -> None:
    await asyncio.sleep(3600)


async def _already_fired() -> None:
    return None


async def _watcher_crashes() -> None:
    raise OSError("stop channel exploded")


def test_clean_turn_reports_not_stopped() -> None:
    async def go() -> None:
        stream = _FakeStream([_event(), _event()], final_status=TrajectoryStatus.COMPLETED, blocks=False)
        watch = asyncio.create_task(_never_fires())
        try:
            _answer, stopped = await consume_until_stop(stream, watch, on_event=_noop)
        finally:
            watch.cancel()
        assert stopped is False
        assert stream.status is TrajectoryStatus.COMPLETED

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_a_fired_watcher_reports_stopped_and_leaves_the_caller_to_react() -> None:
    async def go() -> None:
        stream = _FakeStream([_event()], final_status=None, blocks=True)
        watch = asyncio.create_task(_already_fired())
        _answer, stopped = await consume_until_stop(stream, watch, on_event=_noop)
        # consume_until_stop only reports the stop; it does not touch the stream projection itself.
        assert stopped is True
        assert stream.status is None

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_watcher_failure_is_reraised_not_mistaken_for_a_stop() -> None:
    """Bug #2: a crashed watcher must surface as an error, never silently interrupt the turn."""

    async def go() -> None:
        stream = _FakeStream([_event()], final_status=None, blocks=True)
        watch = asyncio.create_task(_watcher_crashes())
        with pytest.raises(OSError, match="stop channel exploded"):
            await consume_until_stop(stream, watch, on_event=_noop)

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))
