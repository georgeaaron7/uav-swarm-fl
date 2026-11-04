"""Explicit offline handoff of prepared study inputs; never a public data endpoint."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

from .shared.hashing import sha256

FILES = ("cifar10.npz", "context_pilot/cifar10.npz", "channel_traces/deepsense23.npz")


def export_data(data_dir, destination):
    from fl.channel_traces import ChannelTrace
    from run_context_study import pilot_data, source_digest

    root, target = Path(data_dir).resolve(), Path(destination).resolve()
    if target.exists():
        raise FileExistsError("data ZIP already exists; choose a new destination")
    pilot_data(root / "cifar10.npz", root / "context_pilot")
    ChannelTrace(str(root / "channel_traces/deepsense23.npz"), min_sequence_length=200)
    source = source_digest()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True
    ).strip()
    manifest = {
        "schema_version": 1,
        "source_sha256": source,
        "source_commit": revision,
        "files": [
            {
                "path": name,
                "sha256": sha256(root / name),
                "size": (root / name).stat().st_size,
            }
            for name in FILES
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(target.suffix + ".partial")
    if temporary.exists():
        raise FileExistsError("partial data ZIP already exists")
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as archive:
            for name in FILES:
                archive.write(root / name, "data/" + name)
            archive.writestr(
                "data/swarm-data-manifest.json", json.dumps(manifest, indent=2)
            )
        temporary.replace(target)
        if __import__("os").name != "nt":
            target.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": str(target),
        "sha256": sha256(target),
        "size": target.stat().st_size,
        "manifest": manifest,
    }


def verify_data(data_dir):
    from run_context_study import source_digest

    root = Path(data_dir).resolve()
    manifest = json.loads((root / "swarm-data-manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported data manifest")
    if {f["path"] for f in manifest["files"]} != set(FILES) or len(
        manifest["files"]
    ) != len(FILES):
        raise ValueError("unexpected data manifest paths")
    errors = []
    for record in manifest["files"]:
        path = root / record["path"]
        if (
            not path.is_file()
            or path.stat().st_size != record["size"]
            or sha256(path) != record["sha256"]
        ):
            errors.append("missing or mismatched: " + record["path"])
    if source_digest() != manifest["source_sha256"]:
        errors.append(
            "scientific source differs from coordinator; check out the approved source revision"
        )
    return {
        "valid": not errors,
        "errors": errors,
        "files": len(manifest["files"]),
        "source_commit": manifest["source_commit"],
    }
