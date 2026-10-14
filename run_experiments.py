"""Month 2-3 comparison: FedAvg vs CosAvg (base paper) vs CCRA (ours).

Apples-to-apples: every run shares the same seed, non-IID data split, model
initialisation, malicious drones, jammer placement and per-round channel
realisation. Only the aggregation rule changes.

    python run_experiments.py              # run the full matrix (4 runs in parallel)
    python run_experiments.py --only attack_lossy
    python run_experiments.py --seeds 1 2 3 --rounds 50 --out-dir results/multiseed
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

COMMON = ["--partition", "dirichlet", "--dirichlet-alpha", "0.5", "--num-clients", "10",
          "--rounds", "30", "--local-epochs", "1", "--seed", "42", "--threads", "2",
          "--out-dir", "results/compare"]

MALICIOUS = ["--attack", "label_flip", "--malicious-ids", "0,3,6"]   # 3/10 drones (30%)
JAMMED = ["--channel", "lossy", "--jammed-ids", "2,5,9"]               # EW jammer over 3 honest drones

SCENARIOS = {
    "attack_lossy": (MALICIOUS + JAMMED, ["fedavg", "cosavg", "ccra", "ccra_noctx"]),
    "attack_ideal": (MALICIOUS, ["fedavg", "cosavg", "ccra"]),
    "clean_lossy": (JAMMED, ["fedavg", "cosavg", "ccra"]),
    "clean_ideal": ([], ["fedavg", "cosavg", "ccra"]),
}


def run(job):
    out_dir, name, args = job
    t0 = time.time()
    with open(os.path.join(out_dir, f"{name}.log"), "w") as log:
        rc = subprocess.call([sys.executable, "run_baseline.py", "--name", name] + args,
                             stdout=log, stderr=subprocess.STDOUT)
    print(f"{'OK ' if rc == 0 else 'FAIL'} {name} ({(time.time() - t0) / 60:.1f} min)", flush=True)
    return rc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*", default=None)
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--aggs", nargs="*", default=None)
    p.add_argument("--seeds", nargs="*", type=int, default=[42])
    p.add_argument("--rounds", type=int, default=30)
    p.add_argument("--out-dir", default="results/compare")
    a = p.parse_args()
    jobs = []
    for seed in a.seeds:
        # one seed -> results go straight into out_dir; several -> out_dir/seed<N>/
        out_dir = a.out_dir if len(a.seeds) == 1 else os.path.join(a.out_dir, f"seed{seed}")
        os.makedirs(out_dir, exist_ok=True)
        for scen, (extra, aggs) in SCENARIOS.items():
            if a.only and scen not in a.only:
                continue
            for agg in aggs:
                if a.aggs and agg not in a.aggs:
                    continue
                name = f"{scen}__{agg}"
                if os.path.exists(os.path.join(out_dir, name, "history.json")):
                    continue  # already finished (lets an interrupted batch resume)
                jobs.append((out_dir, name, COMMON + extra + [
                    "--aggregator", agg, "--seed", str(seed), "--rounds", str(a.rounds), "--out-dir", out_dir]))
    print(f"{len(jobs)} runs, {a.parallel} in parallel", flush=True)
    with ThreadPoolExecutor(a.parallel) as ex:
        rcs = list(ex.map(run, jobs))
    sys.exit(max(rcs))


if __name__ == "__main__":
    main()
