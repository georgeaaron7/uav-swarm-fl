"""Outbound HTTP worker. Heartbeats remain active during hashing and transfers."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import random
import signal
import threading
import time

import httpx

from ..config import read_config, worker_home, write_config
from ..shared.hashing import sha256
from .executor import archive, extract_checkpoint, failure_reason, launch
from .resources import admit, preferences
from .telemetry import capabilities, telemetry

RESULT_FILES = {
    "config.json",
    "history.json",
    "summary.json",
    "metrics.csv",
    "final_model.pt",
    "best_model.pt",
    "assumptions.json",
    "swarm_partition.json",
    "runtime.json",
}


class Agent:
    def __init__(self):
        self.root = worker_home()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config = read_config()
        self.cap = capabilities(self.config)
        self.http = httpx.Client(
            base_url=self.config["server"].rstrip("/"),
            headers={"Authorization": "Bearer " + self.config["credential"]},
            timeout=httpx.Timeout(30, connect=5),
        )
        self.current = None
        self.process = None
        self.run_root = None
        self.control = "resume"
        self.leaving = False
        self.stopping = threading.Event()
        self.heartbeat_stop = threading.Event()
        self.connected = False
        self.lease_deadline = 0
        self.settings = {"heartbeat_interval": 5, "lease_timeout": 60}
        self.lock = threading.RLock()
        self.log = logging.getLogger("swarm.worker")

    def request(self, method, path, **kwargs):
        response = self.http.request(method, "/api/v1" + path, **kwargs)
        if response.status_code in {401, 403, 409}:
            self.log.warning("Coordinator rejected %s (%s)", path, response.status_code)
            if self.current and self.run_root:
                (self.run_root / "STOP").touch()
                self.lease_deadline = 0
        response.raise_for_status()
        return response.json()

    def status(self, **extra):
        value = {
            "connected": self.connected,
            "control": self.control,
            "attempt": self.current,
            "pid": self.process.pid
            if self.process and self.process.poll() is None
            else None,
            "capabilities": self.cap,
            "updated": time.time(),
            **extra,
        }
        # Fencing credentials never go to the user-readable status/log file.
        if value["attempt"]:
            value["attempt"] = {
                k: v for k, v in value["attempt"].items() if k != "fence"
            }
        temp = self.root / "status.tmp"
        temp.write_text(json.dumps(value))
        temp.replace(self.root / "status.json")

    def heartbeat_loop(self):
        backoff = 1
        while not self.heartbeat_stop.is_set():
            try:
                with self.lock:
                    current = self.current
                    metrics = telemetry(self.root)
                    body = {
                        "telemetry": metrics,
                        "capabilities": self.cap,
                        "preferences": preferences(self.config),
                        "preferences_version": self.config.get(
                            "preferences_version", 0
                        ),
                    }
                    if current:
                        body.update(
                            attempt_id=current["attempt_id"], fence=current["fence"]
                        )
                response = self.request(
                    "POST", f"/workers/{self.config['worker_id']}/heartbeat", json=body
                )
                with self.lock:
                    if response.get("preferences_update"):
                        self.config.update(response["preferences_update"])
                        self.config["preferences_version"] = response[
                            "preferences_version"
                        ]
                        write_config(self.config)
                    self.settings = response["settings"]
                    self.control = response["control"]
                    self.leaving = response.get("leaving", False)
                    self.connected = True
                    if (
                        current
                        and self.current
                        and current["attempt_id"] == self.current["attempt_id"]
                        and response.get("lease_expires")
                    ):
                        self.lease_deadline = (
                            time.monotonic() + self.settings["lease_timeout"] - 2
                        )
                        if self.run_root and self.run_root.exists():
                            temp = self.run_root / "lease.tmp"
                            temp.write_text(
                                json.dumps({"expires_monotonic": self.lease_deadline})
                            )
                            temp.replace(self.run_root / "lease.json")
                backoff = 1
            except (httpx.HTTPError, ValueError, OSError) as exc:
                self.connected = False
                self.log.warning("Heartbeat unavailable: %s", type(exc).__name__)
                backoff = min(30, backoff * 2)
            with self.lock:
                if self.current and (
                    time.monotonic() >= self.lease_deadline
                    or self.control in {"pause", "leave"}
                ):
                    if self.run_root:
                        (self.run_root / "STOP").touch()
            self.heartbeat_stop.wait(
                min(self.settings["heartbeat_interval"], backoff)
                + random.uniform(0, 0.5)
            )

    def publish(self, path, kind, assignment):
        body = {
            "fence": assignment["fence"],
            "kind": kind,
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
        record = self.request(
            "POST", f"/attempts/{assignment['attempt_id']}/uploads", json=body
        )
        id = record["id"]
        headers = {"X-Lease-Token": assignment["fence"]}
        offset = self.request("GET", f"/uploads/{id}", headers=headers)["offset"]
        with path.open("rb") as f:
            f.seek(offset)
            while chunk := f.read(4 * 1024**2):
                offset = self.request(
                    "PUT",
                    f"/uploads/{id}?offset={offset}",
                    headers=headers,
                    content=chunk,
                )["offset"]
        self.request(
            "POST", f"/uploads/{id}/finalize", json={"fence": assignment["fence"]}
        )
        return id

    def download(self, checkpoint, directory):
        path = directory / "recovery.zip"
        with self.http.stream(
            "GET", f"/api/v1/artifacts/{checkpoint['id']}/download"
        ) as response:
            response.raise_for_status()
            count = 0
            with path.open("wb") as f:
                for chunk in response.iter_bytes():
                    count += len(chunk)
                    if count > 512 * 1024**2:
                        raise ValueError("recovery archive too large")
                    f.write(chunk)
        if sha256(path) != checkpoint["sha256"]:
            raise ValueError("recovery transfer checksum mismatch")
        return extract_checkpoint(path, directory / "recovery")

    def execute(self, assignment):
        from fl.checkpoint import identity, load_checkpoint
        from fl.config import FLConfig

        # Verify source and dataset files again immediately before admission.
        cap = capabilities(self.config, False)
        if cap["source_sha256"] != assignment["source_sha256"]:
            raise ValueError("source mismatch")
        for key, value in assignment["datasets"].items():
            if value and cap["datasets"].get(key) != value:
                raise ValueError("dataset mismatch")
        root = self.root / "runs" / assignment["attempt_id"]
        if root.exists():
            raise ValueError("attempt directory already exists; refusing overwrite")
        staging = self.root / "downloads" / assignment["attempt_id"]
        staging.mkdir(parents=True, exist_ok=True)
        if assignment.get("checkpoint"):
            recovery = self.download(assignment["checkpoint"], staging)
            cfg = FLConfig(
                **{
                    **assignment["config"],
                    "data_dir": self.config["data_dir"],
                    "channel_trace_path": self.config["trace_path"],
                }
            )
            load_checkpoint(recovery, identity(cfg))
            assignment["resume_path"] = str(recovery)
        with self.lock:
            self.run_root = root
            self.process, output = launch(assignment, self.config, root)
        published = set()
        last_round = -1
        stop_at = None
        samples = []
        upload_seconds = 0.0
        self.log.info(
            "Experiment %s attempt %s started pid=%s",
            assignment["job_id"],
            assignment["attempt_id"],
            self.process.pid,
        )
        while True:
            config = read_config()
            self.config.update(config)
            metrics = telemetry(self.root)
            samples.append(metrics)
            allowed, reason = admit(self.config, metrics)
            if (
                self.stopping.is_set()
                or not allowed
                or self.control in {"pause", "leave"}
                or time.monotonic() >= self.lease_deadline
            ):
                (root / "STOP").touch()
                if stop_at is None:
                    stop_at = time.monotonic()
                if reason:
                    self.log.info("Requesting checkpointed pause: %s", reason)
            if (
                stop_at
                and time.monotonic() - stop_at > 120
                and self.process.poll() is None
            ):
                self.log.warning(
                    "Round boundary did not arrive in 120s; terminating; latest durable checkpoint remains recovery point"
                )
                self.process.terminate()
            if self.connected and time.monotonic() < self.lease_deadline:
                try:
                    progress = root / "progress.json"
                    if progress.exists():
                        row = json.loads(progress.read_text())
                        if row["round"] != last_round:
                            log = (root / "training.log").read_text(errors="replace")[
                                -65536:
                            ]
                            self.request(
                                "POST",
                                f"/attempts/{assignment['attempt_id']}/progress",
                                json={
                                    "fence": assignment["fence"],
                                    "round": row["round"],
                                    "metrics": row,
                                    "runtime": cap,
                                    "logs": log,
                                },
                            )
                            last_round = row["round"]
                    for cp in sorted((root / "checkpoints").glob("round_*")):
                        if cp.name in published:
                            continue
                        load_checkpoint(cp)
                        bundle = archive(
                            cp,
                            staging / (cp.name + ".zip"),
                            {"state.pt", "metadata.json", "COMPLETE"},
                        )
                        upload_start = time.monotonic()
                        self.publish(bundle, "checkpoint", assignment)
                        published.add(cp.name)
                        upload_seconds += time.monotonic() - upload_start
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    self.log.warning(
                        "Progress/artifact publication pending locally: %s",
                        type(exc).__name__,
                    )
            self.status(current_round=last_round, local_checkpoints=sorted(published))
            if self.process.poll() is not None:
                break
            time.sleep(0.5)
        code = self.process.wait()
        # Renewed heartbeat keeps publication legal after the subprocess exits.
        if not self.connected or time.monotonic() >= self.lease_deadline:
            self.log.warning(
                "Lease unavailable: local artifacts retained; authoritative recovery uses validated coordinator checkpoints"
            )
            return
        if (output / "summary.json").is_file() and code == 0:
            runtime_path = output / "runtime.json"
            runtime = json.loads(runtime_path.read_text())

            def mean(field):
                values = [
                    x[field] for x in samples if isinstance(x.get(field), (int, float))
                ]
                return sum(values) / len(values) if values else None

            gpu_memory = [
                x["gpu_memory_used_mb"]
                for x in samples
                if x.get("gpu_memory_used_mb") is not None
            ]
            runtime["worker_measurements"] = {
                "peak_gpu_memory_mb": max(gpu_memory) if gpu_memory else None,
                "average_gpu_utilization": mean("gpu_utilization"),
                "average_cpu_utilization": mean("cpu_percent"),
                "checkpoint_upload_seconds": upload_seconds,
                "sample_count": len(samples),
                "hardware": cap,
            }
            runtime_path.write_text(json.dumps(runtime, indent=2, allow_nan=False))
            import torch

            weights = torch.load(
                output / "final_model.pt", map_location="cpu", weights_only=True
            )
            if (
                not isinstance(weights, dict)
                or not weights
                or any(
                    not isinstance(v, torch.Tensor) or not torch.isfinite(v).all()
                    for v in weights.values()
                )
            ):
                raise ValueError("final model contains invalid tensor state")
            bundle = archive(output, staging / "result.zip", RESULT_FILES)
            artifact = self.publish(bundle, "result", assignment)
            self.request(
                "POST",
                f"/attempts/{assignment['attempt_id']}/complete",
                json={"fence": assignment["fence"], "artifact_id": artifact},
            )
            self.log.info("Experiment %s result committed", assignment["job_id"])
        elif (root / "STOP").exists() and code == 0:
            local = sorted((root / "checkpoints").glob("round_*"))
            if not local or local[-1].name not in published:
                self.log.warning(
                    "Latest pause checkpoint remains local; lease not released as a published pause"
                )
                return
            self.request(
                "POST",
                f"/attempts/{assignment['attempt_id']}/release",
                json={"fence": assignment["fence"]},
            )
            self.log.info("Checkpoint committed and lease released")
        else:
            text = (root / "training.log").read_text(errors="replace")
            self.request(
                "POST",
                f"/attempts/{assignment['attempt_id']}/fail",
                json={
                    "fence": assignment["fence"],
                    "reason": failure_reason(text),
                    "details": text[-4096:],
                },
            )

    def run(self):
        lock = self.root / "agent.lock"
        if lock.exists():
            try:
                import psutil

                pid = int(lock.read_text())
                if psutil.pid_exists(pid):
                    raise ValueError("agent already running")
            except (ValueError, OSError) as exc:
                if str(exc) == "agent already running":
                    raise
            lock.unlink(missing_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[
                logging.FileHandler(self.root / "agent.log"),
                logging.StreamHandler(),
            ],
        )
        signal.signal(signal.SIGINT, lambda *_: self.stopping.set())
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda *_: self.stopping.set())
        thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        thread.start()
        try:
            while not self.stopping.is_set():
                self.config = read_config()
                if self.config.get("left"):
                    break
                if self.connected and not self.config.get("started_once"):
                    try:
                        self.request(
                            "POST",
                            f"/workers/{self.config['worker_id']}/control",
                            json={"action": "resume"},
                        )
                        self.config["started_once"] = True
                        write_config(self.config)
                    except httpx.HTTPError:
                        self.stopping.wait(2)
                        continue
                if (self.config.get("leaving") or self.leaving) and not self.current:
                    self.request("POST", f"/workers/{self.config['worker_id']}/revoke")
                    self.log.info("Worker credential revoked; participation ended")
                    self.config["left"] = True
                    write_config(self.config)
                    break
                allowed, reason = admit(self.config, telemetry(self.root))
                used = sum(
                    p.stat().st_size
                    for base in ("runs", "downloads")
                    for p in (self.root / base).rglob("*")
                    if p.is_file()
                )
                allowed = (
                    allowed and used < preferences(self.config)["storage_limit_bytes"]
                )
                if (
                    self.connected
                    and self.control == "resume"
                    and self.cap["ready"]
                    and allowed
                ):
                    try:
                        response = self.request(
                            "POST", f"/workers/{self.config['worker_id']}/jobs/claim"
                        )
                        assignment = response.get("assignment")
                        if assignment:
                            with self.lock:
                                self.current = assignment
                                self.lease_deadline = (
                                    time.monotonic()
                                    + assignment["settings"]["lease_timeout"]
                                    - 2
                                )
                            try:
                                self.execute(assignment)
                            except (
                                ValueError,
                                OSError,
                                RuntimeError,
                                httpx.HTTPError,
                            ) as exc:
                                self.log.error(
                                    "Attempt stopped: %s", type(exc).__name__
                                )
                                if (
                                    self.connected
                                    and time.monotonic() < self.lease_deadline
                                ):
                                    reason = "application"
                                    if isinstance(exc, httpx.TransportError):
                                        reason = "network"
                                    elif isinstance(exc, OSError):
                                        reason = "infrastructure"
                                    elif "source mismatch" in str(exc):
                                        reason = "source_mismatch"
                                    elif "dataset mismatch" in str(exc):
                                        reason = "dataset_mismatch"
                                    with contextlib.suppress(httpx.HTTPError):
                                        self.request(
                                            "POST",
                                            f"/attempts/{assignment['attempt_id']}/fail",
                                            json={
                                                "fence": assignment["fence"],
                                                "reason": reason,
                                                "details": str(exc)[:4096],
                                            },
                                        )
                            finally:
                                if self.process and self.process.poll() is None:
                                    self.process.terminate()
                                    with contextlib.suppress(Exception):
                                        self.process.wait(timeout=10)
                                    if self.process.poll() is None:
                                        self.process.kill()
                                        self.process.wait(timeout=10)
                                with self.lock:
                                    self.current = None
                                    self.process = None
                                    self.run_root = None
                    except (httpx.HTTPError, ValueError) as exc:
                        self.log.warning(
                            "Waiting for coordinator: %s", type(exc).__name__
                        )
                self.status(admission_reason=reason)
                self.stopping.wait(2)
        finally:
            self.stopping.set()
            self.heartbeat_stop.set()
            thread.join(timeout=6)
            lock.unlink(missing_ok=True)
            self.http.close()
