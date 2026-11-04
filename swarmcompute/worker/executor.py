from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zipfile
from dataclasses import fields
from pathlib import Path

from fl.config import FLConfig

from ..shared.hashing import scientific_config
from .resources import environment, preferences


def launch(assignment, config, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    scientific = assignment["config"]
    if set(scientific) - {f.name for f in fields(FLConfig)} or scientific.get("extra"):
        raise ValueError("unsupported scientific configuration fields")
    name = scientific["name"]
    if (
        not name
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
    ):
        raise ValueError("unsafe experiment name")
    cfg = {
        **scientific,
        "out_dir": str(root / "output"),
        "data_dir": str(Path(config["data_dir"]).resolve()),
        "channel_trace_path": str(Path(config["trace_path"]).resolve())
        if scientific["channel"] == "trace"
        else "",
        "device": "cpu" if config.get("allow_cpu") else "cuda",
        "threads": preferences(config)["cpu_threads"],
    }
    if scientific_config(cfg) != scientific_config(scientific):
        raise ValueError("execution changed scientific configuration")
    provenance = {k: assignment[k] for k in ("job_id", "study_id", "attempt_id")}
    provenance["worker_id"] = config["worker_id"]
    (root / "provenance.json").write_text(json.dumps(provenance))
    command = [sys.executable, "-m", "run_baseline"]
    for key, value in cfg.items():
        if key != "extra":
            command.extend(["--" + key.replace("_", "-"), str(value)])
    settings = assignment["settings"]
    command.extend(
        [
            "--checkpoint-dir",
            str(root / "checkpoints"),
            "--stop-file",
            str(root / "STOP"),
            "--progress-file",
            str(root / "progress.json"),
            "--provenance-file",
            str(root / "provenance.json"),
            "--checkpoint-every-rounds",
            str(settings["checkpoint_every_rounds"]),
            "--checkpoint-every-seconds",
            str(settings["checkpoint_every_seconds"]),
        ]
    )
    if assignment.get("resume_path"):
        command.extend(["--resume-from", str(assignment["resume_path"])])
    if assignment.get("lease_expires"):
        (root / "lease.json").write_text(
            json.dumps(
                {
                    "expires_monotonic": time.monotonic()
                    + assignment["settings"]["lease_timeout"]
                    - 2
                }
            )
        )
        command.extend(["--lease-file", str(root / "lease.json")])
    log = (root / "training.log").open("w")
    try:
        proc = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment(config),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    finally:
        log.close()
    return proc, root / "output" / name


def archive(directory, destination, names):
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1
    ) as z:
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_file():
                z.write(path, name)
    return Path(destination)


def extract_checkpoint(archive_path, directory):
    # Workers validate safe-loading before resuming, even on a trusted coordinator.
    from fl.checkpoint import load_checkpoint

    allowed = {"state.pt", "metadata.json", "COMPLETE"}
    with zipfile.ZipFile(archive_path) as z:
        if (
            set(z.namelist()) != allowed
            or len(z.infolist()) != 3
            or sum(i.file_size for i in z.infolist()) > 512 * 1024**2
        ):
            raise ValueError("invalid recovery archive")
        Path(directory).mkdir(parents=True, exist_ok=True)
        for name in allowed:
            with z.open(name) as src, (Path(directory) / name).open("wb") as dst:
                import shutil

                shutil.copyfileobj(src, dst)
    load_checkpoint(directory)
    return Path(directory)


def failure_reason(log):
    value = log.lower()
    if "cuda" in value and "out of memory" in value:
        return "cuda_oom"
    if "identity mismatch" in value or "dataset" in value and "missing" in value:
        return "dataset_mismatch"
    if "source mismatch" in value:
        return "source_mismatch"
    return "application"
