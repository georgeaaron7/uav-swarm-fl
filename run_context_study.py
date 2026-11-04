"""Plan and run the controlled context study; see docs/CONTEXT_STUDY.md."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from fl.config import FLConfig

REPO = Path(__file__).resolve().parent
METHODS = ["fedavg", "median", "fltrust", "ccra_noctx", "ccra_maskonly", "ccra"]
CONDITIONS = ["hfl_ideal", "hfl_trace", "hfl_trace_stress"]
ATTACKS = ["clean", "sign_flip", "alie", "ipm"]


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_digest():
    paths = sorted((REPO / "fl").glob("*.py")) + [REPO / "run_baseline.py", Path(__file__)]
    hasher = hashlib.sha256()
    for path in paths:
        hasher.update(path.name.encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def read_json(path):
    def reject(value):
        raise ValueError(f"non-finite JSON value: {value}")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def pilot_data(source, destination):
    """Fixed balanced real CIFAR subset, used only for pipeline validation."""
    destination.mkdir(parents=True, exist_ok=True)
    with np.load(source, allow_pickle=False) as data:
        result = {}
        for split, per_class in (("train", 200), ("test", 50)):
            labels = data[f"y_{split}"].reshape(-1)
            indices = np.concatenate([np.flatnonzero(labels == c)[:per_class] for c in range(10)])
            if len(indices) != 10 * per_class:
                raise ValueError("pilot needs at least 200 train and 50 test examples per class")
            result[f"x_{split}"] = data[f"x_{split}"][indices]
            result[f"y_{split}"] = labels[indices]
    path = destination / "cifar10.npz"
    if path.exists():
        with np.load(path, allow_pickle=False) as existing:
            if any(not np.array_equal(existing[key], value) for key, value in result.items()):
                raise ValueError("existing pilot dataset differs; use a new data directory")
    else:
        np.savez_compressed(path, **result)
    return path


def build_jobs(args, data_dir):
    jobs = []
    for seed in args.seeds:
        # Separate RNG stream; same identities across methods, attacks, and severity.
        rng = np.random.default_rng(np.random.SeedSequence([seed, 8_031_927]))
        malicious = ",".join(map(str, sorted(rng.choice(10, 3, replace=False))))
        for attack in args.attacks:
            for condition in args.conditions:
                for method in args.aggs:
                    scenario = f"{attack}_{condition}"
                    cfg = FLConfig(
                        name=f"{scenario}__{method}", seed=seed,
                        out_dir=str(args.out_dir / f"seed{seed}"),
                        data_dir=str(data_dir), device=args.device, threads=args.threads,
                        num_clients=10, topology="hierarchical", num_base_stations=3,
                        global_sync_every=5, partition="dirichlet", dirichlet_alpha=0.5,
                        rounds=args.rounds, local_epochs=1,
                        aggregator=method, attack="none" if attack == "clean" else attack,
                        malicious_ids="" if attack == "clean" else malicious,
                        channel="ideal" if condition == "hfl_ideal" else "trace",
                        channel_trace_path="" if condition == "hfl_ideal" else str(args.trace_path),
                        trace_snr_reference_db=5.0 if condition == "hfl_trace_stress" else 15.0,
                        trace_stride=5, trace_min_sequence_length=200,
                        noise_scale=0.0, jammed_ids="", stale_policy="drop",
                    )
                    jobs.append({"scenario": scenario, "seed": seed, "config": asdict(cfg)})
    return jobs


def job_directory(job, root=None):
    cfg = job["config"]
    if root is not None:
        return Path(root) / f"seed{job['seed']}" / cfg["name"]
    return Path(cfg["out_dir"]) / cfg["name"]


def completed(job, root=None):
    """Never reuse a crashed run just because history.json happens to exist."""
    cfg = job["config"]
    directory = job_directory(job, root)
    try:
        if read_json(directory / "config.json") != cfg:
            return False
        summary = read_json(directory / "summary.json")
        history = read_json(directory / "history.json")
        if not isinstance(summary.get("diverged"), bool):
            return False
        if summary.get("completed_rounds") != len(history):
            return False
        if not (directory / "final_model.pt").is_file():
            return False
        if summary["diverged"]:
            rnd = summary.get("divergence_round")
            return isinstance(rnd, int) and 1 <= rnd <= cfg["rounds"] and len(history) < rnd
        accuracy = summary.get("final_test_acc")
        return (
            len(history) == cfg["rounds"]
            and [row["round"] for row in history] == list(range(1, cfg["rounds"] + 1))
            and isinstance(accuracy, (int, float)) and math.isfinite(accuracy)
            and 0 <= accuracy <= 1
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def run_job(job):
    cfg = job["config"]
    Path(cfg["out_dir"]).mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(REPO / "run_baseline.py")]
    for key, value in cfg.items():
        if key != "extra":
            command.extend(["--" + key.replace("_", "-"), str(value)])
    log = Path(cfg["out_dir"]) / (cfg["name"] + ".log")
    with log.open("w") as handle:
        result = subprocess.run(command, cwd=REPO, stdout=handle, stderr=subprocess.STDOUT)
    success = result.returncode == 0 and completed(job)
    print(f"{'OK' if success else 'FAIL'} seed{cfg['seed']}/{cfg['name']}", flush=True)
    return success


def main(argv=None):
    import torch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["pilot", "final"], default="pilot")
    parser.add_argument("--trace-path", type=Path, default=REPO / "data/channel_traces/deepsense23.npz")
    parser.add_argument("--data-dir", type=Path, default=REPO / "data")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--rounds", type=int)
    parser.add_argument("--aggs", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--attacks", nargs="+", choices=ATTACKS, default=ATTACKS)
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=CONDITIONS)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--meaningful-effect-pp", type=float, default=1.0)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args(argv)
    args.seeds = args.seeds or ([41, 42] if args.profile == "pilot" else list(range(41, 51)))
    args.rounds = args.rounds if args.rounds is not None else (2 if args.profile == "pilot" else 100)
    if min(args.rounds, args.threads, args.parallel) < 1 or min(args.seeds) < 0:
        parser.error("rounds, threads, parallel must be positive; seeds must be nonnegative")
    for name in ("seeds", "aggs", "attacks", "conditions"):
        if len(getattr(args, name)) != len(set(getattr(args, name))):
            parser.error(f"duplicate {name} would overwrite jobs")
    args.out_dir = (args.out_dir or REPO / f"results/context_{args.profile}").resolve()
    args.data_dir, args.trace_path = args.data_dir.resolve(), args.trace_path.resolve()
    if args.profile == "final" and args.rounds < 60:
        parser.error("final profile requires at least 60 rounds; use pilot for interface checks")
    if args.profile == "final" and len(args.seeds) < 10:
        parser.error("final profile requires at least 10 paired seeds")
    if not math.isfinite(args.meaningful_effect_pp) or args.meaningful_effect_pp <= 0:
        parser.error("meaningful effect must be a finite positive number of percentage points")
    source_data = args.data_dir / "cifar10.npz"
    if not source_data.exists():
        parser.error(f"prepared CIFAR dataset missing: {source_data}")
    if any(c != "hfl_ideal" for c in args.conditions) and not args.trace_path.exists():
        parser.error(f"prepared trace missing: {args.trace_path}")
    data_dir = args.data_dir
    if args.profile == "pilot":
        data_dir = args.data_dir / "context_pilot"
        pilot_data(source_data, data_dir)
    jobs = build_jobs(args, data_dir)
    manifest = {
        "schema_version": 1, "study": "context_ablation", "profile": args.profile,
        "rounds": args.rounds, "seeds": args.seeds,
        "source_sha256": source_digest(),
        "dataset_sha256": digest(data_dir / "cifar10.npz"),
        "trace_sha256": digest(args.trace_path) if any(c != "hfl_ideal" for c in args.conditions) else None,
        "runtime": {"python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__},
        "hypothesis": "CCRA minus mask-only accuracy gain increases under channel stress",
        "meaningful_effect_pp": args.meaningful_effect_pp,
        "primary_estimand": (
            "mean over seeds of mean over attacked scenarios of "
            "[(CCRA - mask-only) at 5 dB - (CCRA - mask-only) at 15 dB]"
        ),
        "jobs": jobs,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "study_manifest.json"
    if path.exists() and read_json(path) != manifest:
        raise SystemExit("study manifest differs (source, data, runtime, or design); use a new --out-dir")
    write_json(path, manifest)
    pending = [job for job in jobs if not completed(job)]
    print(f"{len(jobs)} planned; {len(jobs) - len(pending)} terminal; {len(pending)} pending", flush=True)
    if args.plan_only:
        return
    (args.out_dir / "COMPLETE").unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        results = list(executor.map(run_job, pending))
    if not all(results) or not all(completed(job) for job in jobs):
        raise SystemExit("study incomplete; inspect failed logs, then rerun the identical command")
    (args.out_dir / "COMPLETE").write_text("All planned runs terminal; numerical divergence remains an experimental outcome.\n")


if __name__ == "__main__":
    main()
