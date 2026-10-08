"""The Rich live feed: collapsed steps on a TTY, a panel per step with --expand, plain lines off a TTY."""

from __future__ import annotations

import datetime
import io
import json

from agp_types import TrajectoryEvent
from rich.console import Console

from holo_desktop import events
from holo_desktop.terminal.feed import LiveFeed


def _policy(note: str, thought: str, tool: str, args: dict[str, object]) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=events.AGENT_EVENT,
        data={
            "kind": "policy_event",
            "tool_reqs": [{"tool_name": tool, "args": args}],
            "content": json.dumps({"note": note, "thought": thought}),
        },
        timestamp=datetime.datetime.now(datetime.UTC),
    )


def _tool_result(tool: str, result: str) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=events.AGENT_EVENT,
        data={"kind": "tool_result", "tool_req": {"tool_name": tool}, "result": result},
        timestamp=datetime.datetime.now(datetime.UTC),
    )


def _console(*, terminal: bool) -> Console:
    # _environ pinned: Live consults the ambient TERM even with force_terminal=True, and rich treats any
    # FORCE_COLOR as terminal-forcing. legacy_windows pinned: Windows runners swap rounded borders for square.
    return Console(
        file=io.StringIO(),
        force_terminal=terminal,
        record=True,
        width=120 if terminal else 300,
        _environ={"TERM": "xterm-256color"} if terminal else {},
        legacy_windows=False,
    )


def test_previous_step_collapses_to_one_row_keeping_the_full_note() -> None:
    console = _console(terminal=True)
    feed = LiveFeed(console, expand=False)
    long_note = "The Cmd+Shift+G hotkey didn't work because the focus was in Cursor IDE. " * 3 + "ENDOFNOTEMARKER"
    feed.handle(_policy(long_note, "irrelevant", "click_desktop", {"element": "the dock", "x": 0.218}))
    feed.handle(_policy("second note", "second thought", "key_down_desktop", {"key": "space"}))
    feed.close()
    text = console.export_text()
    rows = [line for line in text.splitlines() if "step 1 ✓" in line]
    assert len(rows) == 1 and "click_desktop" in rows[0] and "The Cmd+Shift+G hotkey" in rows[0]
    assert "element=" not in text
    assert "ENDOFNOTEMARKER" in text
    assert "second thought" in text
    assert '"note"' not in text


def test_expand_mode_prints_a_panel_per_step() -> None:
    console = _console(terminal=False)
    feed = LiveFeed(console, expand=True)
    feed.handle(_policy("first note", "first thought", "click_desktop", {"element": "the dock icon"}))
    feed.handle(_tool_result("click_desktop", "clicked"))
    feed.handle(_policy("second note", "second thought", "key_down_desktop", {"key": "space"}))
    feed.close()
    text = console.export_text()
    assert text.count("╭") == 2
    for fragment in ("first thought", "the dock icon", "second note", "click_desktop → clicked"):
        assert fragment in text


def test_non_tty_prints_plain_lines() -> None:
    console = _console(terminal=False)
    feed = LiveFeed(console, expand=False)
    feed.handle(_policy("plain note", "plain thought", "click_desktop", {"x": 0.1}))
    feed.close()
    text = console.export_text()
    assert "plain note" in text
    assert "╭" not in text and "─" not in text
