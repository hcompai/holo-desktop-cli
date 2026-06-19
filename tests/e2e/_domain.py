from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

type MetadataScalar = str | int | float | bool | None
type MetadataLeaf = MetadataScalar | list[MetadataScalar]
type FlatMetadata = Mapping[str, MetadataLeaf]
type MetadataValue = MetadataLeaf | FlatMetadata
type Metadata = Mapping[str, MetadataValue]


class FailureCategory(StrEnum):
    """High-level phase that caused a live e2e failure."""

    SETUP = "setup"
    HOLO_COMMAND = "holo_command"
    CONFIG = "config"
    MODEL = "model"
    DRIVER = "driver"
    AGENT = "agent"
    """The evaluator ran and determined the agent did not achieve the goal
    (file empty, folder missing, wrong result). The agent's fault, not the harness's."""
    EVALUATOR = "evaluator"
    """The evaluator itself could not determine the outcome (e.g. AX read failed,
    screenshot unreadable). The harness's limitation — the run is inconclusive, not a real agent fail."""
    TASK_DESIGN = "task_design"


@dataclass(frozen=True)
class TaskCase(ABC):
    """A desktop task definition that can prepare a runnable trial."""

    id: str
    intent: str
    app_family: str
    requires: frozenset[str] = field(default_factory=frozenset)

    @abstractmethod
    def prepare(self, workspace: Path) -> PreparedTask:
        """Prepare local state and return the instruction, evaluator, and cleanup."""


@dataclass(frozen=True)
class EvaluationResult:
    """Structured result from checking the post-run desktop state."""

    passed: bool
    message: str
    failure_category: FailureCategory | None = None
    metadata: FlatMetadata = field(default_factory=dict)


class Evaluator(Protocol):
    """Checks whether a prepared task reached its expected terminal state."""

    name: str

    def evaluate(self) -> EvaluationResult: ...


@dataclass(frozen=True)
class PreparedTask:
    """Runnable task instance with generated fixtures and its evaluator."""

    case: TaskCase
    instruction: str
    workspace: Path
    evaluator: Evaluator
    metadata: FlatMetadata = field(default_factory=dict)
    cleanup: Callable[[], None] | None = None
    preserve_artifacts: Callable[[Path], None] | None = None

    def evaluate(self) -> EvaluationResult:
        return self.evaluator.evaluate()

    def preserve_final_artifacts(self, artifact_dir: Path) -> None:
        if self.preserve_artifacts is not None:
            self.preserve_artifacts(artifact_dir)

    def clean_up(self) -> None:
        if self.cleanup is not None:
            self.cleanup()


class EnvironmentRunner(Protocol):
    """Prepares and cleans up live e2e tasks for one target environment."""

    environment_id: str
    task_cases: tuple[TaskCase, ...]

    def supports(self, case: TaskCase) -> bool: ...

    def preflight(self, case: TaskCase) -> None: ...

    def prepare(self, case: TaskCase, workspace: Path) -> PreparedTask: ...

    def cleanup(self, prepared: PreparedTask | None) -> None: ...
