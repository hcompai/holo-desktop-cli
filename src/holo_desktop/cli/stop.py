"""`holo stop`: cancel any running Holo task on this machine."""

from __future__ import annotations

import sys


def stop() -> None:
    """Cancel any in-flight Holo task (the same effect as the double-Esc kill switch)."""
    from hai_agents_local.killswitch import request_stop

    request_stop()
    print("stop requested: any running Holo task will cancel", file=sys.stderr)
