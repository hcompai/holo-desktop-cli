"""`holo serve`: A2A server fronting the hai-agent-runtime binary, one agent-API session per ``contextId``."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated, Literal

import httpx
import tyro
from a2a.helpers import (
    new_data_message,
    new_task_from_user_message,
    new_text_artifact,
    new_text_message,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from agp_types import TrajectoryEvent, TrajectoryStatus
from pydantic import BaseModel, ConfigDict
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from hai_agents.local import LocalRuntime

from holo_desktop import __version__
from holo_desktop.agent_client.client import AgentApiClient
from holo_desktop.agent_client.sdk_runtime import (
    LOOPBACK_HOST,
    SpawnConfig,
    ensure_local_runtime,
    port_from_env,
)
from holo_desktop.agent_client.session_runner import (
    DEFAULT_INTERACTIVE_IDLE_TIMEOUT_S,
    SUCCESSFUL_TURN_STATUSES,
    Session,
    cancel_session_best_effort,
    run_turn,
)
from holo_desktop.settings import HoloSettings

logger = logging.getLogger(__name__)
A2A_DEFAULT_PORT = 18794
EVENT_MEDIA_TYPE = "application/vnd.holo-desktop.event+json"
MAX_RETAINED_SESSIONS = 256

# Bearer token for this A2A server, distinct from the token used against the binary behind it.
A2A_TOKEN_ENV = "HOLO_AUTH_TOKEN"

_TERMINAL_TO_A2A: dict[TrajectoryStatus, TaskState] = {
    TrajectoryStatus.COMPLETED: TaskState.TASK_STATE_COMPLETED,
    TrajectoryStatus.FAILED: TaskState.TASK_STATE_FAILED,
    TrajectoryStatus.TIMED_OUT: TaskState.TASK_STATE_FAILED,
    TrajectoryStatus.INTERRUPTED: TaskState.TASK_STATE_CANCELED,
}


class HoloTaskMetadata(BaseModel):
    """Per-turn budget overrides carried in the ``holo`` block of A2A message metadata."""

    model_config = ConfigDict(frozen=True)
    max_steps: int | None = None
    max_time_s: float | None = None

    @classmethod
    def from_message_metadata(cls, metadata: dict[str, object] | None) -> HoloTaskMetadata:
        # A2A message metadata is an untyped JSON boundary; narrow each value before trusting it.
        raw = (metadata or {}).get("holo")
        holo = raw if isinstance(raw, dict) else {}
        return cls(max_steps=_as_int(holo.get("max_steps")), max_time_s=_as_float(holo.get("max_time_s")))


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="HoloDesktop CLI",
        description=(
            "Binds to one OS window per task and drives it in the background via H Company's "
            "Holo3 VLM. Synthesized clicks and keystrokes go to the bound window only, so the "
            "user keeps their cursor and can use other apps in parallel."
        ),
        version=__version__,
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", EVENT_MEDIA_TYPE],
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="0.3.0"),
        ],
        skills=[
            AgentSkill(
                id="desktop_task",
                name="Run Desktop Task",
                description=(
                    "Carry out a natural-language task on the user's desktop: open apps, fill forms, "
                    "navigate native UI, control logged-in browsers. Turns within one conversation run "
                    "serially; the desktop is a single shared resource, so drive only one Holo task at a "
                    "time per machine."
                ),
                tags=["desktop", "computer-use", "vlm"],
                examples=[
                    "Open Safari and go to hcompany.ai",
                    "Send 'on my way' in Slack #general",
                    "Get my AWS 2FA code from Authy",
                ],
            ),
        ],
    )


class HoloExecutor(AgentExecutor):
    """Bridges A2A's task model to the agent-API binary over HTTP."""

    def __init__(self, *, model: str | None, base_url: str | None, fake: bool, settings: HoloSettings) -> None:
        self._model = model
        self._base_url = base_url
        self._fake = fake
        self._settings = settings
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._runtime: LocalRuntime | None = None
        self._client: AgentApiClient | None = None

    async def startup(self) -> None:
        # Resolved at startup (after load_holo_env) so HAI_AGENT_RUNTIME_PORT from env counts.
        # ensure_local_runtime may download the runtime on first run; keep that off the event loop.
        self._runtime = await asyncio.to_thread(
            ensure_local_runtime,
            SpawnConfig(
                port=port_from_env(settings=self._settings),
                model=self._model,
                base_url=self._base_url,
                fake=self._fake,
            ),
            settings=self._settings,
        )
        self._client = AgentApiClient(self._runtime)

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        # Stop the runtime only if this server spawned it; attached runtimes belong to their spawner.
        if self._runtime is not None and self._runtime.owned:
            await asyncio.to_thread(self._runtime.shutdown)

    @property
    def _api(self) -> AgentApiClient:
        if self._client is None:
            raise RuntimeError("HoloExecutor used before startup(); agent-API client is not ready")
        return self._client

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            if context.message is None:
                raise ValueError("RequestContext must carry either current_task or message")
            task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        task_id, context_id = task.id, task.context_id or ""

        text = (context.get_user_input() or "").strip()
        session, evicted = self._reserve_session(context_id)
        if session is None:
            await event_queue.enqueue_event(
                status_event(
                    task_id,
                    context_id,
                    TaskState.TASK_STATE_FAILED,
                    new_text_message(
                        f"server is at capacity ({MAX_RETAINED_SESSIONS} active sessions); retry shortly",
                        role=Role.ROLE_AGENT,
                        context_id=context_id,
                    ),
                )
            )
            return
        async with session.lock:
            for victim in evicted:
                await cancel_session_best_effort(self._api, victim)
            await event_queue.enqueue_event(status_event(task_id, context_id, TaskState.TASK_STATE_WORKING))
            await self._run_and_stream(session, text, task_id, context_id, event_queue, metadata=context.metadata)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raw_id = context.context_id or ""
        session = self._sessions.get(_safe_context_id(raw_id))
        if session is not None:
            await cancel_session_best_effort(self._api, session)
        task = context.current_task
        if task is not None:
            await event_queue.enqueue_event(
                status_event(task.id, task.context_id or raw_id, TaskState.TASK_STATE_CANCELED)
            )

    def _reserve_session(self, context_id: str) -> tuple[Session | None, list[Session]]:
        """Resolve the context's Session, evicting idle ones to stay at the cap; None when every slot is busy.

        Synchronous so the map mutation is atomic; the caller cancels the returned victims under its lock.
        """
        safe_id = _safe_context_id(context_id)
        existing = self._sessions.get(safe_id)
        if existing is not None:
            self._sessions.move_to_end(safe_id)
            return existing, []
        evicted: list[Session] = []
        while len(self._sessions) >= MAX_RETAINED_SESSIONS:
            victim_id = next((sid for sid, s in self._sessions.items() if not s.lock.locked()), None)
            if victim_id is None:
                return None, evicted
            evicted.append(self._sessions.pop(victim_id))
            logger.info("evicted A2A session %s (cap=%d)", victim_id, MAX_RETAINED_SESSIONS)
        session = Session()
        self._sessions[safe_id] = session
        return session, evicted

    async def _run_and_stream(
        self,
        session: Session,
        text: str,
        task_id: str,
        context_id: str,
        event_queue: EventQueue,
        *,
        metadata: dict[str, object] | None,
    ) -> None:
        meta = HoloTaskMetadata.from_message_metadata(metadata)

        async def forward(event: TrajectoryEvent) -> None:
            for a2a_event in translate_event(event, task_id, context_id):
                await event_queue.enqueue_event(a2a_event)

        try:
            outcome = await run_turn(
                self._api,
                session,
                text,
                max_steps=meta.max_steps,
                max_time_s=meta.max_time_s,
                idle_timeout_s=DEFAULT_INTERACTIVE_IDLE_TIMEOUT_S,
                on_event=forward,
            )
        except httpx.HTTPError:
            logger.warning("agent-API call failed for task %s", task_id, exc_info=True)
            await event_queue.enqueue_event(
                status_event(
                    task_id,
                    context_id,
                    TaskState.TASK_STATE_FAILED,
                    new_text_message("agent backend error", role=Role.ROLE_AGENT, context_id=context_id),
                )
            )
            return

        if outcome.status in SUCCESSFUL_TURN_STATUSES:
            await self._emit_final(event_queue, task_id, context_id, outcome.answer)
            return
        state = _TERMINAL_TO_A2A.get(outcome.status or TrajectoryStatus.FAILED, TaskState.TASK_STATE_FAILED)
        await event_queue.enqueue_event(
            status_event(
                task_id,
                context_id,
                state,
                new_text_message(
                    outcome.error or f"session {outcome.status}", role=Role.ROLE_AGENT, context_id=context_id
                ),
            )
        )

    async def _emit_final(self, event_queue: EventQueue, task_id: str, context_id: str, answer: str) -> None:
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=new_text_artifact(name="answer", text=answer),
            )
        )
        await event_queue.enqueue_event(
            status_event(
                task_id,
                context_id,
                TaskState.TASK_STATE_COMPLETED,
                new_text_message(answer, role=Role.ROLE_AGENT, context_id=context_id),
            )
        )


# A2A clients normally send a contextId (the framework assigns one when omitted); the empty case is
# degenerate. A stable sentinel keeps execute/cancel/pause on the same Session — a fresh-per-call id
# would leave cancel unable to find the in-flight turn and leak one Session per turn.
_ANONYMOUS_CONTEXT_ID = "ctx_anonymous"


def _safe_context_id(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return _ANONYMOUS_CONTEXT_ID
    if re.match(r"^[A-Za-z0-9_\-]{1,128}$", trimmed):
        return trimmed
    return f"ctx_{hashlib.sha256(trimmed.encode('utf-8')).hexdigest()[:32]}"


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def status_event(
    task_id: str,
    context_id: str,
    state: TaskState,
    message: Message | None = None,
) -> TaskStatusUpdateEvent:
    status = TaskStatus(state=state, message=message) if message else TaskStatus(state=state)
    return TaskStatusUpdateEvent(task_id=task_id, context_id=context_id, status=status)


def translate_event(event: TrajectoryEvent, task_id: str, context_id: str) -> Iterator[TaskStatusUpdateEvent]:
    """Forward a wire ``TrajectoryEvent`` as a structured A2A status-update data message."""
    yield TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(
            state=TaskState.TASK_STATE_WORKING,
            message=new_data_message(
                data=event.model_dump(mode="json"),
                media_type=EVENT_MEDIA_TYPE,
                role=Role.ROLE_AGENT,
                context_id=context_id,
            ),
        ),
    )


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"service": "holo-desktop", "status": "ok", "version": __version__})


def _lifespan(executor: HoloExecutor) -> Callable[[Starlette], AbstractAsyncContextManager[None]]:
    """Starlette lifespan: start the agent binary + client on entry, tear both down on exit."""

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        await executor.startup()
        try:
            yield
        finally:
            await executor.shutdown()

    return lifespan


def build_app(
    public_url: str,
    auth_token: str,
    cors_origins: Sequence[str] = (),
    *,
    model: str | None = None,
    base_url: str | None = None,
    fake: bool = False,
    settings: HoloSettings,
) -> Starlette:
    if not auth_token or not auth_token.strip():
        raise ValueError("auth_token must be a non-empty string")
    card = build_agent_card(public_url)
    executor = HoloExecutor(model=model, base_url=base_url, fake=fake, settings=settings)
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes: list[Route] = [Route("/health", health)]
    routes.extend(create_agent_card_routes(card))
    routes.extend(create_jsonrpc_routes(handler, "/a2a", enable_v0_3_compat=True))
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["authorization", "content-type"],
        ),
        Middleware(BearerAuthMiddleware, token=auth_token),
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=_lifespan(executor))


class BearerAuthMiddleware:
    """Require `Authorization: Bearer <token>` on every route except `/health`."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/health":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                text = value.decode("latin-1")
                if text.startswith("Bearer ") and hmac.compare_digest(text[7:], self._token):
                    await self.app(scope, receive, send)
                    return
        response = JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="holo"'},
        )
        await response(scope, receive, send)


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


def serve(
    port: int = A2A_DEFAULT_PORT,
    model: str | None = None,
    base_url: str | None = None,
    cors_origin: Annotated[
        list[str],
        tyro.conf.UseAppendAction,
        tyro.conf.arg(metavar="ORIGIN", help="Extra CORS origin to allow. Repeatable."),
    ] = [],  # noqa: B006
    log_level: Annotated[LogLevel, tyro.conf.arg(metavar="LEVEL")] = "WARNING",
    fake: Annotated[bool, tyro.conf.arg(help="Back the server with the fake agent (no model/desktop).")] = False,
) -> None:
    """Start the A2A server on 127.0.0.1, fronting the hai-agent-runtime binary."""
    import socket

    import uvicorn
    from rich.console import Console
    from rich.panel import Panel

    from holo_desktop.cli.bootstrap import bootstrap_interactive, ensure_guard_running

    settings = bootstrap_interactive(base_url=base_url, fake=fake)
    ensure_guard_running()
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    base = f"http://{LOOPBACK_HOST}:{port}"
    console = Console(stderr=True)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((LOOPBACK_HOST, port))
    except OSError as exc:
        console.print(
            Panel(
                f"could not bind [cyan]{LOOPBACK_HOST}:{port}[/cyan]\n[dim]{exc}[/dim]",
                title="[bold red]✗ bind failed[/bold red]",
                title_align="left",
                border_style="red",
                expand=False,
                padding=(0, 2),
            )
        )
        raise SystemExit(1) from exc

    supplied_token = settings.serve.auth_token
    if supplied_token is not None and not supplied_token.strip():
        console.print(f"[bold red]✗[/bold red] {A2A_TOKEN_ENV} is set but empty; unset it or supply a real value.")
        raise SystemExit(1)
    token = supplied_token or secrets.token_urlsafe(32)
    origins = tuple(cors_origin)
    console.print(f"[bold magenta]holo serve[/bold magenta] [dim]· v{__version__}[/dim]")
    console.print(f"  [cyan]{base}/a2a[/cyan]")
    if supplied_token is None:
        console.print(f"  [dim]export {A2A_TOKEN_ENV}=[/dim][yellow]{token}[/yellow]")
    console.print("  [dim]Ctrl+C to stop[/dim]")
    uvicorn.run(
        build_app(f"{base}/a2a", token, origins, model=model, base_url=base_url, fake=fake, settings=settings),
        host=LOOPBACK_HOST,
        port=port,
        log_level=log_level.lower(),
    )
