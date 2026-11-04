"""Read-only validation/export, retention and online SQLite backups."""

import json
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path

from ..shared.hashing import sha256
from . import models as m
from .artifacts import validate_result
from .database import get, put, rows
from .scheduler import ACTIVE, event, settings


def validate_study(db, study_id):
    errors = []
    with db.transaction() as c:
        study = get(c, m.studies, study_id)
        if not study:
            raise ValueError("study not found")
        jobs = [j for j in rows(c, m.jobs) if j["study_id"] == study_id]
        for j in jobs:
            if j["status"] not in {"SUCCEEDED", "DIVERGED"}:
                errors.append(f"{j['id']}: {j['status']}")
                continue
            artifact = get(c, m.artifacts, j["data"]["result"])
            try:
                if not artifact or not artifact["data"].get("valid"):
                    raise ValueError("result not validated")
                path = db.root / artifact["data"]["path"]
                if sha256(path) != artifact["data"]["sha256"]:
                    raise ValueError("result checksum changed")
                validate_result(path, j)
            except (ValueError, OSError, KeyError) as exc:
                errors.append(f"{j['id']}: {exc}")
    return {
        "study_id": study_id,
        "total": len(jobs),
        "valid": not errors,
        "errors": errors,
    }


def export_study(db, study_id, destination):
    report = validate_study(db, study_id)
    if not report["valid"]:
        raise ValueError("study incomplete/invalid: " + "; ".join(report["errors"][:5]))
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("export destination exists; refusing to overwrite")
    temp = destination.with_name(destination.name + ".partial")
    if temp.exists():
        raise FileExistsError("partial export exists; choose a fresh destination")
    temp.mkdir(parents=True)
    try:
        with db.transaction() as c:
            study = get(c, m.studies, study_id)
            manifest = json.loads(json.dumps(study["data"]["manifest"]))
            manifest["swarmcompute"] = {"study_id": study_id, "exported": time.time()}
            for job in rows(c, m.jobs):
                if job["study_id"] != study_id:
                    continue
                artifact = get(c, m.artifacts, job["data"]["result"])
                config = job["data"]["config"]
                directory = temp / f"seed{config['seed']}" / config["name"]
                directory.mkdir(parents=True)
                with zipfile.ZipFile(db.root / artifact["data"]["path"]) as z:
                    for name in z.namelist():
                        with z.open(name) as src, (directory / name).open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                # Preserve frozen planner config, as completed(job, root=export) expects.
                (directory / "config.json").write_text(json.dumps(config, indent=2))
            (temp / "study_manifest.json").write_text(json.dumps(manifest, indent=2))
            (temp / "COMPLETE").write_text(
                "All planned jobs have exactly one validated terminal result.\n"
            )
        temp.rename(destination)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return destination


def backup(db):
    path = db.root / "backups" / f"swarmcompute-{time.time_ns()}.db"
    with sqlite3.connect(db.path) as source, sqlite3.connect(path) as target:
        source.backup(target)
    return path


def maintain(db):
    removed = []
    now = time.time()
    with db.transaction() as c:
        cfg = settings(c)
        active_jobs = {
            a["job_id"] for a in rows(c, m.attempts) if a["status"] in ACTIVE
        }
        # All checkpoints of active jobs are protected. Inactive jobs retain newest two.
        for job in rows(c, m.jobs):
            if job["id"] in active_jobs:
                continue
            cps = sorted(
                [
                    cp
                    for cp in rows(c, m.checkpoints)
                    if cp["job_id"] == job["id"] and cp["data"].get("valid")
                ],
                key=lambda cp: cp["round"],
                reverse=True,
            )
            for cp in cps[cfg["checkpoint_keep"] :]:
                if cp["id"] == job["data"].get("checkpoint"):
                    continue
                (db.root / cp["data"]["path"]).unlink(missing_ok=True)
                cp["data"].update(valid=False, retention="pruned")
                put(c, m.checkpoints, cp)
                art = get(c, m.artifacts, cp["id"])
                if art:
                    art["data"]["valid"] = False
                    put(c, m.artifacts, art)
                removed.append(cp["id"])
        for path in (db.root / "uploads").iterdir():
            if path.stat().st_mtime < now - 86400:
                art = get(c, m.artifacts, path.name)
                attempt = get(c, m.attempts, art["attempt_id"]) if art else None
                if not attempt or attempt["status"] not in ACTIVE:
                    path.unlink(missing_ok=True)
                    removed.append(path.name)
        event(c, "storage_maintenance", removed=removed)
    return removed
