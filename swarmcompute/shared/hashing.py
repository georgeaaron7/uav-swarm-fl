import hashlib
import json
from pathlib import Path

EXECUTION_FIELDS = {
    "name",
    "out_dir",
    "data_dir",
    "channel_trace_path",
    "device",
    "threads",
}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def scientific_config(config):
    return {k: v for k, v in config.items() if k not in EXECUTION_FIELDS}


def config_hash(config):
    return hashlib.sha256(canonical(scientific_config(config))).hexdigest()


def job_id(study_id, config, datasets, source):
    return hashlib.sha256(
        canonical(
            {
                "study": study_id,
                "config": scientific_config(config),
                "datasets": datasets,
                "source": source,
            }
        )
    ).hexdigest()
