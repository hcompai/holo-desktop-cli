"""`holo acp`: stdio ACP server fronting the hai-agent-runtime binary, one agent-API session per ACP session."""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from collections import OrderedDict
from typing import Any, cast

from acp import (
    PROTOCOL_VERSION,
    AuthenticateResponse,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    RequestError,
    run_agent,
    start_tool_call,
    text_block,
    tool_content,
    update_agent_message,
    update_agent_thought,
    update_tool_call,
)
from acp.interfaces import Agent, Client
from acp.schema import (
    AgentCapabilities,
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
)
from agent_interface.agent_events import ErrorEvent, PolicyEvent, ToolResultEvent
from agp_types import TrajectoryEvent, TrajectoryStatus
from pydantic import JsonValue

from holo_desktop import __version__
from holo_desktop.agent_client.client import AgentApiClient
from holo_desktop.agent_client.events import PolicyView, parse_agent_event
from holo_desktop.agent_client.launcher import AgentDaemon, ensure_running_from_env
from holo_desktop.agent_client.session_runner import (
    DEFAULT_INTERACTIVE_IDLE_TIMEOUT_S,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TIME_S,
    Session,
    cancel_session_best_effort,
    run_turn,
)
from holo_desktop.cli.bootstrap import bootstrap_stdio

logger = logging.getLogger("holo-acp")

MAX_ACTIVE_SESSIONS = 32


class HoloAcpAgent:
    """Maps ACP sessions to agent-API sessions on the hai-agent-runtime binary."""

    _conn: Client

    def __init__(self) -> None:
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._daemon: AgentDaemon | None = None
        self._client: AgentApiClient | None = None
        self._api_lock = asyncio.Lock()
        self._cancelled: set[str] = set()

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def _api(self) -> AgentApiClient:
        if self._client is None:
            async with self._api_lock:
                if self._client is None:
                    self._daemon = await ensure_running_from_env()
                    self._client = AgentApiClient(self._daemon.base_url, self._daemon.token)
        return self._client

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(),
            agent_info=Implementation(name="holo-desktop", title="HoloDesktop CLI", version=__version__),
        )

    async def authenticate(self, method_id: str, **kwargs: Any) -> AuthenticateResponse | None:
        return AuthenticateResponse()

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        await self._api()  # fail fast if the binary cannot start
        while len(self._sessions) >= MAX_ACTIVE_SESSIONS:
            victim_id = next((sid for sid, s in self._sessions.items() if not s.lock.locked()), None)
            if victim_id is None:
                # Every slot holds an in-flight prompt; refuse rather than grow the map without bound.
                raise RequestError.internal_error(
                    {"reason": f"all {MAX_ACTIVE_SESSIONS} sessions are busy; retry once a prompt finishes"}
                )
            evicted = self._sessions.pop(victim_id)
            self._cancelled.discard(victim_id)
            await self._cancel_session(evicted)
            logger.info("evicted ACP session %s (cap=%d)", victim_id, MAX_ACTIVE_SESSIONS)
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = Session()
        return NewSessionResponse(session_id=session_id)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            self._cancelled.add(session_id)
            await self._cancel_session(session)

    async def _cancel_session(self, session: Session) -> None:
        if self._client is not None:
            await cancel_session_best_effort(self._client, session)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> PromptResponse:
        session = self._sessions.get(session_id)
        if session is None:
            raise RequestError.invalid_params({"session_id": session_id, "reason": "unknown session"})

        text = "\n".join(b.text for b in prompt if isinstance(b, TextContentBlock) and b.text).strip()
        if not text:
            raise RequestError.invalid_params({"reason": "prompt must contain non-empty text content"})

        self._cancelled.discard(session_id)
        async with session.lock:
            client = await self._api()

            async def forward(event: TrajectoryEvent) -> None:
                await self._translate(session_id, event)

            try:
                outcome = await run_turn(
                    client,
                    session,
                    text,
                    max_steps=DEFAULT_MAX_STEPS,
                    max_time_s=DEFAULT_MAX_TIME_S,
                    idle_timeout_s=DEFAULT_INTERACTIVE_IDLE_TIMEOUT_S,
                    on_event=forward,
                )
            except Exception:
                if session_id in self._cancelled:
                    self._cancelled.discard(session_id)
                    return PromptResponse(stop_reason="cancelled")
                raise

            if session_id in self._cancelled:
                self._cancelled.discard(session_id)
                return PromptResponse(stop_reason="cancelled")

            if outcome.status == TrajectoryStatus.FAILED:
                await self._conn.session_update(
                    session_id=session_id,
                    update=update_agent_message(text_block(outcome.error or "agent failed")),
                )
                return PromptResponse(stop_reason="refusal")
            if outcome.status == TrajectoryStatus.INTERRUPTED:
                return PromptResponse(stop_reason="cancelled")
            if outcome.status == TrajectoryStatus.TIMED_OUT:
                # Step/time budget exhausted; "max_turn_requests" is ACP's closest truncation signal.
                await self._conn.session_update(
                    session_id=session_id,
                    update=update_agent_message(text_block(outcome.error or "agent timed out before answering")),
                )
                return PromptResponse(stop_reason="max_turn_requests")
            await self._conn.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(outcome.answer)),
            )
            return PromptResponse(stop_reason="end_turn")

    async def _translate(self, session_id: str, event: TrajectoryEvent) -> None:
        match parse_agent_event(event):
            case PolicyEvent() as policy:
                await self._translate_policy(session_id, policy)
            case ToolResultEvent() as result:
                await self._translate_tool_result(session_id, result)
            case ErrorEvent() as error:
                await self._translate_error(session_id, error)

    async def _translate_policy(self, session_id: str, policy: PolicyEvent) -> None:
        view = PolicyView.from_event(policy)
        rationale = "\n".join(part for part in (view.note, view.thought) if part) if view is not None else ""
        if rationale:
            await self._conn.session_update(session_id=session_id, update=update_agent_thought(text_block(rationale)))
        for req in policy.tool_reqs:
            preview = ", ".join(f"{k}={v!r}" for k, v in req.args.items())[:200]
            await self._conn.session_update(
                session_id=session_id,
                update=start_tool_call(
                    req.id or "",
                    f"{req.tool_name}({preview})",
                    kind="execute",
                    status="pending",
                    raw_input=req.args,
                ),
            )

    async def _translate_tool_result(self, session_id: str, result: ToolResultEvent) -> None:
        output = _stringify(result.result)
        await self._conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                result.tool_req.id or "",
                status="completed",
                content=[tool_content(text_block(output))] if output else None,
            ),
        )

    async def _translate_error(self, session_id: str, error: ErrorEvent) -> None:
        if error.tool_req is None:
            return
        await self._conn.session_update(
            session_id=session_id,
            update=update_tool_call(
                error.tool_req.id or "",
                status="failed",
                content=[tool_content(text_block(error.error))],
            ),
        )

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        pass

    async def aclose(self) -> None:
        if self._client is not None:
            for session in list(self._sessions.values()):
                await self._cancel_session(session)
            await self._client.aclose()
        if self._daemon is not None:
            await self._daemon.aclose()


def _stringify(result: JsonValue) -> str:
    """Best-effort one-string view of a tool result so ACP hosts get something renderable."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    return str(result)


def acp() -> None:
    """Run as a stdio ACP server. Spawns the hai-agent-runtime binary on first use."""
    bootstrap_stdio("holo-acp")
    # stdout carries the ACP protocol; the notice must go to stderr only.
    print("holo acp is in beta — interfaces and behaviour may change.", file=sys.stderr, flush=True)

    async def _serve() -> None:
        agent = HoloAcpAgent()
        try:
            # acp.Agent is a structural Protocol; cast for mypy.
            await run_agent(cast(Agent, agent))
        finally:
            await agent.aclose()

    asyncio.run(_serve())
