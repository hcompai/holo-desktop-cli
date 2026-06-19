"""Typed settings for Holo's environment-backed configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticUseDefault
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_API_DEFAULT_PORT = 18795
PORT_ENV = "HAI_AGENT_RUNTIME_PORT"
AUTH_TOKEN_ENV = "HAI_AGENT_RUNTIME_API_TOKEN"
RUNTIME_BASE_URL_ENV = "HAI_AGENT_RUNTIME_BASE_URL"
DOWNLOAD_URL_ENV = "HAI_AGENT_RUNTIME_DOWNLOAD_URL"
DOWNLOAD_SHA256_ENV = "HAI_AGENT_RUNTIME_DOWNLOAD_SHA256"
E2E_ARTIFACT_ROOT_ENV = "HOLO_E2E_ARTIFACT_ROOT"

_TRUE_VALUES = frozenset(("1", "true", "yes"))


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value.strip() if isinstance(value, str) else value


def _parse_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VALUES
    return bool(value)


def _valid_port(value: int) -> int:
    if not 1 <= value <= 65535:
        raise ValueError("port is out of the valid range 1-65535")
    return value


OptionalText = Annotated[str | None, AfterValidator(_blank_to_none)]
Port = Annotated[int, AfterValidator(_valid_port)]


class AuthSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api_key: OptionalText = Field(default=None, validation_alias="HAI_API_KEY")


class GatewaySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: OptionalText = Field(default=None, validation_alias="HAI_BASE_URL")


class RuntimeSpawnSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    port: Port = Field(default=AGENT_API_DEFAULT_PORT, validation_alias=PORT_ENV)
    api_token: OptionalText = Field(default=None, validation_alias=AUTH_TOKEN_ENV)
    model: OptionalText = Field(default=None, validation_alias="HAI_AGENT_RUNTIME_MODEL")
    base_url: OptionalText = Field(default=None, validation_alias=RUNTIME_BASE_URL_ENV)
    fake: bool = Field(default=False, validation_alias="HAI_AGENT_RUNTIME_FAKE")
    fast: bool = Field(default=False, validation_alias="HAI_AGENT_RUNTIME_FAST")
    runs_dir: Path | None = Field(default=None, validation_alias="HAI_AGENT_RUNTIME_RUNS_DIR")

    @field_validator("port", mode="before")
    @classmethod
    def _blank_port_uses_default(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise PydanticUseDefault()
        return value

    @field_validator("fake", "fast", mode="before")
    @classmethod
    def _validate_flags(cls, value: object) -> bool:
        return _parse_flag(value)

    @field_validator("runs_dir", mode="before")
    @classmethod
    def _blank_runs_dir_is_unset(cls, value: object) -> object:
        return _blank_to_none(value)


class RuntimeInstallSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    download_url: OptionalText = Field(default=None, validation_alias=DOWNLOAD_URL_ENV)
    download_sha256: OptionalText = Field(default=None, validation_alias=DOWNLOAD_SHA256_ENV)


class ServeSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    auth_token: str | None = Field(default=None, validation_alias="HOLO_AUTH_TOKEN")


class TestSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    artifact_root: Path | None = Field(default=None, validation_alias=E2E_ARTIFACT_ROOT_ENV)

    @field_validator("artifact_root", mode="before")
    @classmethod
    def _blank_artifact_root_is_unset(cls, value: object) -> object:
        return _blank_to_none(value)


@dataclass(frozen=True)
class HoloSettings:
    auth: AuthSettings
    gateway: GatewaySettings
    runtime: RuntimeSpawnSettings
    install: RuntimeInstallSettings
    serve: ServeSettings
    test: TestSettings


class _AuthEnvSettings(AuthSettings, BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)


class _GatewayEnvSettings(GatewaySettings, BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)


class _RuntimeSpawnEnvSettings(RuntimeSpawnSettings, BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)


class _RuntimeInstallEnvSettings(RuntimeInstallSettings, BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)


class _ServeEnvSettings(ServeSettings, BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)


class _TestEnvSettings(TestSettings, BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)


def load_holo_settings() -> HoloSettings:
    try:
        return HoloSettings(
            auth=_AuthEnvSettings(),
            gateway=_GatewayEnvSettings(),
            runtime=_RuntimeSpawnEnvSettings(),
            install=_RuntimeInstallEnvSettings(),
            serve=_ServeEnvSettings(),
            test=_TestEnvSettings(),
        )
    except ValidationError as exc:
        raise settings_error(exc) from exc


def settings_error(exc: ValidationError) -> RuntimeError:
    problems = []
    for err in exc.errors():
        loc = err.get("loc", ())
        name = str(loc[0]) if isinstance(loc, tuple) and loc else "settings"
        problems.append(f"{name}: {err.get('msg', 'invalid value')}")
    return RuntimeError("; ".join(problems))
