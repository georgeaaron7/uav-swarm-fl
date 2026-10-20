"""Reproducible benchmark matrix for channels, attacks, and aggregators.

Examples
--------
Quick interface check::

    python run_experiments.py --profile smoke --parallel 2

Multi-seed core benchmark::

    python run_experiments.py --profile core --seeds 41 42 43 --rounds 30

Add measurement-driven scenarios::

    python run_experiments.py --profile core --trace-path data/channel_traces/deepsense23.npz
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor


AGGREGATORS = [
    "fedavg", "cosavg", "median", "trimmed_mean", "multi_krum", "fltrust", "ccra", "ccra_noctx"
]
ATTACKS = ["label_flip", "sign_flip", "gaussian", "alie", "ipm"]
MALICIOUS_IDS = "0,3,6"
JAMMED_IDS = "2,5,9"


LEGACY_AGGREGATORS = {
    "attack_lossy": ["fedavg", "cosavg", "ccra", "ccra_noctx"],
    "attack_ideal": ["fedavg", "cosavg", "ccra"],
    "clean_lossy": ["fedavg", "cosavg", "ccra"],
    "clean_ideal": ["fedavg", "cosavg", "ccra"],
}


def scenario_matrix(trace_path: str, profile: str) -> dict[str, list[str]]:
    if profile == "legacy":
        attack = ["--attack", "label_flip", "--malicious-ids", MALICIOUS_IDS]
        lossy = ["--channel", "lossy", "--jammed-ids", JAMMED_IDS]
        return {
            "attack_lossy": attack + lossy,
            "attack_ideal": attack,
            "clean_lossy": lossy,
            "clean_ideal": [],
        }
    common_hfl = [
        "--topology", "hierarchical", "--num-base-stations", "3",
        "--global-sync-every", "5",
    ]
    scenarios = {
        "clean_ideal": [],
        "clean_hfl_ideal": common_hfl,
        "clean_hfl_lossy": common_hfl + ["--channel", "lossy", "--jammed-ids", JAMMED_IDS],
    }
    for attack in ATTACKS:
        scenarios[f"{attack}_ideal"] = [
            "--attack", attack, "--malicious-ids", MALICIOUS_IDS,
        ]
        scenarios[f"{attack}_hfl_ideal"] = common_hfl + [
            "--attack", attack, "--malicious-ids", MALICIOUS_IDS,
        ]
        scenarios[f"{attack}_hfl_lossy"] = common_hfl + [
            "--channel", "lossy", "--jammed-ids", JAMMED_IDS,
            "--attack", attack, "--malicious-ids", MALICIOUS_IDS,
        ]
    if trace_path:
        trace_common = common_hfl + [
            "--channel", "trace", "--channel-trace-path", trace_path,
            "--trace-stride", "5", "--trace-min-sequence-length", "200",
            "--trace-snr-reference-db", "10",
        ]
        scenarios["clean_hfl_trace"] = trace_common
        for attack in ATTACKS:
            scenarios[f"{attack}_hfl_trace"] = trace_common + [
                "--attack", attack, "--malicious-ids", MALICIOUS_IDS,
            ]
    return scenarios


def run(job):
    out_dir, name, args = job
    started = time.time()
    log_path = os.path.join(out_dir, f"{name}.log")
    with open(log_path, "w") as log:
        return_code = subprocess.call(
            [sys.executable, "run_baseline.py", "--name", name] + args,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    print(
        f"{'OK ' if return_code == 0 else 'FAIL'} {name} "
        f"({(time.time() - started) / 60:.1f} min)", flush=True,
    )
    return return_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("legacy", "smoke", "core"), default="core")
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--aggs", nargs="*", default=None)
    parser.add_argument("--seeds", nargs="*", type=int, default=[42])
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--trace-path", default="")
    parser.add_argument("--out-dir", default="results/benchmark")
    args = parser.parse_args()

    scenarios = scenario_matrix(args.trace_path, args.profile)
    selected_aggregators = args.aggs or AGGREGATORS
    unknown = sorted(set(selected_aggregators) - set(AGGREGATORS))
    if unknown:
        raise ValueError(f"unknown aggregators: {', '.join(unknown)}")
    rounds = 2 if args.profile == "smoke" else args.rounds
    common = [
        "--partition", "dirichlet", "--dirichlet-alpha", "0.5",
        "--num-clients", "10", "--rounds", str(rounds),
        "--local-epochs", "1", "--threads", "2",
    ]

    jobs = []
    manifest = {
        "profile": args.profile,
        "seeds": args.seeds,
        "rounds": rounds,
        "aggregators": selected_aggregators,
        "scenarios": {},
        "trace_path": args.trace_path or None,
    }
    for seed in args.seeds:
        out_dir = args.out_dir if len(args.seeds) == 1 else os.path.join(args.out_dir, f"seed{seed}")
        os.makedirs(out_dir, exist_ok=True)
        for scenario, extra in scenarios.items():
            if args.only and scenario not in args.only:
                continue
            manifest["scenarios"][scenario] = extra
            for aggregator in selected_aggregators:
                if args.profile == "legacy" and aggregator not in LEGACY_AGGREGATORS[scenario]:
                    continue
                name = f"{scenario}__{aggregator}"
                if os.path.exists(os.path.join(out_dir, name, "history.json")):
                    continue
                jobs.append((out_dir, name, common + extra + [
                    "--aggregator", aggregator,
                    "--seed", str(seed),
                    "--out-dir", out_dir,
                ]))

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "manifest.json"), "w") as handle:
        json.dump(manifest, handle, indent=2)
    print(f"{len(jobs)} runs, {args.parallel} in parallel", flush=True)
    with ThreadPoolExecutor(args.parallel) as executor:
        return_codes = list(executor.map(run, jobs))
    sys.exit(max(return_codes, default=0))


if __name__ == "__main__":
    main()
