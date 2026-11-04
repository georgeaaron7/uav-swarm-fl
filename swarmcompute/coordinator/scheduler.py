"""Single-coordinator transactional scheduler. Every publication is attempt-fenced."""

from __future__ import annotations

import shutil
import time

from ..config import DEFAULTS
from . import models as m
from .auth import token, uid
from .database import get, insert, put, rows

TERMINAL = {"SUCCEEDED", "DIVERGED"}
ACTIVE = {"LEASED", "RUNNING", "CHECKPOINTING"}
JOB_STATES = {
    "PENDING",
    "QUEUED",
    *ACTIVE,
    "RETRY_WAIT",
    *TERMINAL,
    "FAILED",
    "NEEDS_ATTENTION",
    "CANCELLED",
}
WORKER_STATES = {
    "ONLINE_IDLE",
    "ONLINE_BUSY",
    "DRAINING",
    "PAUSED",
    "OFFLINE",
    "UNHEALTHY",
    "INCOMPATIBLE",
}
RETRYABLE = {"infrastructure", "network", "shutdown", "artifact_corruption"}


class Conflict(ValueError):
    pass


class Forbidden(ValueError):
    pass


def settings(c):
    row = get(c, m.settings, "coordinator")
    return {**DEFAULTS, **(row["data"] if row else {})}


def event(c, kind, **payload):
    insert(c, m.events, id=uid(), created=time.time(), kind=kind, data=payload)


class Scheduler:
    def __init__(self, database):
        self.db = database

    def active(self, c, attempt_id, worker_id, fence, now=None):
        now = time.time() if now is None else now
        attempt = get(c, m.attempts, attempt_id)
        if not attempt or attempt["worker_id"] != worker_id:
            raise Forbidden("attempt does not belong to this worker")
        job = get(c, m.jobs, attempt["job_id"])
        if (
            attempt["status"] not in ACTIVE
            or attempt["expires"] <= now
            or job["data"]["current_attempt"] != attempt_id
            or attempt["data"]["fence"] != fence
            or job["status"] in TERMINAL
        ):
            raise Conflict("expired or superseded attempt")
        return attempt, job

    def retry(self, c, attempt, job, reason, now):
        cfg = settings(c)
        attempt["status"] = "FAILED"
        attempt["data"].update(ended=now, failure=reason)
        put(c, m.attempts, attempt)
        job["data"]["retry_count"] += 1
        n = job["data"]["retry_count"]
        retry = reason in RETRYABLE and n <= cfg["max_retries"]
        job["status"] = "RETRY_WAIT" if retry else "NEEDS_ATTENTION"
        job["data"].update(
            current_attempt=None,
            retry_at=now
            + min(cfg["retry_delay"] * 2 ** (n - 1), cfg["max_retry_delay"]),
            failure=reason,
        )
        put(c, m.jobs, job)
        event(
            c,
            "retry_scheduled" if retry else "experiment_failed",
            job_id=job["id"],
            attempt_id=attempt["id"],
            reason=reason,
        )

    def reconcile(self, c, now=None):
        now = time.time() if now is None else now
        cfg = settings(c)
        for attempt in rows(c, m.attempts, m.attempts.c.status.in_(ACTIVE)):
            if attempt["status"] in ACTIVE and attempt["expires"] <= now:
                job = get(c, m.jobs, attempt["job_id"])
                if job["data"]["current_attempt"] == attempt["id"]:
                    self.retry(c, attempt, job, "infrastructure", now)
        for worker in rows(c, m.workers):
            if (
                worker["last_seen"] < now - cfg["suspect_timeout"]
                and worker["data"]["status"] != "OFFLINE"
            ):
                worker["data"]["status"] = "OFFLINE"
                put(c, m.workers, worker)
                event(c, "worker_disconnected", worker_id=worker["id"])
        for job in rows(c, m.jobs):
            if job["status"] == "RETRY_WAIT" and job["data"].get("retry_at", 0) <= now:
                job["status"] = "QUEUED"
                put(c, m.jobs, job)

    def eligible(self, worker, job):
        cap = worker["data"]["capabilities"]
        prefs = worker["data"].get("preferences", {})
        if worker["data"].get("control") != "resume" or worker["data"].get("revoked"):
            return False
        if (
            not cap.get("ready")
            or cap.get("source_sha256") != job["data"]["source_sha256"]
        ):
            return False
        if not cap.get("cuda") and job["data"].get("profile") == "final":
            return False
        if not cap.get("cuda") and not prefs.get("allow_cpu", False):
            return False
        if any(
            v and cap.get("datasets", {}).get(k) != v
            for k, v in job["data"]["datasets"].items()
        ):
            return False
        budget = prefs.get("vram_budget_mb", 0)
        required = job["data"].get("required_vram_mb")
        if budget and (required is None or required > budget):
            return False
        telemetry = worker["data"].get("telemetry", {})
        if telemetry.get("on_battery") and not prefs.get("allow_battery", False):
            return False
        if telemetry.get("battery_percent") is not None and telemetry[
            "battery_percent"
        ] < prefs.get("min_battery", 20):
            return False
        if telemetry.get("gpu_temperature") is not None and telemetry[
            "gpu_temperature"
        ] >= prefs.get("max_temperature", 85):
            return False
        if prefs.get("mode") == "light" and telemetry.get("cpu_percent", 0) > 20:
            return False
        return True

    def claim(self, c, worker_id):
        self.reconcile(c)
        worker = get(c, m.workers, worker_id)
        active = [
            a
            for a in rows(c, m.attempts, m.attempts.c.status.in_(ACTIVE))
            if a["status"] in ACTIVE
        ]
        cfg = settings(c)
        if (
            any(a["worker_id"] == worker_id for a in active)
            or len(active) >= cfg["max_concurrent"]
        ):
            return None
        if shutil.disk_usage(self.db.root).free < cfg["disk_critical_bytes"]:
            return None
        studies = {s["id"]: s for s in rows(c, m.studies)}
        jobs = sorted(
            rows(c, m.jobs),
            key=lambda j: (not bool(j["data"]["checkpoint"]), j["created"]),
        )
        for job in jobs:
            if (
                job["status"] != "QUEUED"
                or studies[job["study_id"]]["data"]["status"] != "RUNNING"
            ):
                continue
            if not self.eligible(worker, job):
                continue
            now = time.time()
            id = uid()
            fence = token()
            job["data"]["generation"] += 1
            attempt = insert(
                c,
                m.attempts,
                id=id,
                job_id=job["id"],
                worker_id=worker_id,
                status="LEASED",
                expires=now + cfg["lease_timeout"],
                data={
                    "fence": fence,
                    "generation": job["data"]["generation"],
                    "started": now,
                    "ended": None,
                    "runtime": {},
                    "metrics": [],
                    "logs": "",
                },
            )
            job["status"] = "LEASED"
            job["data"]["current_attempt"] = id
            put(c, m.jobs, job)
            worker["data"].update(status="ONLINE_BUSY", current_attempt=id)
            put(c, m.workers, worker)
            event(
                c,
                "experiment_assigned",
                worker_id=worker_id,
                job_id=job["id"],
                attempt_id=id,
            )
            return {
                "job_id": job["id"],
                "study_id": job["study_id"],
                "attempt_id": id,
                "fence": fence,
                "lease_expires": attempt["expires"],
                "config": job["data"]["config"],
                "source_sha256": job["data"]["source_sha256"],
                "datasets": job["data"]["datasets"],
                "checkpoint": self.valid_checkpoint(c, job),
                "settings": cfg,
            }
        return None

    def valid_checkpoint(self, c, job):
        from .artifacts import verify_checkpoint

        candidates = sorted(
            [
                r
                for r in rows(c, m.checkpoints)
                if r["job_id"] == job["id"] and r["data"].get("valid")
            ],
            key=lambda r: r["round"],
            reverse=True,
        )
        for cp in candidates:
            try:
                verify_checkpoint(
                    self.db.root / cp["data"]["path"], job, expected_round=cp["round"]
                )
                if job["data"]["checkpoint"] != cp["id"]:
                    job["data"]["checkpoint"] = cp["id"]
                    put(c, m.jobs, job)
                return {
                    "id": cp["id"],
                    "round": cp["round"],
                    "sha256": cp["data"]["sha256"],
                }
            except (OSError, ValueError, KeyError):
                cp["data"]["valid"] = False
                put(c, m.checkpoints, cp)
                event(c, "checkpoint_corrupt", checkpoint_id=cp["id"], job_id=job["id"])
        job["data"]["checkpoint"] = None
        put(c, m.jobs, job)
        return None

    def heartbeat(self, c, worker_id, body):
        worker = get(c, m.workers, worker_id)
        now = time.time()
        old = worker["data"]["status"]
        worker["last_seen"] = now
        worker["data"]["telemetry"] = body.get("telemetry", {})
        if body.get("capabilities"):
            worker["data"]["capabilities"] = body["capabilities"]
        version = worker["data"].get("preferences_version", 0)
        if body.get("preferences") and body.get("preferences_version", 0) >= version:
            worker["data"]["preferences"] = body["preferences"]
        control = worker["data"].get("control", "resume")
        worker["data"]["status"] = (
            ("DRAINING" if control == "drain" else "PAUSED")
            if control != "resume"
            else ("ONLINE_BUSY" if body.get("attempt_id") else "ONLINE_IDLE")
        )
        if not worker["data"]["capabilities"].get("ready"):
            worker["data"]["status"] = "INCOMPATIBLE"
        if old == "OFFLINE":
            event(c, "worker_connected", worker_id=worker_id)
        renewed = None
        if body.get("attempt_id"):
            attempt, job = self.active(
                c, body["attempt_id"], worker_id, body.get("fence")
            )
            attempt["expires"] = now + settings(c)["lease_timeout"]
            attempt["status"] = "RUNNING"
            job["status"] = "RUNNING"
            put(c, m.attempts, attempt)
            put(c, m.jobs, job)
            renewed = attempt["expires"]
        else:
            worker["data"]["current_attempt"] = None
        put(c, m.workers, worker)
        return {
            "preferences_version": version,
            "preferences_update": worker["data"]["preferences"]
            if body.get("preferences_version", 0) < version
            else None,
            "lease_expires": renewed,
            "control": control,
            "leaving": worker["data"].get("leaving", False),
            "settings": settings(c),
        }

    def release(self, c, worker_id, attempt_id, fence):
        attempt, job = self.active(c, attempt_id, worker_id, fence)
        if not self.valid_checkpoint(c, job):
            raise Conflict("cannot release before checkpoint publication")
        attempt["status"] = "PAUSED"
        attempt["data"]["ended"] = time.time()
        put(c, m.attempts, attempt)
        job["status"] = "QUEUED"
        job["data"]["current_attempt"] = None
        put(c, m.jobs, job)
        event(
            c,
            "worker_paused",
            worker_id=worker_id,
            job_id=job["id"],
            attempt_id=attempt_id,
        )
