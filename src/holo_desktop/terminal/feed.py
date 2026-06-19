"""Rich feed for trajectory events in collapse or expand mode."""

from __future__ import annotations

from agp_types import TrajectoryEvent
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from holo_desktop.agent_client.events import PolicyView, format_event, is_policy_event, policy_view

_ARG_VALUE_MAX = 150


class LiveFeed:
    """Streams events to a console; owns a ``Live`` region in collapse mode on a terminal."""

    def __init__(self, console: Console, *, expand: bool) -> None:
        self._console = console
        self._expand = expand
        self._step = 0
        self._current: tuple[int, PolicyView] | None = None
        self._live: Live | None = None
        if not expand and console.is_terminal:
            self._live = Live(console=console, auto_refresh=False, transient=False)
            self._live.start()

    def handle(self, event: TrajectoryEvent) -> None:
        """Render one event: policy steps get a panel, everything else is a line."""
        is_policy = is_policy_event(event)
        view = policy_view(event) if is_policy else None
        if view is None:
            # An empty policy step must not leave the previous panel looking current.
            if is_policy and self._live is not None:
                self._collapse_current()
                self._live.update(Group(), refresh=True)
            line = format_event(event)
            if line:
                self._print_line(line)
            return
        self._step += 1
        if self._expand:
            self._console.print(_policy_panel(view, self._step))
            return
        if self._live is None:
            line = format_event(event)
            if line:
                self._print_line(line)
            return
        self._collapse_current()
        self._current = (self._step, view)
        self._live.update(_policy_panel(view, self._step), refresh=True)

    def close(self) -> None:
        """Stop the live region, leaving the last step's panel in scrollback."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _collapse_current(self) -> None:
        if self._current is not None:
            step, view = self._current
            self._print_line(_collapsed_row(view, step))
            self._current = None

    def _print_line(self, line: str) -> None:
        # While Live is active, console prints land above the live region.
        self._console.print(Text(line, style="dim"))


def _collapsed_row(view: PolicyView, step: int) -> str:
    """Summary row of a finished step: note first, args dropped."""
    tools = ", ".join(call.name for call in view.tool_calls)
    parts = [f"step {step} ✓"]
    if tools:
        parts.append(tools)
    rationale = view.note or view.thought
    if rationale:
        parts.append(f"· {rationale}")
    return " ".join(parts)


def _policy_panel(view: PolicyView, step: int) -> Panel:
    parts: list[RenderableType] = []
    if view.note:
        parts.append(Text(f"📝 {view.note}", style="yellow"))
    if view.thought:
        parts.append(Text(f"💭 {view.thought}", style="bright_blue"))
    for call in view.tool_calls:
        parts.append(Text(f"⚡ {call.name}", style="bright_green"))
        for key, value in call.args.items():
            text = str(value)
            if len(text) > _ARG_VALUE_MAX:
                text = f"{text[: _ARG_VALUE_MAX - 1]}…"
            parts.append(Text(f"   • {key}: {text}", style="green"))
    # Emoji stay out of the title: width disagreements leave duplicated border artifacts in some terminals.
    return Panel(
        Group(*parts),
        title=f"[bold green]step {step}[/bold green]",
        title_align="left",
        border_style="green",
        padding=(0, 2),
    )
