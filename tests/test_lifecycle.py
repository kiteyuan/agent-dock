from __future__ import annotations

import time

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.lifecycle import ModuleLifecycle


class DummySupervisor:
    def start(self, target):
        return {"ok": True, "pid": 123}

    def stop(self, target):
        return {"ok": True}


class DummyHealth:
    def __init__(self):
        self.invalidated = []

    def invalidate(self, target):
        self.invalidated.append(target)


class DummyPetInstaller:
    def install(self, **kwargs):
        return "pet.webp"


def wait_job(lifecycle, job_id):
    for _ in range(100):
        job = lifecycle.job(job_id)
        if job and job.state in ("done", "error"):
            return job
        time.sleep(0.01)
    raise AssertionError("job did not complete")


def test_lifecycle_runs_service_action_in_job() -> None:
    health = DummyHealth()
    lifecycle = ModuleLifecycle(
        catalog=ModuleCatalog.load({}),
        supervisor=DummySupervisor(),
        health=health,
        pet_installer=DummyPetInstaller(),
    )
    queued = lifecycle.submit("start", "runtime")
    assert queued.ok and queued.job_id
    job = wait_job(lifecycle, queued.job_id)
    assert job.state == "done"
    assert job.result and job.result.ok
    assert "runtime" in health.invalidated
    lifecycle.close()


def test_lifecycle_rejects_unknown_action() -> None:
    lifecycle = ModuleLifecycle(
        catalog=ModuleCatalog.load({}),
        supervisor=DummySupervisor(),
        health=DummyHealth(),
        pet_installer=DummyPetInstaller(),
    )
    assert not lifecycle.submit("delete", "pi").ok
    lifecycle.close()


def test_lifecycle_prepare_pi_is_bundled_npm(monkeypatch, tmp_path) -> None:
    """Pi prepare uses in-repo npm install, not an external CLI download."""
    catalog = ModuleCatalog.load({})
    pi = catalog.module("pi")
    assert pi is not None and pi.install.kind == "npm"

    lifecycle = ModuleLifecycle(
        catalog=catalog,
        supervisor=DummySupervisor(),
        health=DummyHealth(),
        pet_installer=DummyPetInstaller(),
    )
    # Without forcing npm, prepare succeeds when node_modules already exists
    # or runs npm; either way it must not say "official CLI is not installed".
    queued = lifecycle.submit("prepare", "pi")
    assert queued.ok and queued.job_id
    job = wait_job(lifecycle, queued.job_id)
    assert job.result is not None
    assert "official CLI" not in (job.result.error or "")
    lifecycle.close()


def test_lifecycle_refuses_parallel_jobs_for_same_target() -> None:
    health = DummyHealth()

    class SlowSupervisor(DummySupervisor):
        def start(self, target):
            time.sleep(0.05)
            return {"ok": True, "pid": 1}

    lifecycle = ModuleLifecycle(
        catalog=ModuleCatalog.load({}),
        supervisor=SlowSupervisor(),
        health=health,
        pet_installer=DummyPetInstaller(),
    )
    first = lifecycle.submit("start", "runtime")
    second = lifecycle.submit("start", "runtime")
    assert first.ok and first.job_id
    assert not second.ok
    assert "already has an active job" in (second.error or "")
    wait_job(lifecycle, first.job_id)
    lifecycle.close()


def test_lifecycle_refuses_to_start_pi_without_bundle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "runtime.platform.presence.shutil.which",
        lambda _command: None,
    )
    # Pretend bundled node_modules is missing by pointing catalog root elsewhere.
    catalog = ModuleCatalog.load({})
    monkeypatch.setattr(catalog, "root", tmp_path)

    supervisor = DummySupervisor()
    supervisor.started = []

    def start(target):
        supervisor.started.append(target)
        return {"ok": True, "pid": 123}

    supervisor.start = start
    lifecycle = ModuleLifecycle(
        catalog=catalog,
        supervisor=supervisor,
        health=DummyHealth(),
        pet_installer=DummyPetInstaller(),
    )
    queued = lifecycle.submit("start", "pi")
    assert queued.ok and queued.job_id
    job = wait_job(lifecycle, queued.job_id)
    assert job.state == "error"
    assert job.result and (
        "not on PATH" in (job.result.error or "")
        or "not detected" in (job.result.error or "")
        or "bundled" in (job.result.error or "").lower()
    )
    assert supervisor.started == []
    lifecycle.close()
