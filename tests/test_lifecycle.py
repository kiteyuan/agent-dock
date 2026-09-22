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


def test_lifecycle_does_not_one_click_install_agents() -> None:
    lifecycle = ModuleLifecycle(
        catalog=ModuleCatalog.load({}),
        supervisor=DummySupervisor(),
        health=DummyHealth(),
        pet_installer=DummyPetInstaller(),
    )
    queued = lifecycle.submit("prepare", "qwen-code")
    assert queued.ok and queued.job_id
    job = wait_job(lifecycle, queued.job_id)
    assert job.state == "error"
    assert job.result and job.result.ok is False
    assert "official CLI" in (job.result.error or "")
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


def test_lifecycle_refuses_to_start_missing_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        "runtime.platform.presence.shutil.which",
        lambda _command: None,
    )
    supervisor = DummySupervisor()
    supervisor.started = []

    def start(target):
        supervisor.started.append(target)
        return {"ok": True, "pid": 123}

    supervisor.start = start
    lifecycle = ModuleLifecycle(
        catalog=ModuleCatalog.load({}),
        supervisor=supervisor,
        health=DummyHealth(),
        pet_installer=DummyPetInstaller(),
    )
    queued = lifecycle.submit("start", "qwen-code")
    assert queued.ok and queued.job_id
    job = wait_job(lifecycle, queued.job_id)
    assert job.state == "error"
    assert job.result and "not on PATH" in (job.result.error or "")
    assert supervisor.started == []
    lifecycle.close()
