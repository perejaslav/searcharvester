"""Unit tests for orchestrator — pure logic with fake Docker client."""
from __future__ import annotations

import asyncio

import pytest

from orchestrator import Orchestrator, JobStatus, REPORT_MARKER
from tests.conftest import FakeContainer


# ---------- spawn() ----------

@pytest.mark.asyncio
async def test_spawn_returns_hex_job_id(fake_docker, orch_config):
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="anything")
    assert len(job_id) == 16
    assert all(c in "0123456789abcdef" for c in job_id)


@pytest.mark.asyncio
async def test_spawn_creates_workspace_dir(fake_docker, orch_config, tmp_jobs_dir):
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    assert (tmp_jobs_dir / job_id).is_dir()


@pytest.mark.asyncio
async def test_spawn_passes_query_and_skills_to_hermes_cli(fake_docker, orch_config):
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    await orch.spawn(query="what is RAG")
    kw = fake_docker.containers.last_run_kwargs
    cmd = kw["command"]
    # Query should contain the user's text + the mandatory output contract suffix.
    q_index = cmd.index("-q") + 1
    passed_query = cmd[q_index]
    assert passed_query.startswith("what is RAG")
    assert "REPORT_SAVED" in passed_query  # orchestrator's mandatory contract
    assert "-s" in cmd
    skills_arg = cmd[cmd.index("-s") + 1]
    assert "searcharvester-deep-research" in skills_arg
    assert "--yolo" in cmd


@pytest.mark.asyncio
async def test_spawn_mounts_workspace_volume(fake_docker, orch_config, tmp_jobs_dir):
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    volumes = fake_docker.containers.last_run_kwargs["volumes"]
    workspace_host = str(tmp_jobs_dir / job_id)
    assert workspace_host in volumes
    assert volumes[workspace_host]["bind"] == "/workspace"


@pytest.mark.asyncio
async def test_spawn_container_start_failure_marks_job_failed(fake_docker, orch_config):
    fake_docker.containers.run_raises = RuntimeError("boom")
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    job = orch.get(job_id)
    assert job.status == JobStatus.failed
    assert "boom" in job.error


# ---------- watch() / result handling ----------

@pytest.mark.asyncio
async def test_watch_parses_report_saved_marker_and_reads_report(
    fake_docker, orch_config, tmp_jobs_dir
):
    fake_docker.containers.prepare(
        FakeContainer(
            _logs=f"working...\n{REPORT_MARKER} /workspace/report.md\n".encode()
        )
    )
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    # Simulate Hermes writing the report file into the workspace.
    (tmp_jobs_dir / job_id / "report.md").write_text(
        "# Title\n\nBody with citation [1]\n\n[1] https://x\n"
    )
    await asyncio.sleep(0.1)
    job = orch.get(job_id)
    assert job.status == JobStatus.completed
    assert "Title" in job.report
    # Log file persisted on disk
    assert (tmp_jobs_dir / job_id / "hermes.log").exists()


@pytest.mark.asyncio
async def test_watch_without_marker_marks_failed(fake_docker, orch_config):
    fake_docker.containers.prepare(
        FakeContainer(_logs=b"some chatter without marker\n")
    )
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    await asyncio.sleep(0.1)
    job = orch.get(job_id)
    assert job.status == JobStatus.failed
    assert "marker" in job.error.lower()


@pytest.mark.asyncio
async def test_watch_marker_but_no_report_md_marks_failed(
    fake_docker, orch_config, tmp_jobs_dir
):
    fake_docker.containers.prepare(
        FakeContainer(_logs=f"{REPORT_MARKER} /workspace/report.md\n".encode())
    )
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    # Deliberately DO NOT write report.md.
    await asyncio.sleep(0.1)
    job = orch.get(job_id)
    assert job.status == JobStatus.failed
    assert "report.md" in job.error


@pytest.mark.asyncio
async def test_watch_timeout_kills_container(fake_docker, orch_config):
    orch_config["timeout_sec"] = 1  # short

    def _slow():
        import time
        time.sleep(3)

    container = FakeContainer()
    container._side_effect_on_wait = _slow
    fake_docker.containers.prepare(container)

    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    await asyncio.sleep(2)
    job = orch.get(job_id)
    assert job.status == JobStatus.timeout
    assert container._killed is True
    assert container._removed is True


@pytest.mark.asyncio
async def test_concurrent_spawns_have_independent_state(fake_docker, orch_config):
    fake_docker.containers.prepare(FakeContainer(_logs=b"no marker"))
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    ids = await asyncio.gather(*[orch.spawn(query=f"q{i}") for i in range(3)])
    assert len(set(ids)) == 3
    for i in ids:
        assert orch.get(i) is not None


# ---------- cancel() ----------

@pytest.mark.asyncio
async def test_cancel_kills_running_container(fake_docker, orch_config):
    def _block():
        import time
        time.sleep(5)

    container = FakeContainer()
    container._side_effect_on_wait = _block
    fake_docker.containers.prepare(container)

    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    await asyncio.sleep(0.05)
    ok = await orch.cancel(job_id)
    assert ok is True
    job = orch.get(job_id)
    assert job.status == JobStatus.cancelled
    assert container._killed is True


@pytest.mark.asyncio
async def test_cancel_already_completed_is_noop(
    fake_docker, orch_config, tmp_jobs_dir
):
    fake_docker.containers.prepare(
        FakeContainer(_logs=f"{REPORT_MARKER} ok\n".encode())
    )
    orch = Orchestrator(docker_client=fake_docker, **orch_config)
    job_id = await orch.spawn(query="x")
    (tmp_jobs_dir / job_id / "report.md").write_text("#")
    await asyncio.sleep(0.1)
    assert orch.get(job_id).status == JobStatus.completed
    ok = await orch.cancel(job_id)
    assert ok is False
    assert orch.get(job_id).status == JobStatus.completed
