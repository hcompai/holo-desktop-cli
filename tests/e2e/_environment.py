from __future__ import annotations

import sys

from ._domain import EnvironmentRunner
from .environments.macos import MacOSEnvironmentRunner
from .environments.windows import WindowsEnvironmentRunner


class UnsupportedEnvironmentError(ValueError):
    """Raised when live foreground e2es are requested on an unsupported platform."""


def runner_for_platform(platform: str) -> EnvironmentRunner:
    """Return the live e2e runner for a Python platform identifier."""

    match platform:
        case "darwin":
            return MacOSEnvironmentRunner()
        case "win32":
            return WindowsEnvironmentRunner()
        case _:
            raise UnsupportedEnvironmentError(
                f"foreground live e2e tests support macOS and Windows only; got {platform!r}"
            )


def current_environment_runner() -> EnvironmentRunner:
    """Return the live e2e runner for the current host platform."""

    return runner_for_platform(sys.platform)


def current_platform_id() -> str:
    """Return the stable platform id written into e2e artifacts."""

    return sys.platform
