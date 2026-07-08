from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from holo_desktop.agent_client.runtime_install import RuntimeArtifactUnavailable
from holo_desktop.settings import RuntimeInstallSettings


def test_installer_bootstrap_prepares_runtime_and_prints_next_steps(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    setup_module = importlib.import_module("holo_desktop.installer_bootstrap")

    calls: list[tuple[str, object]] = []
    runtime_path = tmp_path / "runtime" / "hai-agent-runtime"

    monkeypatch.setattr(setup_module, "load_holo_env", lambda: calls.append(("load_env", None)))
    monkeypatch.setattr(
        setup_module, "load_holo_settings", lambda: type("Settings", (), {"install": RuntimeInstallSettings()})()
    )
    monkeypatch.setattr(setup_module, "seed_bundled_skills", lambda: calls.append(("seed_skills", None)))

    def fake_ensure(*, settings: RuntimeInstallSettings, assume_yes: bool) -> Path:
        calls.append(("ensure_runtime", assume_yes))
        return runtime_path

    monkeypatch.setattr(setup_module, "ensure_managed_runtime", fake_ensure)

    setup_module.bootstrap_installer(yes=True, login=False, install_hosts=False)

    err = capsys.readouterr().err
    assert calls == [("load_env", None), ("seed_skills", None), ("ensure_runtime", True)]
    assert "runtime ready" in err
    assert "holo login" in err
    assert "holo install" in err


def test_installer_bootstrap_exits_cleanly_for_unsupported_runtime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_module = importlib.import_module("holo_desktop.installer_bootstrap")

    monkeypatch.setattr(setup_module, "load_holo_env", lambda: None)
    monkeypatch.setattr(
        setup_module, "load_holo_settings", lambda: type("Settings", (), {"install": RuntimeInstallSettings()})()
    )
    monkeypatch.setattr(setup_module, "seed_bundled_skills", lambda: None)
    monkeypatch.setattr(
        setup_module,
        "ensure_managed_runtime",
        lambda *, settings, assume_yes: (_ for _ in ()).throw(RuntimeArtifactUnavailable("not published")),
    )

    with pytest.raises(SystemExit) as exc:
        setup_module.bootstrap_installer(yes=True, login=False, install_hosts=False)

    assert exc.value.code == 1
    assert "not published" in capsys.readouterr().err


def test_installer_bootstrap_can_run_login_and_host_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    setup_module = importlib.import_module("holo_desktop.installer_bootstrap")

    calls: list[str] = []
    monkeypatch.setattr(setup_module, "load_holo_env", lambda: None)
    monkeypatch.setattr(
        setup_module, "load_holo_settings", lambda: type("Settings", (), {"install": RuntimeInstallSettings()})()
    )
    monkeypatch.setattr(setup_module, "seed_bundled_skills", lambda: None)
    monkeypatch.setattr(
        setup_module,
        "ensure_managed_runtime",
        lambda *, settings, assume_yes: tmp_path / "hai-agent-runtime",
    )

    install_module = importlib.import_module("holo_desktop.cli.install")
    login_module = importlib.import_module("holo_desktop.cli.login")

    monkeypatch.setattr(login_module, "login", lambda: calls.append("login"))
    monkeypatch.setattr(install_module, "install", lambda: calls.append("install"))

    setup_module.bootstrap_installer(yes=True, login=True, install_hosts=True)

    assert calls == ["login", "install"]
