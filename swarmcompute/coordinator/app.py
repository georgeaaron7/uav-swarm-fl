from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import PROTOCOL_VERSION, __version__
from ..config import DEFAULTS, data_home
from ..shared.schemas import (
    Complete,
    Control,
    Enroll,
    Enrollment,
    Failure,
    Fenced,
    Heartbeat,
    Login,
    Preferences,
    Progress,
    Study,
    Upload,
)
from . import auth
from . import models as m
from .artifacts import ArtifactStore
from .database import Database, attempt_summaries, get, insert, put, rows
from .scheduler import ACTIVE, Conflict, Forbidden, Scheduler, event, settings
from .studies import create_study, plan_study


def public(row):
    if not row:
        return None
    data = {**row, "data": dict(row["data"])}
    for key in ("credential_hash", "password_hash", "fence"):
        data["data"].pop(key, None)
    return data


def create_app(root=None):
    db = Database(root or data_home())
    scheduler = Scheduler(db)
    artifacts = ArtifactStore(db, scheduler)

    @asynccontextmanager
    async def lifespan(app):
        with db.transaction() as c:
            scheduler.reconcile(c)
            event(c, "coordinator_restarted")

        async def reconcile():
            while True:
                await asyncio.sleep(5)
                with db.transaction() as c:
                    scheduler.reconcile(c)

        task = asyncio.create_task(reconcile())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(
        title="SwarmCompute",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.db, app.state.scheduler = db, scheduler
    attempts_by_ip = defaultdict(deque)

    @app.middleware("http")
    async def guard(request, call_next):
        # No browser cookies are accepted: browser mutations require an explicit
        # Authorization header, so cross-origin forms cannot authenticate (CSRF).
        if request.url.path.startswith("/api/"):
            raw_upload = request.method == "PUT" and request.url.path.startswith(
                "/api/v1/uploads/"
            )
            limit = DEFAULTS["max_upload_bytes"] if raw_upload else 1024 * 1024
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > limit:
                return Response("request too large", 413)
            if not raw_upload:
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        return Response("request too large", 413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return Response(
            json.dumps({"detail": str(exc)}), 409, media_type="application/json"
        )

    @app.exception_handler(Forbidden)
    async def forbidden(request, exc):
        return Response(
            json.dumps({"detail": str(exc)}), 403, media_type="application/json"
        )

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return Response(
            json.dumps({"detail": str(exc)}), 400, media_type="application/json"
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return Response(
            '{"detail":"entity already exists or invalid reference"}',
            409,
            media_type="application/json",
        )

    def rate_limit(request):
        key = request.client.host if request.client else "local"
        q = attempts_by_ip[key]
        now = time.monotonic()
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 12:
            raise HTTPException(429, "too many attempts; retry in one minute")
        q.append(now)

    def principal(request: Request):
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise HTTPException(401, "authentication required")
        with db.transaction() as c:
            p = auth.principal(c, header[7:])
        if not p:
            raise HTTPException(401, "credential expired or revoked")
        return p

    def admin(p=Depends(principal)):
        if p["role"] != "admin":
            raise HTTPException(403, "administrator required")
        return p

    def human(p=Depends(principal)):
        if p["role"] not in {"admin", "owner"}:
            raise HTTPException(403, "user login required")
        return p

    def worker(p, id):
        if p["role"] != "worker" or p["id"] != id:
            raise HTTPException(403, "scoped worker credential required")

    def owned(c, p, id, action=None):
        row = get(c, m.workers, id)
        if not row:
            raise HTTPException(404, "worker not found")
        if p["id"] in {id, row["owner_id"]}:
            return row
        if p["role"] == "admin" and (
            action is None
            or action in row["data"].get("preferences", {}).get("admin_permissions", [])
        ):
            return row
        raise HTTPException(403, "owner permission required")

    @app.get("/health")
    def health():
        try:
            with db.transaction() as c:
                c.execute(select(m.settings).limit(1))
            writable = os.access(db.root / "artifacts", os.W_OK)
            return {
                "status": "ok" if writable else "degraded",
                "version": __version__,
                "database": True,
                "storage": writable,
            }
        except Exception:
            return Response(
                '{"status":"unavailable"}', 503, media_type="application/json"
            )

    @app.post("/api/v1/auth/login")
    def login(body: Login, request: Request):
        rate_limit(request)
        with db.transaction() as c:
            credential = auth.login(c, body.username, body.password)
        if not credential:
            raise HTTPException(401, "invalid username or password")
        return {"token": credential}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, p=Depends(principal)):
        with db.transaction() as c:
            c.execute(
                m.sessions.delete().where(
                    m.sessions.c.id
                    == auth.fingerprint(request.headers["authorization"][7:])
                )
            )
        return {"ok": True}

    @app.post("/api/v1/auth/password")
    def password_change(body: dict, p=Depends(human)):
        old, new = body.get("current_password"), body.get("new_password")
        if (
            not isinstance(old, str)
            or not isinstance(new, str)
            or not 12 <= len(new) <= 256
        ):
            raise ValueError("new password must contain 12–256 characters")
        with db.transaction() as c:
            user = get(c, m.users, p["id"])
            try:
                auth.hasher.verify(user["data"]["password_hash"], old)
            except Exception:
                raise HTTPException(403, "current password is incorrect")
            user["data"]["password_hash"] = auth.hasher.hash(new)
            put(c, m.users, user)
            event(c, "password_changed", actor=p["id"])
        return {"ok": True}

    @app.get("/api/v1/auth/me")
    def me(p=Depends(principal)):
        return p

    @app.post("/api/v1/enrollment-codes")
    def enrollment(body: Enrollment, p=Depends(admin)):
        code = auth.token()
        with db.transaction() as c:
            cfg = settings(c)
            if not cfg["enrollment_enabled"]:
                raise Conflict("enrollment disabled")
            insert(
                c,
                m.enrollments,
                id=auth.fingerprint(code),
                expires=time.time() + body.ttl,
                data={"owner": body.owner, "redeemed": False},
            )
            event(c, "enrollment_created", actor=p["id"], owner=body.owner)
        return {"code": code, "expires_in": body.ttl}

    @app.post("/api/v1/workers/enroll")
    def enroll(body: Enroll, request: Request):
        rate_limit(request)
        if body.protocol_version != PROTOCOL_VERSION:
            raise Conflict("incompatible protocol version")
        with db.transaction() as c:
            row = get(c, m.enrollments, auth.fingerprint(body.code))
            cfg = settings(c)
            if (
                not cfg["enrollment_enabled"]
                or not row
                or row["expires"] <= time.time()
                or row["data"]["redeemed"]
            ):
                raise HTTPException(401, "invalid, expired or redeemed enrollment code")
            if (
                len([w for w in rows(c, m.workers) if not w["data"].get("revoked")])
                >= cfg["max_workers"]
            ):
                raise Conflict("worker limit reached")
            owner_name = row["data"]["owner"]
            owner = next(
                (u for u in rows(c, m.users) if u["username"] == owner_name), None
            )
            owner_password = None
            if owner is None:
                owner, owner_password = auth.new_user(c, owner_name)
            if owner["data"]["role"] != "owner":
                raise ValueError("enrollment must name an owner account")
            row["data"]["redeemed"] = True
            put(c, m.enrollments, row)
            id = auth.uid()
            credential = auth.token()
            now = time.time()
            insert(
                c,
                m.workers,
                id=id,
                owner_id=owner["id"],
                last_seen=now,
                data={
                    "name": body.name,
                    "capabilities": body.capabilities,
                    "preferences": body.preferences,
                    "protocol_version": body.protocol_version,
                    "credential_hash": auth.fingerprint(credential),
                    "status": "ONLINE_IDLE"
                    if body.capabilities.get("ready")
                    else "INCOMPATIBLE",
                    "control": "resume" if cfg["automatic_start"] else "pause",
                    "registered": now,
                    "telemetry": {},
                    "revoked": False,
                },
            )
            event(c, "worker_connected", worker_id=id)
        return {
            "worker_id": id,
            "credential": credential,
            "owner_username": owner_name,
            "owner_password": owner_password,
            "settings": cfg,
            "protocol_version": PROTOCOL_VERSION,
        }

    @app.post("/api/v1/workers/{id}/heartbeat")
    def heartbeat(id: str, body: Heartbeat, p=Depends(principal)):
        worker(p, id)
        with db.transaction() as c:
            return scheduler.heartbeat(c, id, body.model_dump(exclude_none=True))

    @app.post("/api/v1/workers/{id}/jobs/claim")
    def claim(id: str, p=Depends(principal)):
        worker(p, id)
        with db.transaction() as c:
            return {"assignment": scheduler.claim(c, id)}

    @app.post("/api/v1/attempts/{id}/progress")
    def progress(id: str, body: Progress, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            attempt, job = scheduler.active(c, id, p["id"], body.fence)
            if body.round > job["data"]["config"]["rounds"]:
                raise ValueError("round exceeds experiment")
            metrics = attempt["data"]["metrics"]
            if metrics and body.round < metrics[-1]["round"]:
                raise Conflict("progress cannot move backwards")
            row = {**body.metrics, "round": body.round}
            if metrics and metrics[-1]["round"] == body.round:
                metrics[-1] = row
            else:
                metrics.append(row)
            attempt["data"].update(runtime=body.runtime, logs=body.logs[-65536:])
            attempt["status"] = "RUNNING"
            put(c, m.attempts, attempt)
            job["status"] = "RUNNING"
            job["data"]["current_round"] = body.round
            put(c, m.jobs, job)
        return {"ok": True}

    @app.post("/api/v1/attempts/{id}/uploads")
    def initialize_upload(id: str, body: Upload, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            scheduler.active(c, id, p["id"], body.fence)
            if body.size > settings(c)["max_upload_bytes"]:
                raise HTTPException(413, "upload too large")
            if (
                shutil.disk_usage(db.root).free
                < body.size + settings(c)["disk_critical_bytes"]
            ):
                raise HTTPException(507, "insufficient artifact storage")
            found = (
                c.execute(
                    select(m.artifacts).where(
                        m.artifacts.c.attempt_id == id,
                        m.artifacts.c.kind == body.kind,
                        m.artifacts.c.data["sha256"].as_string() == body.sha256,
                    )
                )
                .mappings()
                .first()
            )
            existing = dict(found) if found else None
            if existing:
                return public(existing)
            record = insert(
                c,
                m.artifacts,
                id=auth.uid(),
                attempt_id=id,
                kind=body.kind,
                data={
                    "sha256": body.sha256,
                    "size": body.size,
                    "valid": False,
                    "created": time.time(),
                },
            )
            return public(record)

    @app.put("/api/v1/uploads/{id}")
    async def upload_bytes(
        id: str, request: Request, offset: int = 0, p=Depends(principal)
    ):
        if p["role"] != "worker":
            raise HTTPException(403)
        fence = request.headers.get("x-lease-token", "")
        with db.transaction() as c:
            artifact = get(c, m.artifacts, id)
            if not artifact:
                raise HTTPException(404)
            scheduler.active(c, artifact["attempt_id"], p["id"], fence)
            if artifact["data"].get("valid"):
                return {"offset": artifact["data"]["size"]}
            size = artifact["data"]["size"]
        # Each upload has one stream. OS exclusive lock files reject concurrent writes.
        path = db.root / "uploads" / id
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Conflict("upload already in progress")
        os.close(fd)
        try:
            current = path.stat().st_size if path.exists() else 0
            if offset != current:
                raise Conflict(f"resume upload at offset {current}")
            with path.open("ab") as f:
                async for chunk in request.stream():
                    current += len(chunk)
                    if current > size:
                        raise HTTPException(413, "upload exceeds declared size")
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            return {"offset": current}
        except BaseException:
            if path.exists() and path.stat().st_size > size:
                path.unlink()
            raise
        finally:
            lock.unlink(missing_ok=True)

    @app.get("/api/v1/uploads/{id}")
    def upload_status(id: str, request: Request, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            artifact = get(c, m.artifacts, id)
            if not artifact:
                raise HTTPException(404)
            scheduler.active(
                c, artifact["attempt_id"], p["id"], request.headers.get("x-lease-token")
            )
        path = db.root / "uploads" / id
        return {
            "offset": artifact["data"]["size"]
            if artifact["data"].get("valid")
            else (path.stat().st_size if path.exists() else 0)
        }

    @app.post("/api/v1/uploads/{id}/finalize")
    def finalize(id: str, body: Fenced, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            record = artifacts.finalize(c, id, p["id"], body.fence)
            return {
                "id": record["id"],
                "data": {
                    k: v
                    for k, v in record["data"].items()
                    if k not in {"history", "runtime"}
                },
            }

    @app.post("/api/v1/attempts/{id}/complete")
    def complete(id: str, body: Complete, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            return public(
                artifacts.complete(c, p["id"], id, body.fence, body.artifact_id)
            )

    @app.post("/api/v1/attempts/{id}/release")
    def release(id: str, body: Fenced, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            scheduler.release(c, p["id"], id, body.fence)
        return {"ok": True}

    @app.post("/api/v1/attempts/{id}/fail")
    def fail(id: str, body: Failure, p=Depends(principal)):
        if p["role"] != "worker":
            raise HTTPException(403)
        with db.transaction() as c:
            attempt, job = scheduler.active(c, id, p["id"], body.fence)
            attempt["data"]["diagnostics"] = body.details
            scheduler.retry(c, attempt, job, body.reason, time.time())
        return {"ok": True}

    @app.post("/api/v1/workers/{id}/control")
    def control(id: str, body: Control, p=Depends(principal)):
        with db.transaction() as c:
            row = owned(c, p, id, body.action)
            row["data"]["control"] = body.action
            if body.action == "leave":
                row["data"]["control"] = "pause"
                row["data"]["leaving"] = True
            if body.action == "resume":
                row["data"]["leaving"] = False
            put(c, m.workers, row)
            event(c, "worker_control", worker_id=id, actor=p["id"], action=body.action)
        return {"ok": True}

    @app.put("/api/v1/workers/{id}/preferences")
    def worker_preferences(id: str, body: Preferences, p=Depends(principal)):
        with db.transaction() as c:
            row = owned(c, p, id, "preferences")
            values = body.model_dump(exclude_none=True)
            if "admin_permissions" in values and p["id"] not in {id, row["owner_id"]}:
                raise HTTPException(
                    403, "only the owner can grant administrative permissions"
                )
            if "mode" in values and "cpu_threads" not in values:
                from ..worker.resources import MODES

                values["cpu_threads"] = MODES[values["mode"]]
            row["data"]["preferences"].update(values)
            row["data"]["preferences_version"] = (
                row["data"].get("preferences_version", 0) + 1
            )
            put(c, m.workers, row)
            event(
                c,
                "worker_preferences_updated",
                worker_id=id,
                actor=p["id"],
                keys=list(values),
            )
        return {"ok": True}

    @app.post("/api/v1/workers/{id}/revoke")
    def revoke(id: str, p=Depends(principal)):
        with db.transaction() as c:
            row = owned(c, p, id, "leave")
            if any(
                a["worker_id"] == id and a["status"] in ACTIVE
                for a in rows(c, m.attempts)
            ):
                raise Conflict(
                    "checkpoint and release active work before revoking credential"
                )
            row["data"].update(revoked=True, status="OFFLINE")
            put(c, m.workers, row)
            event(c, "worker_left", worker_id=id, actor=p["id"])
        return {"ok": True}

    @app.get("/api/v1/overview")
    def overview(request: Request, p=Depends(human)):
        from ..network import addresses

        with db.transaction() as c:
            scheduler.reconcile(c)
            ws, js, ats, ev = (
                rows(c, m.workers),
                rows(c, m.jobs),
                [
                    {"id": r.id, "status": r.status, "data": {"started": r.started}}
                    for r in c.execute(
                        select(
                            m.attempts.c.id,
                            m.attempts.c.status,
                            m.attempts.c.data["started"].as_float().label("started"),
                        )
                    )
                ],
                rows(c, m.events),
            )
            counts = Counter(j["status"] for j in js)
            terminal = [a for a in ats if a["status"] in {"SUCCEEDED", "DIVERGED"}]
            active_workers = [
                w
                for w in ws
                if w["data"]["status"] != "OFFLINE" and not w["data"].get("revoked")
            ]
            elapsed = max(
                1,
                time.time()
                - min((a["data"]["started"] for a in ats), default=time.time()),
            )
            throughput = len(terminal) / elapsed * 3600 if terminal else None
            cfg = settings(c)
        free = shutil.disk_usage(db.root).free
        return {
            "jobs": dict(counts),
            "total": len(js),
            "terminal": len(terminal),
            "workers": len(ws),
            "online": len(active_workers),
            "busy": sum(w["data"]["status"] == "ONLINE_BUSY" for w in ws),
            "gpu_count": sum(
                w["data"]["capabilities"].get("gpu_count", 0) for w in active_workers
            ),
            "vram_mb": sum(
                w["data"]["capabilities"].get("vram_mb", 0) for w in active_workers
            ),
            "throughput_per_hour": throughput,
            "eta_hours": (len(js) - len(terminal)) / throughput if throughput else None,
            "free_disk_bytes": free,
            "disk_warning": free < cfg["disk_warning_bytes"],
            "addresses": addresses(request.url.port or 8787),
            "events": sorted(ev, key=lambda e: e["created"], reverse=True)[:20],
        }

    @app.get("/api/v1/workers")
    def workers(p=Depends(human)):
        with db.transaction() as c:
            scheduler.reconcile(c)
            return [
                public(w)
                for w in rows(c, m.workers)
                if p["role"] == "admin" or w["owner_id"] == p["id"]
            ]

    @app.get("/api/v1/workers/{id}")
    def worker_detail(id: str, p=Depends(principal)):
        with db.transaction() as c:
            row = owned(c, p, id)
            result = public(row)
            result["attempts"] = [
                public(a) for a in rows(c, m.attempts) if a["worker_id"] == id
            ]
            return result

    @app.get("/api/v1/studies")
    def studies(p=Depends(admin)):
        with db.transaction() as c:
            return rows(c, m.studies)

    @app.post("/api/v1/studies")
    def study_create(body: Study, p=Depends(admin)):
        manifest = plan_study(**body.model_dump())
        with db.transaction() as c:
            id = create_study(c, manifest)
            event(c, "study_created", study_id=id, actor=p["id"])
        return {"id": id, "jobs": len(manifest["jobs"])}

    @app.post("/api/v1/studies/{id}/{action}")
    def study_control(id: str, action: str, p=Depends(admin)):
        if action not in {"start", "pause", "resume"}:
            raise HTTPException(404)
        with db.transaction() as c:
            study = get(c, m.studies, id)
            if not study:
                raise HTTPException(404)
            study["data"]["status"] = "PAUSED" if action == "pause" else "RUNNING"
            put(c, m.studies, study)
            if action != "pause":
                for job in rows(c, m.jobs):
                    if job["study_id"] == id and job["status"] == "PENDING":
                        job["status"] = "QUEUED"
                        put(c, m.jobs, job)
            event(c, "study_" + action, study_id=id, actor=p["id"])
        return {"ok": True}

    @app.get("/api/v1/experiments")
    def jobs(
        status: str | None = None,
        aggregator: str | None = None,
        attack: str | None = None,
        condition: str | None = None,
        seed: int | None = None,
        worker_id: str | None = None,
        p=Depends(admin),
    ):
        with db.transaction() as c:
            scheduler.reconcile(c)
            all_attempts = {a["id"]: a for a in attempt_summaries(c)}
            result = []
            for j in rows(c, m.jobs):
                d = j["data"]
                cfg = d["config"]
                attempt = all_attempts.get(d["current_attempt"])
                if (
                    status
                    and j["status"] != status
                    or aggregator
                    and cfg["aggregator"] != aggregator
                    or attack
                    and cfg["attack"] != attack
                    or condition
                    and not d["scenario"].endswith(condition)
                    or seed is not None
                    and d["seed"] != seed
                    or worker_id
                    and (not attempt or attempt["worker_id"] != worker_id)
                ):
                    continue
                item = public(j)
                item["worker_id"] = attempt["worker_id"] if attempt else None
                item["runtime_s"] = (
                    (attempt["data"].get("ended") or time.time())
                    - attempt["data"]["started"]
                    if attempt
                    else None
                )
                result.append(item)
            return result

    @app.get("/api/v1/experiments/{id}")
    def job_detail(id: str, p=Depends(admin)):
        with db.transaction() as c:
            row = get(c, m.jobs, id)
            if not row:
                raise HTTPException(404)
            result = public(row)
            result["attempts"] = [
                public(a) for a in rows(c, m.attempts) if a["job_id"] == id
            ]
            result["checkpoints"] = [
                public(a) for a in rows(c, m.checkpoints) if a["job_id"] == id
            ]
            artifact = (
                get(c, m.artifacts, row["data"]["result"])
                if row["data"]["result"]
                else None
            )
            result["history"] = artifact["data"]["history"] if artifact else []
            result["runtime"] = artifact["data"]["runtime"] if artifact else None
            return result

    @app.get("/api/v1/checkpoints")
    def checkpoints(p=Depends(admin)):
        with db.transaction() as c:
            return rows(c, m.checkpoints)

    @app.get("/api/v1/artifacts/{id}/download")
    def download(id: str, p=Depends(principal)):
        with db.transaction() as c:
            artifact = get(c, m.artifacts, id)
            if not artifact or not artifact["data"].get("valid"):
                raise HTTPException(404)
            if p["role"] == "worker":
                attempt = get(c, m.attempts, artifact["attempt_id"])
                owned_active = any(
                    a["worker_id"] == p["id"]
                    and a["job_id"] == attempt["job_id"]
                    and a["status"] in ACTIVE
                    and a["expires"] > time.time()
                    for a in rows(c, m.attempts)
                )
                if not owned_active or artifact["kind"] != "checkpoint":
                    raise HTTPException(403)
            elif p["role"] != "admin":
                raise HTTPException(403)
            path = db.root / artifact["data"]["path"]
            from ..shared.hashing import sha256

            if not path.is_file() or sha256(path) != artifact["data"]["sha256"]:
                raise Conflict("artifact corrupted")
        return FileResponse(path, filename=id + ".zip", media_type="application/zip")

    @app.get("/api/v1/events")
    def events(kind: str | None = None, entity: str | None = None, p=Depends(admin)):
        with db.transaction() as c:
            return sorted(
                [
                    e
                    for e in rows(c, m.events)
                    if (not kind or e["kind"] == kind)
                    and (not entity or entity in e["data"].values())
                ],
                key=lambda e: e["created"],
                reverse=True,
            )[:500]

    @app.get("/api/v1/events/download")
    def download_events(p=Depends(admin)):
        with db.transaction() as c:
            result = sorted(
                rows(c, m.events), key=lambda e: e["created"], reverse=True
            )[:500]
        return Response(
            "\n".join(json.dumps(e) for e in result),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=events.ndjson"},
        )

    @app.get("/api/v1/settings")
    def get_settings(p=Depends(admin)):
        with db.transaction() as c:
            return settings(c)

    @app.put("/api/v1/settings")
    def update_settings(body: dict, p=Depends(admin)):
        if set(body) - set(DEFAULTS):
            raise ValueError("unknown setting")
        merged = {**DEFAULTS, **body}
        for key, value in merged.items():
            if isinstance(DEFAULTS[key], bool):
                if type(value) is not bool:
                    raise ValueError(f"{key} must be boolean")
            elif type(value) is not int or value < 1:
                raise ValueError(f"{key} must be positive integer")
        if merged["lease_timeout"] < 3 * merged["heartbeat_interval"]:
            raise ValueError("lease must cover at least 3 heartbeats")
        with db.transaction() as c:
            row = get(c, m.settings, "coordinator")
            if row:
                row["data"] = merged
                put(c, m.settings, row)
            else:
                insert(c, m.settings, id="coordinator", data=merged)
            event(c, "settings_updated", actor=p["id"], keys=list(body))
        return merged

    @app.get("/api/v1/stream")
    async def stream(request: Request, p=Depends(human)):
        async def generate():
            for _ in range(120):
                if await request.is_disconnected():
                    break
                yield "event: refresh\ndata: {}\n\n"
                await asyncio.sleep(5)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    static = Path(__file__).resolve().parents[1] / "static"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        if not (static / "index.html").is_file():
            raise HTTPException(
                503, "dashboard build missing; run npm ci && npm run build in web/"
            )
        return FileResponse(static / "index.html")

    return app
