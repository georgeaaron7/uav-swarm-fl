import json
from contextlib import nullcontext

import pytest
from test_swarm_coordinator import cluster as cluster
from typer.testing import CliRunner

from swarmcompute.cli import app

runner = CliRunner()


def test_documented_server_init_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["server", "init"])
    assert result.exit_code == 0, result.output
    assert "Initial password (shown once)" in result.output
    assert "localhost:8787" in result.output
    assert runner.invoke(app, ["server", "init"]).exit_code != 0
    assert runner.invoke(app, ["version"]).exit_code == 0


def test_documented_join_owner_controls_and_secret_redaction(
    cluster, tmp_path, monkeypatch
):
    application, client, admin = cluster
    monkeypatch.setenv("SWARM_WORKER_HOME", str(tmp_path / "worker"))
    code = client.post(
        "/api/v1/enrollment-codes", headers=admin, json={"owner": "cli-owner"}
    ).json()["code"]
    monkeypatch.setattr(
        "swarmcompute.cli.httpx.Client", lambda **kwargs: nullcontext(client)
    )
    monkeypatch.setattr(
        "swarmcompute.worker.telemetry.capabilities",
        lambda cfg: {
            "ready": False,
            "diagnostics": ["test fixture: no CUDA"],
            "datasets": {},
        },
    )
    result = runner.invoke(
        app,
        ["join", "--server", "http://testserver", "--name", "cli-laptop"],
        input=code + "\n",
    )
    assert result.exit_code == 0, result.output
    config = json.loads((tmp_path / "worker/config.json").read_text())
    assert config["name"] == "cli-laptop" and config["credential"]
    assert code not in result.output
    assert config["credential"] not in runner.invoke(app, ["config", "show"]).output
    # Exercise CLI option parsing; remote calls use their own scoped HTTP client.
    monkeypatch.undo()


def test_final_planner_generates_240_and_keeps_base_paper_separate(
    tmp_path, monkeypatch
):
    from swarmcompute.coordinator.studies import plan_study

    # Fingerprint fixtures are temporary and not scientific datasets.
    data = tmp_path / "data"
    data.mkdir()
    import numpy as np

    np.savez_compressed(
        data / "cifar10.npz",
        x_train=np.zeros((600, 32, 32, 3), dtype=np.uint8),
        y_train=np.arange(600) % 10,
        x_test=np.zeros((100, 32, 32, 3), dtype=np.uint8),
        y_test=np.arange(100) % 10,
    )
    trace = data / "trace.npz"
    from fl.channel_traces import REQUIRED_FIELDS

    np.savez_compressed(
        trace,
        **{
            key: np.zeros(400, dtype=int)
            if key == "sequence_id"
            else np.arange(400, dtype=float)
            for key in REQUIRED_FIELDS
        },
    )
    manifest = plan_study("matrix", "final", ["fedavg", "ccra"], data, trace)
    assert len(manifest["jobs"]) == 240
    assert {j["config"]["rounds"] for j in manifest["jobs"]} == {100}
    assert {j["seed"] for j in manifest["jobs"]} == set(range(41, 51))
    base = plan_study("base-paper", "final", ["bp_fresh", "bp_reuse"], data, trace)
    assert len(base["jobs"]) == 240
    with pytest.raises(ValueError, match="their own study"):
        plan_study("mixed", "final", ["bp_fresh", "ccra"], data, trace)
    monkeypatch.setenv("SWARM_HOME", str(tmp_path / "home"))
    result = runner.invoke(
        app,
        [
            "study",
            "create",
            "cli-matrix",
            "--profile",
            "final",
            "--aggs",
            "fedavg",
            "ccra",
            "--data-dir",
            str(data),
            "--trace-path",
            str(trace),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "240 jobs planned" in result.output


def test_local_password_recovery_revokes_existing_sessions(
    cluster, tmp_path, monkeypatch
):
    application, client, admin = cluster
    monkeypatch.setenv("SWARM_HOME", str(application.state.db.root))
    password = "new-owner-chosen-password"
    result = runner.invoke(
        app,
        ["server", "reset-password", "--username", "admin"],
        input=password + "\n" + password + "\n",
    )
    assert result.exit_code == 0, result.output
    assert password not in result.output
    assert client.get("/api/v1/settings", headers=admin).status_code == 401
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": password}
    )
    assert response.status_code == 200
