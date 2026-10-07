"""Feed lines the CLI renders from wire events."""

from __future__ import annotations

import datetime
import json

from agent_interface.agent_events import AnswerEvent as PublicAnswerEvent
from agent_interface.agent_events import ErrorEvent as PublicErrorEvent
from agent_interface.agent_events import MessageEvent as PublicMessageEvent
from agent_interface.agent_events import PolicyEvent as PublicPolicyEvent
from agent_interface.agent_events import ToolRequest as PublicToolRequest
from agent_interface.agent_events import ToolResultEvent as PublicToolResultEvent
from agp_types import TrajectoryEvent
from pydantic import BaseModel

from holo_desktop import events


def _wire(model: BaseModel) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=events.AGENT_EVENT, data=model.model_dump(mode="json"), timestamp=datetime.datetime.now(datetime.UTC)
    )


def test_served_event_schemas_render() -> None:
    assert (
        events.format_event(
            _wire(PublicToolResultEvent(tool_req=PublicToolRequest(tool_name="click", id="t1"), result="done"))
        )
        == "click → done"
    )
    assert events.format_event(_wire(PublicErrorEvent(error="boom", origin="tool"))) == "ERROR boom"
    assert (
        events.format_event(_wire(PublicMessageEvent(caller_id="agent", content=["working on it"])))
        == "agent: working on it"
    )
    answer = _wire(PublicAnswerEvent(answer="final"))
    assert events.is_answer(answer) and events.answer_text(answer) == "final"
    assert events.format_event(answer) is None
    crash = TrajectoryEvent(
        type=events.AGENT_ERROR_EVENT, data={"error": "crashed"}, timestamp=datetime.datetime.now(datetime.UTC)
    )
    assert events.format_event(crash) == "ERROR crashed"


def test_policy_line_shows_tool_call_and_note_with_clamped_args() -> None:
    element = "Finder icon in the dock - blue and white smiling face icon, leftmost in the dock"
    policy = PublicPolicyEvent(
        content=json.dumps({"note": "Opening Finder via the dock.", "thought": "unused"}),
        tool_reqs=[PublicToolRequest(tool_name="click_desktop", args={"element": element})],
    )
    line = events.format_event(_wire(policy))
    assert line is not None
    assert line.startswith("click_desktop(element=") and line.endswith("· Opening Finder via the dock.")
    assert element not in line


def test_policy_falls_back_to_thought_then_reasoning() -> None:
    view = events.PolicyView.from_policy({"content": json.dumps({"thought": "Click save."})})
    assert view is not None and view.thought == "Click save."
    view = events.PolicyView.from_policy({"content": None, "reasoning_content": "the link is in the navbar"})
    assert view is not None and view.thought == "the link is in the navbar"
    assert events.PolicyView.from_policy({"content": "   ", "tool_reqs": []}) is None


def test_noise_is_skipped_and_long_lines_truncate() -> None:
    observation = TrajectoryEvent(
        type=events.AGENT_EVENT, data={"kind": "observation_event"}, timestamp=datetime.datetime.now(datetime.UTC)
    )
    assert events.format_event(observation) is None
    long = _wire(PublicToolResultEvent(tool_req=PublicToolRequest(tool_name="read", id="t1"), result="x" * 500))
    line = events.format_event(long)
    assert line is not None and len(line) <= 200 and line.endswith("…")
