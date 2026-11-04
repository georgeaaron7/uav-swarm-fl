"""Bounded archives, immutable storage and transactional publication."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from run_context_study import completed

from ..shared.hashing import scientific_config, sha256
from . import models as m
from .database import get, insert, put
from .scheduler import event

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
CHECKPOINT_FILES = {"state.pt", "metadata.json", "COMPLETE"}


def read_json(raw):
    def reject(v):
        raise ValueError(f"non-finite JSON: {v}")

    return json.loads(raw, parse_constant=reject)


def inspect_archive(path, allowed, maximum=512 * 1024**2):
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > len(allowed) or len({i.filename for i in infos}) != len(
                infos
            ):
                raise ValueError("duplicate/unexpected members")
            if sum(i.file_size for i in infos) > maximum:
                raise ValueError("expanded upload too large")
            if any(
                i.filename not in allowed
                or i.is_dir()
                or (i.external_attr >> 16) & 0o170000 == 0o120000
                for i in infos
            ):
                raise ValueError("unsafe archive member")
            if z.testzip():
                raise ValueError("archive checksum invalid")
            return set(z.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid artifact archive") from exc


def verify_checkpoint(path, job, expected_round=None):
    if inspect_archive(path, CHECKPOINT_FILES) != CHECKPOINT_FILES:
        raise ValueError("incomplete checkpoint")
    with zipfile.ZipFile(path) as z:
        meta = read_json(z.read("metadata.json"))
        if meta.get("schema_version") != 1:
            raise ValueError("unsupported checkpoint schema")
        if (
            meta.get("job_id") != job["id"]
            or meta.get("config_sha256") != job["data"]["config_hash"]
        ):
            raise ValueError("checkpoint identity mismatch")
        if meta.get("source_sha256") != job["data"]["source_sha256"]:
            raise ValueError("checkpoint source mismatch")
        for k, v in job["data"]["datasets"].items():
            # Ideal runs have no trace dependency even in mixed-channel studies.
            expected = (
                None
                if k == "trace_sha256" and job["data"]["config"]["channel"] != "trace"
                else v
            )
            if meta.get(k) != expected:
                raise ValueError(f"checkpoint dataset mismatch: {k}")
        rnd = meta["completed_round"]
        if not isinstance(rnd, int) or not 1 <= rnd <= job["data"]["config"]["rounds"]:
            raise ValueError("invalid checkpoint round")
        if expected_round is not None and rnd != expected_round:
            raise ValueError("checkpoint round mismatch")
        with z.open("state.pt") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            checksum != meta["sha256"]
            or z.getinfo("state.pt").file_size != meta["size"]
            or z.read("COMPLETE").decode().strip() != checksum
        ):
            raise ValueError("checkpoint integrity mismatch")
        return meta


def validate_model_container(path):
    # Validate the portable Torch archive without importing torch or unpickling.
    # Full weights_only safe-loading happens in the trusted training worker.
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if not any(n.endswith("/data.pkl") for n in names) or not any(
                "/data/" in n for n in names
            ):
                raise ValueError("final model is not a tensor-state archive")
            if z.testzip():
                raise ValueError("model archive is corrupt")
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid model archive") from exc


def validate_result(path, job):
    names = inspect_archive(path, RESULT_FILES)
    required = {
        "config.json",
        "history.json",
        "summary.json",
        "metrics.csv",
        "final_model.pt",
        "runtime.json",
    }
    if not required <= names:
        raise ValueError("required result files missing")
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        with zipfile.ZipFile(path) as z:
            for name in names:
                with z.open(name) as src, (directory / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        validate_model_container(directory / "final_model.pt")
        config = read_json((directory / "config.json").read_bytes())
        if scientific_config(config) != scientific_config(job["data"]["config"]):
            raise ValueError("result scientific configuration differs")
        check_job = {"seed": job["data"]["seed"], "config": config}
        check_job["config"] = {
            **config,
            "name": directory.name,
            "out_dir": str(directory.parent),
        }
        (directory / "config.json").write_text(json.dumps(check_job["config"]))
        if not completed(check_job):
            raise ValueError("existing completed() validator rejected result")
        history = read_json((directory / "history.json").read_bytes())
        if [r["round"] for r in history] != list(range(1, len(history) + 1)):
            raise ValueError("non-contiguous history")
        summary = read_json((directory / "summary.json").read_bytes())
        if summary["diverged"] and (
            len(history) + 1 != summary["divergence_round"]
            or not summary.get("divergence_stage")
        ):
            raise ValueError("invalid divergence semantics")
        csv_rows = list(csv.DictReader((directory / "metrics.csv").open()))
        if [int(r["round"]) for r in csv_rows] != [r["round"] for r in history]:
            raise ValueError("metrics/history rounds differ")
        for csv_row, record in zip(csv_rows, history):
            for key, value in record.items():
                if (
                    key in csv_row
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    if not math.isfinite(value) or float(csv_row[key]) != value:
                        raise ValueError("metrics/history values differ")
        for row in history:
            for k in (
                "test_acc",
                "test_loss",
                "train_loss",
                "mean_pdr",
                "mean_latency_s",
            ):
                if k in row and (
                    not isinstance(row[k], (int, float)) or not math.isfinite(row[k])
                ):
                    raise ValueError("invalid metrics")
        runtime = read_json((directory / "runtime.json").read_bytes())
        for key in ("source_sha256", "dataset_sha256", "config_sha256"):
            expected = (
                job["data"]["config_hash"]
                if key == "config_sha256"
                else job["data"].get(key, job["data"]["datasets"].get(key))
            )
            if runtime.get(key) != expected:
                raise ValueError(f"result provenance mismatch: {key}")
        expected_trace = (
            job["data"]["datasets"]["trace_sha256"]
            if config["channel"] == "trace"
            else None
        )
        if runtime.get("trace_sha256") != expected_trace:
            raise ValueError("result trace mismatch")
        if runtime.get("provenance", {}).get("job_id") != job["id"]:
            raise ValueError("result job mismatch")
        return summary, history, runtime


class ArtifactStore:
    def __init__(self, db, scheduler):
        self.db, self.scheduler = db, scheduler

    def finalize(self, c, upload_id, worker_id, fence):
        artifact = get(c, m.artifacts, upload_id)
        if not artifact:
            raise ValueError("unknown upload")
        attempt, job = self.scheduler.active(
            c, artifact["attempt_id"], worker_id, fence
        )
        if artifact["data"].get("valid"):
            return artifact
        path = self.db.root / "uploads" / upload_id
        if (
            not path.is_file()
            or path.stat().st_size != artifact["data"]["size"]
            or sha256(path) != artifact["data"]["sha256"]
        ):
            path.unlink(missing_ok=True)
            raise ValueError(
                "upload size/checksum mismatch; upload reset to offset zero"
            )
        if artifact["kind"] == "checkpoint":
            meta = verify_checkpoint(path, job)
            if meta.get("attempt_id") != attempt["id"]:
                raise ValueError("checkpoint attempt mismatch")
        else:
            summary, history, runtime = validate_result(path, job)
            if runtime["provenance"].get("attempt_id") != attempt["id"]:
                raise ValueError("result attempt mismatch")
            artifact["data"].update(summary=summary, history=history, runtime=runtime)
        dest = Path("artifacts") / (artifact["data"]["sha256"] + ".zip")
        if not (self.db.root / dest).exists():
            os.replace(path, self.db.root / dest)
        else:
            path.unlink(missing_ok=True)
        artifact["data"].update(path=str(dest), valid=True)
        put(c, m.artifacts, artifact)
        if artifact["kind"] == "checkpoint":
            insert(
                c,
                m.checkpoints,
                id=upload_id,
                job_id=job["id"],
                attempt_id=attempt["id"],
                round=meta["completed_round"],
                data={
                    "path": str(dest),
                    "sha256": artifact["data"]["sha256"],
                    "size": artifact["data"]["size"],
                    "valid": True,
                    "created": time.time(),
                    "metadata": meta,
                    "retention": "retained",
                },
            )
            current = (
                get(c, m.checkpoints, job["data"]["checkpoint"])
                if job["data"]["checkpoint"]
                else None
            )
            if current is None or current["round"] <= meta["completed_round"]:
                job["data"]["checkpoint"] = upload_id
                put(c, m.jobs, job)
            event(
                c,
                "experiment_checkpointed",
                job_id=job["id"],
                attempt_id=attempt["id"],
                round=meta["completed_round"],
            )
        return artifact

    def complete(self, c, worker_id, attempt_id, fence, artifact_id):
        existing = get(c, m.attempts, attempt_id)
        job = get(c, m.jobs, existing["job_id"]) if existing else None
        if (
            job
            and job["status"] in {"SUCCEEDED", "DIVERGED"}
            and job["data"]["result"] == artifact_id
            and existing["worker_id"] == worker_id
            and existing["data"]["fence"] == fence
        ):
            return job
        attempt, job = self.scheduler.active(c, attempt_id, worker_id, fence)
        artifact = get(c, m.artifacts, artifact_id)
        if (
            not artifact
            or artifact["attempt_id"] != attempt_id
            or artifact["kind"] != "result"
            or not artifact["data"].get("valid")
        ):
            raise ValueError("validated attempt result required")
        path = self.db.root / artifact["data"]["path"]
        if sha256(path) != artifact["data"]["sha256"]:
            raise ValueError("result corrupted after validation")
        status = "DIVERGED" if artifact["data"]["summary"]["diverged"] else "SUCCEEDED"
        job["status"] = status
        job["data"].update(
            result=artifact_id,
            summary=artifact["data"]["summary"],
            current_round=artifact["data"]["summary"]["completed_rounds"],
        )
        attempt["status"] = status
        attempt["data"]["ended"] = time.time()
        put(c, m.attempts, attempt)
        put(c, m.jobs, job)
        event(
            c,
            "experiment_diverged" if status == "DIVERGED" else "experiment_completed",
            job_id=job["id"],
            attempt_id=attempt_id,
        )
        return job
