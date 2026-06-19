"""On-disk identity cache at `~/.holo/profile.json`."""

import contextlib
import logging
import os

from pydantic import BaseModel, ConfigDict, ValidationError

from holo_desktop.customization import HOLO_DIR

logger = logging.getLogger(__name__)

PROFILE_PATH = HOLO_DIR / "profile.json"


class Profile(BaseModel):
    """Identity cache for the signed-in user."""

    model_config = ConfigDict(extra="ignore")
    email: str
    org_id: str
    key_id: str
    key_label: str
    org_name: str | None = None


def load_profile() -> Profile | None:
    """The cached identity, or None when absent or unusable (logged, so `holo login` is the obvious fix)."""
    if not PROFILE_PATH.exists():
        return None
    try:
        return Profile.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("ignoring unreadable profile %s (%s); run `holo login` to recreate it", PROFILE_PATH, exc)
        return None
    except ValidationError as exc:
        logger.warning("ignoring malformed profile %s (%s); run `holo login` to recreate it", PROFILE_PATH, exc)
        return None


def save_profile(profile: Profile) -> None:
    """Atomic write via temp + rename so a crash mid-write leaves the prior file intact."""
    HOLO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROFILE_PATH.with_suffix(".json.tmp")
    tmp.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, PROFILE_PATH)
    # Profile holds email + org_id + key_id; tighten so other local users can't read it.
    with contextlib.suppress(OSError):
        os.chmod(PROFILE_PATH, 0o600)
