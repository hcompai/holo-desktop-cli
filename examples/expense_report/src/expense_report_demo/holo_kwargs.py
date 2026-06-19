"""Frozen Pydantic model for everything the runners pass to the agent runtime.

One source of truth across the CLI and the demo runner. The `task.json`
persisted by the runner serialises this model directly, so any downstream
tooling that reads those payloads gets a typed contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from expense_report_demo.session import RuntimeConfig


class HoloKwargs(BaseModel):
    """Per-task caps plus the spawn-time knobs the runtime accepts."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    max_steps: int = Field(ge=1, le=500)
    max_time_s: float = Field(gt=0.0, le=3600.0)
    model: str | None
    llm_base_url: str | None
    port: int = Field(ge=1, le=65535)
    fake: bool

    def runtime_config(self) -> RuntimeConfig:
        return RuntimeConfig(port=self.port, model=self.model, base_url=self.llm_base_url, fake=self.fake)
