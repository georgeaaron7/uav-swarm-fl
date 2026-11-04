"""Real HTTP coordinator + independent training subprocess acceptance on CPU.

Synthetic input is restricted to this temporary test fixture; none of these
measurements are scientific study results or hardware performance claims.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pytest

from swarmcompute.coordinator import auth
from swarmcompute.coordinator import models as m
from swarmcompute.coordinator.database import Database, insert, rows

REPO = Path(__file__).resolve().parents[1]


def wait_for(predicate, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("timed out waiting for distributed test condition")


def test_two_workers_execute_and_export_real_pilot(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    rng = np.random.default_rng(10)
    np.savez_compressed(
        data / "cifar10.npz",
        x_train=rng.integers(0, 256, (2000, 32, 32, 3), dtype=np.uint8),
        y_train=np.arange(2000) % 10,
        x_test=rng.integers(0, 256, (500, 32, 32, 3), dtype=np.uint8),
        y_test=np.arange(500) % 10,
    )
    home = tmp_path / "coordinator"
    db = Database(home)
    with db.transaction() as c:
        auth.new_user(c, "admin", "admin", "test-only-password")
        insert(
            c,
            m.settings,
            id="coordinator",
            data={
                "heartbeat_interval": 1,
                "lease_timeout": 12,
                "retry_delay": 1,
                "disk_critical_bytes": 1,
            },
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "SWARM_HOME": str(home)}
    log = (tmp_path / "server.log").open("w")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "swarmcompute",
            "server",
            "start",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    workers = []
    handles = [log]
    url = f"http://127.0.0.1:{port}"
    try:

        def ready():
            try:
                return httpx.get(url + "/health", timeout=1).status_code == 200
            except httpx.HTTPError:
                return False

        wait_for(ready, 20)
        client = httpx.Client(base_url=url, timeout=30)
        token = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "test-only-password"},
        ).json()["token"]
        admin = {"Authorization": "Bearer " + token}
        response = client.post(
            "/api/v1/studies",
            headers=admin,
            json={
                "name": "cpu-acceptance",
                "profile": "pilot",
                "aggs": ["fedavg", "ccra"],
                "data_dir": str(data),
                "trace_path": str(data / "absent.npz"),
                "seeds": [41],
                "rounds": 2,
                "attacks": ["clean"],
                "conditions": ["hfl_ideal"],
            },
        )
        assert response.status_code == 200, response.text
        study = response.json()["id"]
        assert response.json()["jobs"] == 2
        for i in range(2):
            worker_home = tmp_path / f"worker{i}"
            worker_home.mkdir()
            code = client.post(
                "/api/v1/enrollment-codes", headers=admin, json={"owner": f"owner{i}"}
            ).json()["code"]
            # First enroll without fabricating readiness; agent supplies measured capabilities.
            response = client.post(
                "/api/v1/workers/enroll",
                json={
                    "code": code,
                    "name": f"cpu-test-{i}",
                    "capabilities": {},
                    "preferences": {"allow_cpu": True},
                },
            )
            assert response.status_code == 200, response.text
            joined = response.json()
            config = {
                "server": url,
                "worker_id": joined["worker_id"],
                "credential": joined["credential"],
                "data_dir": str(data / "context_pilot"),
                "trace_path": str(data / "absent.npz"),
                "mode": "balanced",
                "allow_cpu": True,
            }
            (worker_home / "config.json").write_text(json.dumps(config))
            handle = (tmp_path / f"worker{i}.log").open("w")
            handles.append(handle)
            workers.append(
                subprocess.Popen(
                    [sys.executable, "-m", "swarmcompute", "start"],
                    cwd=REPO,
                    env={**os.environ, "SWARM_WORKER_HOME": str(worker_home)},
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                )
            )

        def online():
            ws = client.get("/api/v1/workers", headers=admin).json()
            return len(ws) == 2 and all(
                w["data"]["capabilities"].get("ready") for w in ws
            )

        wait_for(online, 30)
        assert (
            client.post(f"/api/v1/studies/{study}/start", headers=admin).status_code
            == 200
        )

        def completed():
            jobs = client.get("/api/v1/experiments", headers=admin).json()
            bad = [j for j in jobs if j["status"] == "NEEDS_ATTENTION"]
            if bad:
                raise AssertionError(json.dumps(bad))
            return (
                jobs
                if len(jobs) == 2 and all(j["status"] == "SUCCEEDED" for j in jobs)
                else None
            )

        jobs = wait_for(completed, 120)
        with db.transaction() as c:
            attempts = rows(c, m.attempts)
            assert len({a["worker_id"] for a in attempts}) == 2
            assert all(a["status"] == "SUCCEEDED" for a in attempts)
            assert len(rows(c, m.checkpoints)) >= 2
        for j in jobs:
            detail = client.get("/api/v1/experiments/" + j["id"], headers=admin).json()
            assert [r["round"] for r in detail["history"]] == [1, 2]
            assert detail["runtime"]["provenance"]["job_id"] == j["id"]
        from swarmcompute.coordinator.operations import export_study, validate_study

        assert validate_study(db, study)["valid"]
        destination = export_study(db, study, tmp_path / "export")
        from run_context_study import completed as validate

        manifest = json.loads((destination / "study_manifest.json").read_text())
        assert all(validate(j, destination) for j in manifest["jobs"])
        with pytest.raises(FileExistsError):
            export_study(db, study, destination)
        # Static frontend routes are served by the same process/port.
        assert client.get("/workers").status_code == 200
        assert "SwarmCompute" in client.get("/").text
        client.close()
    finally:
        for proc in workers + [server]:
            proc.terminate()
        for proc in workers + [server]:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for h in handles:
            h.close()
