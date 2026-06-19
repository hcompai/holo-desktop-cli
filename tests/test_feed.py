"""Behavioural tests for the Rich live event feed (collapse and expand modes)."""

from __future__ import annotations

import datetime
import io
import json

from agp_types import TrajectoryEvent
from rich.console import Console

from holo_desktop.agent_client import events
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


def _empty_policy() -> TrajectoryEvent:
    return TrajectoryEvent(
        type=events.AGENT_EVENT,
        data={"kind": "policy_event", "tool_reqs": [], "content": "   "},
        timestamp=datetime.datetime.now(datetime.UTC),
    )


def _tool_result(tool: str, result: str) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=events.AGENT_EVENT,
        data={"kind": "tool_result", "tool_req": {"tool_name": tool}, "result": result},
        timestamp=datetime.datetime.now(datetime.UTC),
    )


def _terminal_console() -> Console:
    # _environ pinned: Live consults the ambient TERM even with force_terminal=True
    # (dumb/unset TERM silently skips repaints), so shells and CI would diverge.
    # legacy_windows pinned: Windows runners lack a VT console, making rich swap
    # the rounded box borders the tests assert on for square ones.
    return Console(
        file=io.StringIO(),
        force_terminal=True,
        record=True,
        width=120,
        _environ={"TERM": "xterm-256color"},
        legacy_windows=False,
    )


def _plain_console() -> Console:
    # _environ pinned: rich 15 treats any ambient FORCE_COLOR value (even "0") as terminal-forcing.
    return Console(file=io.StringIO(), record=True, width=300, force_terminal=False, _environ={}, legacy_windows=False)


# --- collapse mode -----------------------------------------------------------


def test_current_policy_step_renders_full_panel() -> None:
    console = _terminal_console()
    feed = LiveFeed(console, expand=False)
    feed.handle(_policy("Receipt 01 processed", "Press Space next", "click_desktop", {"x": 0.45}))
    feed.close()
    text = console.export_text()
    assert "Receipt 01 processed" in text
    assert "Press Space next" in text
    assert "click_desktop" in text
    assert '"note"' not in text  # structured content is parsed, never dumped raw


def test_previous_step_collapses_to_note_first_row_with_full_wrapped_note() -> None:
    console = _terminal_console()
    feed = LiveFeed(console, expand=False)
    long_element = "Finder icon in the dock - blue and white smiling face icon, leftmost in the dock"
    long_note = "The Cmd+Shift+G hotkey didn't work because the focus was in Cursor IDE. " * 3 + "ENDOFNOTEMARKER"
    feed.handle(_policy(long_note, "irrelevant", "click_desktop", {"element": long_element, "x": 0.218}))
    feed.handle(_policy("second note", "second thought", "key_down_desktop", {"key": "space"}))
    feed.close()
    text = console.export_text()
    # Match the collapsed row, not bare "step 1": the recording also keeps every
    # Live repaint of the step-1 panel frame (overwritten in place on a real screen).
    rows = [line for line in text.splitlines() if "step 1 ✓" in line]
    assert len(rows) == 1
    (first_row,) = rows
    assert "click_desktop" in first_row
    assert "The Cmd+Shift+G hotkey" in first_row  # note starts on the same row
    assert "element=" not in text  # args are dropped from collapsed rows
    # The full note wraps into the scrollback, never cropped.
    assert "ENDOFNOTEMARKER" in text


def test_empty_policy_event_collapses_the_live_panel() -> None:
    console = _terminal_console()
    feed = LiveFeed(console, expand=False)
    feed.handle(_policy("first note", "a thought", "click", {"x": 1}))
    feed.handle(_empty_policy())
    feed.close()
    # The empty step finishes step 1: it must collapse to a row instead of
    # leaving the step-1 panel rendering as if it were still current.
    assert "step 1 ✓" in console.export_text()


def test_panel_border_has_no_emoji() -> None:
    console = _terminal_console()
    feed = LiveFeed(console, expand=False)
    feed.handle(_policy("a note", "a thought", "click", {"x": 1}))
    feed.close()
    border_lines = [line for line in console.export_text().splitlines() if "╭" in line]
    assert border_lines
    assert all("🤖" not in line for line in border_lines)


def test_tool_results_print_as_lines() -> None:
    console = _terminal_console()
    feed = LiveFeed(console, expand=False)
    feed.handle(_policy("a note", "a thought", "click", {"x": 1}))
    feed.handle(_tool_result("click", "ok at (1, 2)"))
    feed.close()
    assert "click → ok at (1, 2)" in console.export_text()


def test_non_tty_console_prints_plain_lines_without_panels() -> None:
    console = _plain_console()
    feed = LiveFeed(console, expand=False)
    feed.handle(_policy("plain note", "plain thought", "click_desktop", {"x": 0.1}))
    feed.close()
    text = console.export_text()
    assert "plain note" in text
    assert "╭" not in text
    assert "─" not in text


# --- expand mode -------------------------------------------------------------


def test_expand_mode_prints_full_panel_per_step() -> None:
    console = _plain_console()
    feed = LiveFeed(console, expand=True)
    feed.handle(_policy("first full note", "first full thought", "click_desktop", {"element": "the dock icon"}))
    feed.handle(_tool_result("click_desktop", "clicked"))
    feed.handle(_policy("second full note", "second full thought", "key_down_desktop", {"key": "space"}))
    feed.close()
    text = console.export_text()
    assert text.count("╭") == 2, "every policy step gets its own panel"
    for fragment in (
        "first full note",
        "first full thought",
        "the dock icon",
        "second full note",
        "second full thought",
        "click_desktop → clicked",
    ):
        assert fragment in text
