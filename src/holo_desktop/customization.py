"""User state in ~/.holo/: agents.md, memories, rules, skills, settings.json."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import re
import threading
from importlib import resources
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from agent_interface.specs.skill import Skill
from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

HOLO_DIR = Path.home() / ".holo"
AGENTS_PATH = HOLO_DIR / "agents.md"
MEMORIES_PATH = HOLO_DIR / "memories.md"
HOLO_MEMORIES_PATH = HOLO_DIR / "holo-memories.md"
RULES_PATH = HOLO_DIR / "rules.md"
SKILLS_DIR = HOLO_DIR / "skills"
SETTINGS_PATH = HOLO_DIR / "settings.json"

SKILL_DESCRIPTION_MAX_CHARS = 280
CUSTOMIZATION_MAX_BYTES = 128 * 1024

# Hosts Holo desktop can actually drive; Linux has no native desktop driver.
HostOs = Literal["macos", "windows"]

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
# AgentSkill.name validator: lowercase alphanumerics separated by single hyphens.
_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_KEBAB_SCRUB = re.compile(r"[^a-z0-9]+")


def ensure_holo_dir() -> Path:
    """Create ``~/.holo`` owner-only (0700) and return it; safe to call repeatedly."""
    HOLO_DIR.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        HOLO_DIR.chmod(0o700)  # no-op on Windows
    return HOLO_DIR


def _holo_dir_resolved() -> Path:
    return ensure_holo_dir().resolve(strict=True)


def _safe_read(path: Path, max_bytes: int = CUSTOMIZATION_MAX_BYTES) -> str:
    """Read a HOLO_DIR-contained file; empty on missing, escape, error, or oversize (with marker)."""
    try:
        if not path.resolve(strict=False).is_relative_to(_holo_dir_resolved()):
            logger.warning("refusing to read %s: resolves outside %s", path, HOLO_DIR)
            return ""
        data = path.read_bytes()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.warning("could not read %s: %s", path, exc)
        return ""
    if len(data) > max_bytes:
        head = data[:max_bytes].decode("utf-8", errors="replace")
        return f"{head}\n\n[truncated: file is {len(data)} bytes, showing first {max_bytes}]"
    return data.decode("utf-8", errors="replace")


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split an optional YAML frontmatter fence from the body; ``({}, stripped text)`` when absent or malformed."""
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.strip()
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        meta = None
    return (meta if isinstance(meta, dict) else {}), match.group(2).strip()


def _skill_from_md(slug: str, text: str) -> Skill | None:
    """Parse `~/.holo/skills/<slug>/SKILL.md` into a ``Skill``."""
    if not text:
        return None
    meta, body = _parse_frontmatter(text)
    description = str(meta.get("description") or "").strip()
    if not description:
        return None
    if len(description) > SKILL_DESCRIPTION_MAX_CHARS:
        description = description[: SKILL_DESCRIPTION_MAX_CHARS - 1].rstrip() + "…"
    if not body:
        return None
    name = _kebab_slug(slug)
    if not _KEBAB_RE.fullmatch(name):
        logger.warning("skipped skill %s: slug is not convertible to kebab-case", slug)
        return None
    try:
        return Skill(name=name, description=description, body=body)
    except ValidationError as exc:
        logger.warning("skipped skill %s: %s", slug, exc)
        return None


def _kebab_slug(slug: str) -> str:
    """Coerce an arbitrary directory name into the kebab-case shape AgentSkill demands."""
    cleaned = _KEBAB_SCRUB.sub("-", slug.lower()).strip("-")
    return cleaned


class AgentContext(BaseModel):
    """Snapshot of `~/.holo/` taken at run start; frozen for the duration of a run."""

    model_config = ConfigDict(frozen=True)

    agents_md: str
    memories: tuple[str, ...]
    rules: tuple[str, ...]
    skills: tuple[Skill, ...]


def load_agent_context() -> AgentContext:
    """Read every customization file from disk and return a frozen snapshot."""
    return AgentContext(
        agents_md=_render_agents_md(_safe_read(AGENTS_PATH)),
        memories=(*_read_memories(MEMORIES_PATH), *_read_memories(HOLO_MEMORIES_PATH)),
        rules=tuple(_read_memories(RULES_PATH)),
        skills=tuple(_walk_skills(SKILLS_DIR)),
    )


def render_instructions(ctx: AgentContext) -> str:
    """Fold ``agents.md`` + memories + rules into one ``Agent.instructions`` string."""
    parts: list[str] = []
    if ctx.agents_md.strip():
        parts.append(ctx.agents_md.strip())
    if ctx.memories:
        rendered_memories = "\n".join(f"- {m}" for m in ctx.memories)
        parts.append(f"## Memories\n{rendered_memories}")
    if ctx.rules:
        rendered_rules = "\n".join(f"- {r}" for r in ctx.rules)
        parts.append(f"## Rules\n{rendered_rules}")
    return "\n\n".join(parts)


def _render_agents_md(raw: str) -> str:
    """Strip optional `name` frontmatter and prepend a one-line introductory sentence."""
    if not raw:
        return ""
    meta, body = _parse_frontmatter(raw)
    name = str(meta.get("name") or "").strip()
    intro = f"You are talking to {name}." if name else ""
    # Malformed frontmatter can leave nothing extractable; fall back to raw so the user's text is never dropped.
    return "\n\n".join(s for s in (intro, body) if s) or raw.strip()


def _read_memories(path: Path) -> list[str]:
    """Blank-line-separated entries; falls back to one-per-line for files with no blank lines."""
    text = _safe_read(path).replace("\r\n", "\n")
    if "\n\n" in text:
        return [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
    return [line for line in text.splitlines() if line.strip()]


def _walk_skills(root: Path) -> list[Skill]:
    """Load every `<slug>/SKILL.md` under `root`; malformed skills are skipped."""
    if not root.is_dir():
        return []
    skills: list[Skill] = []
    seen: set[str] = set()
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        skill = _skill_from_md(skill_dir.name, _safe_read(skill_dir / "SKILL.md"))
        if skill is None:
            continue
        if skill.name in seen:
            logger.warning("skipped duplicate skill name %s (from %s)", skill.name, skill_dir.name)
            continue
        seen.add(skill.name)
        skills.append(skill)
    return skills


_settings_lock = threading.Lock()


def bundled_skill_os() -> HostOs | None:
    """Which bundled skill set applies to this host; None where Holo ships none (e.g. Linux)."""
    # platform.system(): mypy narrows sys.platform to the analysis OS, flagging other branches unreachable.
    match platform.system():
        case "Darwin":
            return "macos"
        case "Windows":
            return "windows"
        case _:
            return None


def seed_bundled_skills() -> None:
    """Seed every `<slug>/SKILL.md` from the host OS's `holo_desktop.skills/<os>/` folder to `~/.holo/skills/`."""
    os_name = bundled_skill_os()
    if os_name is None:
        return
    os_skills = resources.files("holo_desktop.skills").joinpath(os_name)
    ensure_holo_dir()
    with _settings_lock:
        try:
            text = SETTINGS_PATH.read_text(encoding="utf-8")
            data = json.loads(text) if text.strip() else {}
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        seeded_raw = data.get("seeded_skills")
        seeded: list[str] = list(seeded_raw) if isinstance(seeded_raw, list) else []
        dirty = False
        for entry in sorted(os_skills.iterdir(), key=lambda e: e.name):
            slug = entry.name
            if not entry.is_dir() or slug.startswith(("_", ".")) or slug in seeded:
                continue
            try:
                content = entry.joinpath("SKILL.md").read_text(encoding="utf-8")
            except (FileNotFoundError, OSError):
                continue
            dest = SKILLS_DIR / slug / "SKILL.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_text(content, encoding="utf-8")
            seeded.append(slug)
            dirty = True
        if dirty:
            data["seeded_skills"] = seeded
            _atomic_write_settings(data)


def _atomic_write_settings(data: dict[str, object]) -> None:
    """Atomic settings.json write; per-write temp name avoids racing concurrent writers."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_name(f"settings.json.tmp.{os.getpid()}.{uuid4().hex}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)
