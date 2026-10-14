"""Month 2-3 comparison: FedAvg vs CosAvg (base paper) vs CCRA (ours).

Apples-to-apples: every run shares the same seed, non-IID data split, model
initialisation, malicious drones, jammer placement and per-round channel
realisation. Only the aggregation rule changes.

    python run_experiments.py              # run the full matrix (4 runs in parallel)
    python run_experiments.py --only attack_lossy
"""
from __future__ import annotations

import argparse
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
    name, args = job
    t0 = time.time()
    with open(f"results/compare/{name}.log", "w") as log:
        rc = subprocess.call([sys.executable, "run_baseline.py", "--name", name] + args,
                             stdout=log, stderr=subprocess.STDOUT)
    print(f"{'OK ' if rc == 0 else 'FAIL'} {name} ({(time.time() - t0) / 60:.1f} min)", flush=True)
    return rc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*", default=None)
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--aggs", nargs="*", default=None)
    a = p.parse_args()
    import os
    os.makedirs("results/compare", exist_ok=True)
    jobs = []
    for scen, (extra, aggs) in SCENARIOS.items():
        if a.only and scen not in a.only:
            continue
        for agg in aggs:
            if a.aggs and agg not in a.aggs:
                continue
            jobs.append((f"{scen}__{agg}", COMMON + extra + ["--aggregator", agg]))
    print(f"{len(jobs)} runs, {a.parallel} in parallel", flush=True)
    with ThreadPoolExecutor(a.parallel) as ex:
        rcs = list(ex.map(run, jobs))
    sys.exit(max(rcs))


if __name__ == "__main__":
    main()
