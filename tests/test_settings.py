from pathlib import Path

import pytest
from pydantic import ValidationError

from holo_desktop.settings import (
    AGENT_API_DEFAULT_PORT,
    AuthSettings,
    GatewaySettings,
    RuntimeInstallSettings,
    RuntimeSpawnSettings,
    ServeSettings,
)
from holo_desktop.settings import (
    TestSettings as HoloTestSettings,
)


def test_auth_settings_ignore_unrelated_environment_keys() -> None:
    settings = AuthSettings.model_validate({"HAI_API_KEY": "key", "PATH": "/bin"})

    assert settings.api_key == "key"


def test_blank_optional_settings_are_unset() -> None:
    runtime = RuntimeSpawnSettings.model_validate(
        {
            "HAI_AGENT_RUNTIME_MODEL": " ",
            "HAI_AGENT_RUNTIME_BASE_URL": "",
            "HAI_AGENT_RUNTIME_RUNS_DIR": "\t",
        }
    )
    install = RuntimeInstallSettings.model_validate(
        {"HAI_AGENT_RUNTIME_DOWNLOAD_URL": "", "HAI_AGENT_RUNTIME_DOWNLOAD_SHA256": " "}
    )

    assert runtime.model is None
    assert runtime.base_url is None
    assert runtime.runs_dir is None
    assert install.download_url is None
    assert install.download_sha256 is None
    assert HoloTestSettings.model_validate({"HOLO_E2E_ARTIFACT_ROOT": " "}).artifact_root is None
    assert GatewaySettings.model_validate({"HAI_BASE_URL": ""}).base_url is None


def test_serve_auth_token_preserves_blank_for_user_facing_error() -> None:
    assert ServeSettings.model_validate({"HOLO_AUTH_TOKEN": " "}).auth_token == " "


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_runtime_port_uses_default(value: str) -> None:
    settings = RuntimeSpawnSettings.model_validate({"HAI_AGENT_RUNTIME_PORT": value})

    assert settings.port == AGENT_API_DEFAULT_PORT


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_runtime_fake_accepts_existing_true_values(value: str) -> None:
    assert RuntimeSpawnSettings.model_validate({"HAI_AGENT_RUNTIME_FAKE": value}).fake is True


def test_runtime_fake_rejects_other_values_as_false() -> None:
    assert RuntimeSpawnSettings.model_validate({"HAI_AGENT_RUNTIME_FAKE": "on"}).fake is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_runtime_fast_accepts_existing_true_values(value: str) -> None:
    assert RuntimeSpawnSettings.model_validate({"HAI_AGENT_RUNTIME_FAST": value}).fast is True


def test_runtime_fast_defaults_false() -> None:
    assert RuntimeSpawnSettings.model_validate({}).fast is False


def test_runtime_spawn_defaults_and_path_parsing() -> None:
    settings = RuntimeSpawnSettings.model_validate({"HAI_AGENT_RUNTIME_RUNS_DIR": "~/runs"})

    assert settings.port == AGENT_API_DEFAULT_PORT
    assert settings.runs_dir == Path("~/runs")


def test_test_settings_parse_artifact_root_path() -> None:
    settings = HoloTestSettings.model_validate({"HOLO_E2E_ARTIFACT_ROOT": "~/holo-e2e"})

    assert settings.artifact_root == Path("~/holo-e2e")


@pytest.mark.parametrize("value", ["not-a-port", "0", "65536"])
def test_runtime_port_validation_names_env_var(value: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        RuntimeSpawnSettings.model_validate({"HAI_AGENT_RUNTIME_PORT": value})

    assert "HAI_AGENT_RUNTIME_PORT" in str(excinfo.value)
