from __future__ import annotations

import sys
from threading import Event

import pytest

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.installer import InstallCancelled, InstallError, InstallManager
from runtime.platform.module_state import ModuleState
from runtime.platform.types import (
    InstallSpec,
    InstallStep,
    LicenseSpec,
    ModuleSpec,
)


def make_installer(tmp_path):
    module = ModuleSpec(
        id="fixture",
        name="Fixture",
        kind="agent",
        install=InstallSpec(
            kind="steps",
            steps=[
                InstallStep(
                    kind="command",
                    executable=sys.executable,
                    args=[
                        "-c",
                        "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ok')",
                        "{module_dir}/installed.txt",
                    ],
                )
            ],
        ),
        licenses=[
            LicenseSpec(
                id="fixture-license",
                name="Fixture",
                url="https://example.invalid/license",
                requires_acceptance=True,
            )
        ],
    )
    catalog = ModuleCatalog(modules=[module], sidecars=[], root=tmp_path)
    workspace = tmp_path / "vault"
    installs = tmp_path / "installs"
    state = ModuleState(tmp_path / "state")
    return (
        InstallManager(
            catalog=catalog,
            workspace=workspace,
            installs_root=installs,
            state=state,
        ),
        state,
    )


def test_installer_requires_explicit_license_acceptance(tmp_path) -> None:
    installer, _ = make_installer(tmp_path)
    with pytest.raises(InstallError, match="license acceptance"):
        installer.install("fixture")


def test_installer_records_receipt_and_only_uninstalls_managed_dir(tmp_path) -> None:
    installer, state = make_installer(tmp_path)
    state.accept_license("fixture", "fixture-license", accepted=True)
    receipt = installer.install("fixture")
    target = tmp_path / "installs" / "fixture"
    assert (target / "installed.txt").read_text() == "ok"
    assert receipt["module_id"] == "fixture"
    assert state.receipt("fixture") is not None

    installer.uninstall("fixture")
    assert not target.exists()
    with pytest.raises(InstallError, match="unmanaged"):
        installer.uninstall("fixture")


def test_installer_rolls_back_failed_upgrade(tmp_path) -> None:
    installer, state = make_installer(tmp_path)
    state.accept_license("fixture", "fixture-license", accepted=True)
    installer.install("fixture")
    target = tmp_path / "installs" / "fixture"
    module = installer.catalog.module("fixture")
    assert module is not None
    module.install.steps = [
        InstallStep(
            kind="command",
            executable=sys.executable,
            args=["-c", "raise SystemExit(2)"],
        )
    ]
    with pytest.raises(InstallError):
        installer.install("fixture", force=True)
    assert (target / "installed.txt").read_text() == "ok"


def test_installer_honors_cancellation_before_mutation(tmp_path) -> None:
    installer, state = make_installer(tmp_path)
    state.accept_license("fixture", "fixture-license", accepted=True)
    cancel = Event()
    cancel.set()
    with pytest.raises(InstallCancelled):
        installer.install("fixture", cancel=cancel)
    assert not (tmp_path / "installs" / "fixture").exists()
