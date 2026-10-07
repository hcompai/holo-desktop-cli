"""Render ``agp_types.TrajectoryEvent`` as one human line for CLI feeds."""

from __future__ import annotations

import json
import logging

from agent_interface.agent_events import (
    AgentEventData,
    AnswerEvent,
    ErrorEvent,
    MessageEvent,
    PolicyEvent,
    ToolResultEvent,
)
from agp_types import TrajectoryEvent
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

_LINE_MAX = 200
_ARG_VALUE_MAX = 40

# Wire envelope ``type`` values (``TrajectoryEvent.type``). The per-step ``kind`` lives
# inside ``data`` and is owned by the typed ``AgentEventData`` union, the single source
# of truth for agent-event shapes (its ``kind`` discriminator can't drift from a constant).
AGENT_EVENT = "AgentEvent"
AGENT_ERROR_EVENT = "AgentErrorEvent"

_AGENT_EVENT_ADAPTER: TypeAdapter[AgentEventData] = TypeAdapter(AgentEventData)


def parse_agent_event_data(data: dict[str, object]) -> AgentEventData | None:
    """Validate one flattened agent-event ``data`` payload into the typed union."""
    try:
        return _AGENT_EVENT_ADAPTER.validate_python(data)
    except ValidationError:
        logger.debug("agent event did not match the public schema; skipping", exc_info=True)
        return None


def parse_agent_event(event: TrajectoryEvent) -> AgentEventData | None:
    """Typed view of an ``AgentEvent`` envelope's ``data``; ``None`` if it is not one."""
    if event.type != AGENT_EVENT or not isinstance(event.data, dict):
        return None
    return parse_agent_event_data(event.data)


def is_policy_event(event: TrajectoryEvent) -> bool:
    """True for a policy (LLM) step — the unit the feed counts and panels."""
    return isinstance(parse_agent_event(event), PolicyEvent)


def is_answer(event: TrajectoryEvent) -> bool:
    """True for the final answer event (rendered separately as the final answer)."""
    return isinstance(parse_agent_event(event), AnswerEvent)


def answer_text(event: TrajectoryEvent) -> str | None:
    """The answer string from an answer event; structured answers stringify."""
    parsed = parse_agent_event(event)
    if not isinstance(parsed, AnswerEvent):
        return None
    return parsed.answer if isinstance(parsed.answer, str) else str(parsed.answer)


def as_text(answer: str | dict[str, object] | None) -> str | None:
    """One-string view of a ``TrajectoryChanges.answer`` (structured answers stringify)."""
    if answer is None:
        return None
    return answer if isinstance(answer, str) else str(answer)


def format_event(event: TrajectoryEvent) -> str | None:
    """One-line preview, or ``None`` to skip (observations, answers, noise)."""
    if event.type != AGENT_EVENT:
        return _format_lifecycle(event)
    parsed = parse_agent_event(event)
    return _format_agent_event(parsed) if parsed is not None else None


def _trunc(text: str, limit: int = _LINE_MAX) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _format_lifecycle(event: TrajectoryEvent) -> str | None:
    if event.type == AGENT_ERROR_EVENT:
        error = event.data.get("error") if isinstance(event.data, dict) else None
        return _trunc(f"ERROR {error}") if error else "ERROR"
    return None


def _format_agent_event(event: AgentEventData) -> str | None:
    if isinstance(event, PolicyEvent):
        return _format_policy(event)
    if isinstance(event, ToolResultEvent):
        return _format_tool_result(event)
    if isinstance(event, ErrorEvent):
        return _trunc(f"ERROR {event.error}".rstrip())
    if isinstance(event, MessageEvent):
        body = " ".join(part for part in event.content if isinstance(part, str)).strip()
        caller = event.caller_id or "agent"
        return _trunc(f"{caller}: {body}") if body else None
    return None  # AnswerEvent (rendered separately), ObservationEvent, FlowEvent


class ToolCallView(BaseModel):
    """One requested tool call, as flattened on the wire."""

    model_config = ConfigDict(frozen=True)
    name: str
    args: dict[str, object]


class PolicyView(BaseModel):
    """Structured view of a flattened policy event."""

    model_config = ConfigDict(frozen=True)
    note: str | None
    thought: str | None
    tool_calls: tuple[ToolCallView, ...]

    @classmethod
    def from_event(cls, policy: PolicyEvent) -> PolicyView | None:
        """Build the view from a parsed policy event; ``None`` when there is nothing to show."""
        tool_calls = tuple(ToolCallView(name=req.tool_name, args=req.args) for req in policy.tool_reqs)
        note, thought = _split_content(policy.content)
        if thought is None and policy.reasoning_content and policy.reasoning_content.strip():
            thought = policy.reasoning_content.strip()
        if not tool_calls and note is None and thought is None:
            return None
        return cls(note=note, thought=thought, tool_calls=tool_calls)

    @classmethod
    def from_policy(cls, data: dict[str, object]) -> PolicyView | None:
        """Parse a policy event's ``data``; ``None`` when there is nothing to show."""
        try:
            policy = PolicyEvent.model_validate(data)
        except ValidationError:
            logger.warning("policy event did not match the public schema; skipping its feed entry")
            return None
        return cls.from_event(policy)


def policy_view(event: TrajectoryEvent) -> PolicyView | None:
    """The :class:`PolicyView` for a policy step, or ``None`` for any other event."""
    parsed = parse_agent_event(event)
    return PolicyView.from_event(parsed) if isinstance(parsed, PolicyEvent) else None


def _split_content(content: str | None) -> tuple[str | None, str | None]:
    """(note, thought) from the policy message content; plain text becomes the note."""
    if content is None or not content.strip():
        return None, None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content.strip(), None
    if not isinstance(parsed, dict):
        return content.strip(), None
    # Embedded tool_call duplicates tool_reqs, so only the prose fields survive.
    note = parsed.get("note")
    thought = parsed.get("thought")
    return (
        note.strip() if isinstance(note, str) and note.strip() else None,
        thought.strip() if isinstance(thought, str) and thought.strip() else None,
    )


def _format_policy(event: PolicyEvent) -> str | None:
    view = PolicyView.from_event(event)
    if view is None:
        return None
    parts = [f"{call.name}({_args_preview(call.args)})" for call in view.tool_calls]
    rationale = view.note or view.thought
    if rationale:
        parts.append(f"· {rationale}")
    return _trunc(" ".join(parts)) if parts else None


def _args_preview(args: dict[str, object]) -> str:
    return ", ".join(f"{k}={_trunc(repr(v), _ARG_VALUE_MAX)}" for k, v in args.items())


def _format_tool_result(event: ToolResultEvent) -> str | None:
    name = event.tool_req.tool_name or "tool"
    output = _result_text(event.result).strip()
    return _trunc(f"{name} → {output}") if output else f"{name} → ok"


def _result_text(result: JsonValue) -> str:
    return result if isinstance(result, str) else ""
