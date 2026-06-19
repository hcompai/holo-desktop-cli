"""Unit tests for the shared CLI event formatter (pure functions over wire events)."""

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

from holo_desktop.agent_client import events


def _agent_event(kind: str, **data: object) -> TrajectoryEvent:
    return TrajectoryEvent(
        type=events.AGENT_EVENT,
        data={"kind": kind, **data},
        timestamp=datetime.datetime.now(datetime.UTC),
    )


def _from_model(model: BaseModel) -> TrajectoryEvent:
    """Wrap a vendored agent-event model as it arrives on the wire (its own ``kind`` included)."""
    return TrajectoryEvent(
        type=events.AGENT_EVENT,
        data=model.model_dump(mode="json"),
        timestamp=datetime.datetime.now(datetime.UTC),
    )


def _lifecycle_event(type_: str, **data: object) -> TrajectoryEvent:
    return TrajectoryEvent(type=type_, data=dict(data), timestamp=datetime.datetime.now(datetime.UTC))


# --- answers ---------------------------------------------------------------


def test_answer_event_is_detected_and_extracted() -> None:
    event = _agent_event("answer_event", answer="all done")
    assert events.is_answer(event)
    assert events.answer_text(event) == "all done"
    assert events.format_event(event) is None  # rendered separately, never as a feed line


def test_structured_answer_stringifies() -> None:
    event = _agent_event("answer_event", answer={"result": 42})
    assert events.answer_text(event) == "{'result': 42}"


def test_non_answer_events_are_not_answers() -> None:
    assert not events.is_answer(_agent_event("policy_event"))
    assert not events.is_answer(_lifecycle_event("AgentStartedEvent"))


def test_as_text_passes_strings_and_stringifies_dicts() -> None:
    assert events.as_text(None) is None
    assert events.as_text("plain") == "plain"
    assert events.as_text({"k": "v"}) == "{'k': 'v'}"


# --- per-kind formatting ----------------------------------------------------


def test_policy_event_renders_tool_calls_and_rationale() -> None:
    event = _agent_event(
        "policy_event",
        tool_reqs=[{"tool_name": "click", "args": {"x": 10, "y": 20}}],
        content="Clicking the save button",
    )
    line = events.format_event(event)
    assert line is not None
    assert "click(x=10, y=20)" in line
    assert "Clicking the save button" in line


def test_policy_event_with_structured_json_content_renders_note_not_json() -> None:
    content = json.dumps(
        {
            "note": "Receipt 01 processed: $186.93, food.",
            "thought": "Press Space to open QuickLook.",
            "tool_call": {"tool_name": "key_down_desktop", "key": "space"},
        }
    )
    event = _agent_event(
        "policy_event",
        tool_reqs=[{"tool_name": "key_down_desktop", "args": {"key": "space"}}],
        content=content,
    )
    line = events.format_event(event)
    assert line == "key_down_desktop(key='space') · Receipt 01 processed: $186.93, food."


def test_policy_event_structured_content_without_note_falls_back_to_thought() -> None:
    event = _agent_event(
        "policy_event",
        tool_reqs=[{"tool_name": "click", "args": {"x": 1}}],
        content=json.dumps({"thought": "Click the save button."}),
    )
    assert events.format_event(event) == "click(x=1) · Click the save button."


def test_from_policy_extracts_note_thought_and_tool_calls() -> None:
    view = events.PolicyView.from_policy(
        {
            "kind": "policy_event",
            "tool_reqs": [{"tool_name": "click", "args": {"x": 1, "y": 2}}],
            "content": json.dumps({"note": "a note", "thought": "a thought"}),
        }
    )
    assert view is not None
    assert view.note == "a note"
    assert view.thought == "a thought"
    assert [(c.name, c.args) for c in view.tool_calls] == [("click", {"x": 1, "y": 2})]


def test_from_policy_parses_typed_policy_event() -> None:
    # Build the payload from the vendored schema so this test fails loudly if the
    # served PolicyEvent shape drifts on the next hai-agent-api bump.
    payload = PublicPolicyEvent(
        content=json.dumps({"note": "a note", "thought": "a thought"}),
        tool_reqs=[PublicToolRequest(tool_name="click", args={"x": 1})],
    ).model_dump()
    view = events.PolicyView.from_policy(payload)
    assert view is not None
    assert view.note == "a note"
    assert view.thought == "a thought"
    assert [(c.name, c.args) for c in view.tool_calls] == [("click", {"x": 1})]


def test_from_policy_uses_reasoning_content_as_thought_fallback() -> None:
    view = events.PolicyView.from_policy(
        {
            "kind": "policy_event",
            "tool_reqs": [{"tool_name": "click", "args": {}}],
            "content": None,
            "reasoning_content": "the link is in the navbar",
        }
    )
    assert view is not None
    assert view.note is None
    assert view.thought == "the link is in the navbar"


def test_from_policy_non_json_content_becomes_note() -> None:
    view = events.PolicyView.from_policy({"content": "Clicking the save button"})
    assert view is not None
    assert view.note == "Clicking the save button"
    assert view.thought is None
    assert view.tool_calls == ()


def test_from_policy_empty_event_returns_none() -> None:
    assert events.PolicyView.from_policy({}) is None
    assert events.PolicyView.from_policy({"content": "   ", "tool_reqs": []}) is None


def test_policy_one_liner_clamps_long_arg_values() -> None:
    element = "Finder icon in the dock - blue and white smiling face icon, leftmost in the dock"
    event = _agent_event(
        "policy_event",
        tool_reqs=[{"tool_name": "click_desktop", "args": {"element": element, "x": 0.218}}],
        content=json.dumps({"note": "Opening Finder via the dock."}),
    )
    line = events.format_event(event)
    assert line is not None
    assert "Opening Finder via the dock." in line  # note survives despite the long element
    assert element not in line  # arg values are clamped, never shown in full
    assert "Finder icon in the dock" in line


def test_tool_result_event_renders_name_and_output() -> None:
    event = _agent_event("tool_result", tool_req={"tool_name": "click"}, result="ok at (10, 20)")
    assert events.format_event(event) == "click → ok at (10, 20)"


def test_tool_result_without_output_renders_ok() -> None:
    event = _agent_event("tool_result", tool_req={"tool_name": "click"}, result="")
    assert events.format_event(event) == "click → ok"


def test_error_event_renders_error_line() -> None:
    line = events.format_event(_agent_event("error_event", error="window vanished", origin="tool"))
    assert line == "ERROR window vanished"


def test_message_event_renders_caller_and_body() -> None:
    event = _agent_event("message_event", caller_id="agent", content=["On it."])
    assert events.format_event(event) == "agent: On it."


def test_empty_message_event_renders_nothing() -> None:
    assert events.format_event(_agent_event("message_event", caller_id="agent", content=[])) is None


def test_observation_events_are_skipped() -> None:
    assert events.format_event(_agent_event("observation_event", text="a screen")) is None


# --- vendored-schema contract ----------------------------------------------
# These build events straight from the hai-agent-api models, so a kind-string or
# field drift on the next bump fails here instead of silently dropping feed lines.


def test_tool_result_built_from_vendored_schema_renders() -> None:
    event = _from_model(PublicToolResultEvent(tool_req=PublicToolRequest(tool_name="click", id="t1"), result="done"))
    assert events.format_event(event) == "click → done"


def test_error_built_from_vendored_schema_renders() -> None:
    event = _from_model(PublicErrorEvent(error="boom", origin="tool"))
    assert events.format_event(event) == "ERROR boom"


def test_message_built_from_vendored_schema_renders() -> None:
    event = _from_model(PublicMessageEvent(caller_id="agent", content=["working on it"]))
    assert events.format_event(event) == "agent: working on it"


def test_answer_built_from_vendored_schema_is_detected() -> None:
    event = _from_model(PublicAnswerEvent(answer="final"))
    assert events.is_answer(event)
    assert events.answer_text(event) == "final"


# --- lifecycle events -------------------------------------------------------


def test_agent_error_lifecycle_event_renders() -> None:
    assert events.format_event(_lifecycle_event(events.AGENT_ERROR_EVENT, error="crashed")) == "ERROR crashed"


def test_quiet_lifecycle_events_render_nothing() -> None:
    assert events.format_event(_lifecycle_event("AgentStartedEvent")) is None
    assert events.format_event(_lifecycle_event("AgentCompletionEvent")) is None


# --- truncation --------------------------------------------------------------


def test_long_lines_truncate_with_ellipsis() -> None:
    event = _agent_event("tool_result", tool_req={"tool_name": "read"}, result="x" * 500)
    line = events.format_event(event)
    assert line is not None
    assert len(line) <= 200
    assert line.endswith("…")
