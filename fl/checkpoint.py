"""Versioned, safe, CPU-portable round-boundary checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

SCHEMA_VERSION = 1
EXECUTION_FIELDS = {
    "name",
    "out_dir",
    "data_dir",
    "channel_trace_path",
    "device",
    "threads",
}


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def scientific_config(cfg):
    values = asdict(cfg) if not isinstance(cfg, dict) else cfg
    return {k: v for k, v in values.items() if k not in EXECUTION_FIELDS}


def identity(cfg):
    from run_context_study import source_digest

    config_hash = hashlib.sha256(
        json.dumps(
            scientific_config(cfg),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    data = Path(cfg.data_dir) / "cifar10.npz"
    return {
        "config_sha256": config_hash,
        "source_sha256": source_digest(),
        "dataset_sha256": digest(data) if data.is_file() else None,
        "trace_sha256": digest(cfg.channel_trace_path)
        if cfg.channel == "trace"
        else None,
    }


def pack(value):
    if isinstance(value, np.ndarray):
        return {"__numpy__": True, "dtype": str(value.dtype), "data": value.tolist()}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {k: pack(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(pack(v) for v in value)
    if isinstance(value, list):
        return [pack(v) for v in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise TypeError(f"unsupported checkpoint type {type(value).__name__}")


def unpack(value):
    if isinstance(value, dict):
        if value.get("__numpy__") is True:
            return np.array(value["data"], dtype=value["dtype"])
        return {k: unpack(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(unpack(v) for v in value)
    if isinstance(value, list):
        return [unpack(v) for v in value]
    return value


def rng_state():
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }


def restore_rng(state):
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])
    if state["cuda"] and torch.cuda.is_available():
        if len(state["cuda"]) != torch.cuda.device_count():
            raise ValueError("CUDA device count differs; cannot restore RNG state")
        torch.cuda.set_rng_state_all(state["cuda"])


def save_checkpoint(server, root, provenance=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rnd = server.completed_round
    target = root / f"round_{rnd:04d}"
    if target.exists():
        load_checkpoint(target, identity(server.cfg))
        return target
    temp = Path(tempfile.mkdtemp(prefix=".checkpoint-", dir=root))
    try:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "state": pack(server.state_dict()),
            "rng": pack(rng_state()),
        }
        with (temp / "state.pt").open("wb") as f:
            torch.save(payload, f)
            f.flush()
            os.fsync(f.fileno())
        metadata = {
            **identity(server.cfg),
            **(provenance or {}),
            "schema_version": SCHEMA_VERSION,
            "completed_round": rnd,
            "created_at": time.time(),
            "torch": str(torch.__version__),
            "size": (temp / "state.pt").stat().st_size,
            "sha256": digest(temp / "state.pt"),
        }
        (temp / "metadata.json").write_text(
            json.dumps(metadata, indent=2, allow_nan=False)
        )
        (temp / "COMPLETE").write_text(metadata["sha256"])
        load_checkpoint(temp, identity(server.cfg))
        for filename in ("metadata.json", "COMPLETE"):
            with (temp / filename).open("rb") as handle:
                os.fsync(handle.fileno())
        os.replace(temp, target)
        if os.name != "nt":
            fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return target


def load_checkpoint(path, expected=None):
    path = Path(path)
    metadata = json.loads((path / "metadata.json").read_text())
    if (
        metadata.get("schema_version") != SCHEMA_VERSION
        or not (path / "COMPLETE").is_file()
    ):
        raise ValueError("incomplete or unsupported checkpoint")
    state_path = path / "state.pt"
    if (
        state_path.stat().st_size != metadata["size"]
        or digest(state_path) != metadata["sha256"]
    ):
        raise ValueError("checkpoint checksum/size mismatch")
    for k, v in (expected or {}).items():
        if metadata.get(k) != v:
            raise ValueError(f"checkpoint identity mismatch: {k}")
    payload = torch.load(state_path, weights_only=True, map_location="cpu")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported state schema")
    state = unpack(payload["state"])
    rnd = metadata["completed_round"]
    if state["completed_round"] != rnd or [
        h["round"] for h in state["history"]
    ] != list(range(1, rnd + 1)):
        raise ValueError("checkpoint round history inconsistent")
    return state, unpack(payload["rng"]), metadata


def latest_valid(root, expected=None):
    for path in sorted(Path(root).glob("round_*"), reverse=True):
        try:
            load_checkpoint(path, expected)
            return path
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
    return None
