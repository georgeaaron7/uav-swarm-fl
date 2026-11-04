import importlib.util
import socket
from pathlib import Path

import httpx

from swarmcompute.coordinator.auth import new_user
from swarmcompute.coordinator.database import Database


def test_local_coordinator_shortcuts_start_and_stop_only_their_process(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SWARM_HOME", str(tmp_path / "coordinator"))
    db = Database(tmp_path / "coordinator")
    with db.transaction() as c:
        new_user(c, "admin", "admin", "test-only-password")
    path = Path(__file__).resolve().parents[1] / "scripts/coordinator.py"
    spec = importlib.util.spec_from_file_location("coordinator_control", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    try:
        assert module.control("start", port)["running"]
        assert module.control("start", port)["detail"].startswith("Already running")
        assert module.control("status", port)["running"]
        with httpx.Client(base_url=f"http://localhost:{port}") as client:
            token = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "test-only-password"},
            ).json()["token"]
            with client.stream(
                "GET", "/api/v1/stream", headers={"Authorization": "Bearer " + token}
            ) as response:
                assert next(response.iter_lines()).startswith("event:")
                report = module.control("stop", port)
    finally:
        if module.control("status", port)["running"]:
            module.control("stop", port)
    assert report["stopped"]
    assert not module.control("status", port)["running"]
