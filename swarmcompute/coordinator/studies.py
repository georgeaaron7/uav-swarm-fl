"""Reuse the scientific planner and completion validator without importing torch."""

from __future__ import annotations

import time
from argparse import Namespace
from pathlib import Path

import numpy as np

from run_context_study import (
    ATTACKS,
    CONDITIONS,
    METHODS,
    build_jobs,
    digest,
    pilot_data,
    source_digest,
)

from ..shared.hashing import config_hash, job_id
from . import models as m
from .auth import uid
from .database import insert

SUPPORTED_METHODS = set(METHODS) | {"cosavg", "trimmed_mean", "krum", "multi_krum"}


def plan_study(
    name,
    profile,
    aggs,
    data_dir,
    trace_path,
    seeds=None,
    rounds=None,
    attacks=None,
    conditions=None,
):
    if not name or len(name) > 80 or not all(x.isalnum() or x in "-_" for x in name):
        raise ValueError("study name must contain only letters, digits, - and _")
    if profile not in {"pilot", "final"}:
        raise ValueError("unknown profile")
    if not aggs or set(aggs) - SUPPORTED_METHODS:
        raise ValueError(
            "unsupported aggregator; bp_fresh/bp_reuse are absent from this source revision"
        )
    seeds = seeds or ([41, 42] if profile == "pilot" else list(range(41, 51)))
    rounds = rounds if rounds is not None else (2 if profile == "pilot" else 100)
    attacks = ATTACKS if attacks is None else attacks
    conditions = CONDITIONS if conditions is None else conditions
    if (
        not attacks
        or not conditions
        or set(attacks) - set(ATTACKS)
        or set(conditions) - set(CONDITIONS)
    ):
        raise ValueError("unknown or empty attacks/conditions")
    if rounds < 1 or min(seeds) < 0:
        raise ValueError("invalid rounds or seeds")
    if any(len(v) != len(set(v)) for v in (aggs, seeds, attacks, conditions)):
        raise ValueError("duplicate matrix dimensions")
    if profile == "final" and (rounds < 60 or len(seeds) < 10):
        raise ValueError("final profile requires >=60 rounds and >=10 paired seeds")
    data_dir, trace_path = Path(data_dir).resolve(), Path(trace_path).resolve()
    source = data_dir / "cifar10.npz"
    if not source.is_file():
        raise ValueError(f"prepared dataset missing: {source}")
    if any(c != "hfl_ideal" for c in conditions) and not trace_path.is_file():
        raise ValueError(f"prepared trace missing: {trace_path}")
    try:
        with np.load(source, allow_pickle=False) as prepared:
            for split in ("train", "test"):
                images, labels = (
                    prepared[f"x_{split}"],
                    prepared[f"y_{split}"].reshape(-1),
                )
                if (
                    images.shape != (len(labels), 32, 32, 3)
                    or images.dtype != np.uint8
                    or not np.issubdtype(labels.dtype, np.integer)
                ):
                    raise ValueError("prepared CIFAR image/label schema differs")
                if not len(labels) or labels.min() < 0 or labels.max() > 9:
                    raise ValueError("prepared CIFAR labels must be in [0,9]")
            if min(np.bincount(prepared["y_train"].reshape(-1), minlength=10)) <= 50:
                raise ValueError(
                    "training data needs more than 50 examples per class for disjoint root/client data"
                )
        if any(c != "hfl_ideal" for c in conditions):
            from fl.channel_traces import ChannelTrace

            ChannelTrace(str(trace_path), min_sequence_length=200)
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("prepared data validation failed") from exc
    if profile == "pilot":
        data_dir = data_dir / "context_pilot"
        pilot_data(source, data_dir)
    args = Namespace(
        seeds=seeds,
        attacks=attacks,
        conditions=conditions,
        aggs=aggs,
        out_dir=Path("results") / name,
        device="cuda",
        threads=2,
        rounds=rounds,
        trace_path=trace_path,
    )
    jobs = build_jobs(args, data_dir)
    datasets = {
        "dataset_sha256": digest(data_dir / "cifar10.npz"),
        "trace_sha256": digest(trace_path)
        if any(c != "hfl_ideal" for c in conditions)
        else None,
    }
    files = [
        {
            "name": "cifar10.npz",
            "sha256": datasets["dataset_sha256"],
            "size": (data_dir / "cifar10.npz").stat().st_size,
            "version": 1,
            "instructions": "python prepare_data.py; pilot uses existing pilot_data() subset",
        }
    ]
    if datasets["trace_sha256"]:
        files.append(
            {
                "name": "deepsense23.npz",
                "sha256": datasets["trace_sha256"],
                "size": trace_path.stat().st_size,
                "version": 1,
                "instructions": "python scripts/prepare_deepsense23.py --help",
            }
        )
    return {
        "schema_version": 1,
        "study": name,
        "profile": profile,
        "rounds": rounds,
        "seeds": seeds,
        "source_sha256": source_digest(),
        **datasets,
        "dataset_manifest": files,
        "jobs": jobs,
    }


def create_study(c, manifest):
    study_id = uid()
    now = time.time()
    insert(
        c,
        m.studies,
        id=study_id,
        name=manifest["study"],
        created=now,
        data={"manifest": manifest, "status": "PENDING"},
    )
    for ordinal, job in enumerate(manifest["jobs"]):
        datasets = {k: manifest[k] for k in ("dataset_sha256", "trace_sha256")}
        id = job_id(study_id, job["config"], datasets, manifest["source_sha256"])
        insert(
            c,
            m.jobs,
            id=id,
            study_id=study_id,
            status="PENDING",
            created=now + ordinal * 0.000001,
            data={
                **job,
                "config_hash": config_hash(job["config"]),
                "profile": manifest.get("profile", "pilot"),
                "retry_count": 0,
                "generation": 0,
                "current_attempt": None,
                "checkpoint": None,
                "result": None,
                "current_round": 0,
                "datasets": datasets,
                "source_sha256": manifest["source_sha256"],
            },
        )
    return study_id
