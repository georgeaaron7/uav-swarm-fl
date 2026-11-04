from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {
    "heartbeat_interval": 5,
    "suspect_timeout": 20,
    "lease_timeout": 60,
    "retry_delay": 30,
    "max_retry_delay": 300,
    "max_retries": 5,
    "checkpoint_every_rounds": 10,
    "checkpoint_every_seconds": 180,
    "max_workers": 16,
    "max_concurrent": 8,
    "disk_warning_bytes": 5 * 1024**3,
    "disk_critical_bytes": 1024**3,
    "max_upload_bytes": 512 * 1024**2,
    "checkpoint_keep": 2,
    "enrollment_enabled": True,
    "automatic_start": False,
}


def data_home():
    return (
        Path(os.environ.get("SWARM_HOME", Path.home() / ".swarmcompute"))
        .expanduser()
        .resolve()
    )


def worker_home():
    return (
        Path(os.environ.get("SWARM_WORKER_HOME", data_home() / "worker"))
        .expanduser()
        .resolve()
    )


def read_config():
    path = worker_home() / "config.json"
    if not path.exists():
        raise ValueError("worker is not enrolled; run swarm join")
    return json.loads(path.read_text())


def write_config(value):
    root = worker_home()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "config.json"
    temp = root / "config.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    if os.name != "nt":
        path.chmod(0o600)
