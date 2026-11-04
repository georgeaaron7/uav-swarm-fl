"""Local Mac coordinator start/status/stop helper; installs no login service."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

from swarmcompute.config import data_home

REPO = Path(__file__).resolve().parents[1]


def health(port):
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
        return r.status_code == 200 and r.json().get("version") is not None
    except (httpx.HTTPError, ValueError):
        return False


def control(action, port=8787):
    root = data_home()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    pidfile = root / "coordinator-process.json"
    if action == "status":
        return {"running": health(port), "dashboard": f"http://localhost:{port}"}
    if action == "stop":
        if not pidfile.exists():
            return {
                "stopped": False,
                "detail": "No shortcut-owned process. Stop the existing coordinator in its Terminal window.",
            }
        saved = json.loads(pidfile.read_text())
        try:
            process = psutil.Process(saved["pid"])
            command = process.cmdline()
            if abs(process.create_time() - saved["created"]) > 0.01 or not all(
                v in command for v in ("swarmcompute", "server", "start")
            ):
                raise ValueError(
                    "PID is no longer the recorded coordinator; refusing to stop it"
                )
            process.terminate()
            try:
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                raise RuntimeError(
                    "Coordinator did not stop within 10 seconds; inspect its logs"
                )
        except psutil.NoSuchProcess:
            pass
        pidfile.unlink(missing_ok=True)
        return {"stopped": True}
    if health(port):
        return {
            "running": True,
            "dashboard": f"http://localhost:{port}",
            "detail": "Already running; no duplicate process started",
        }
    logs = root / "logs"
    logs.mkdir(exist_ok=True, mode=0o700)
    logfile = logs / "coordinator.log"
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as handle:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "swarmcompute",
                "server",
                "start",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ],
            cwd=REPO,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    pidfile.write_text(
        json.dumps(
            {
                "pid": process.pid,
                "created": psutil.Process(process.pid).create_time(),
                "port": port,
            }
        )
    )
    if os.name != "nt":
        pidfile.chmod(0o600)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if health(port):
            return {
                "running": True,
                "dashboard": f"http://localhost:{port}",
                "log": str(logfile),
            }
        if process.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f"Coordinator failed to start; inspect {logfile}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop"])
    parser.add_argument("--port", type=int, default=8787)
    arguments = parser.parse_args()
    print(json.dumps(control(arguments.action, arguments.port), indent=2))
