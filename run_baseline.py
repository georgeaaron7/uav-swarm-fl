"""Month 1: standard (non-robust) FedAvg baseline for a UAV swarm.

Examples
--------
    python run_baseline.py                                  # IID, 10 drones, 50 rounds
    python run_baseline.py --partition dirichlet --dirichlet-alpha 0.5 --name fedavg_noniid
    python run_baseline.py --rounds 2 --name smoke_test     # quick sanity check
"""
from __future__ import annotations

import json
import os
import sys
import time

import torch

from fl.client import DroneClient
from fl.config import parse_args
from fl.data import CIFAR10_CLASSES, load_dataset, partition
from fl.models import build_model
from fl.server import FederatedServer
from fl.attacks import validate_attack
from fl.utils import count_params, get_device, set_seed


def main(argv=None):
    cfg = parse_args(argv)
    validate_attack(cfg.attack)
    if cfg.topology not in {"centralized", "hierarchical"}:
        raise ValueError("topology must be centralized or hierarchical")
    if cfg.channel not in {"ideal", "lossy", "trace"}:
        raise ValueError("channel must be ideal, lossy, or trace")
    if cfg.stale_policy not in {"drop", "accept"}:
        raise ValueError("stale_policy must be drop or accept")
    set_seed(cfg.seed)
    device = get_device(cfg.device)
    torch.set_num_threads(cfg.threads)

    run_dir = os.path.join(cfg.out_dir, cfg.name)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        f.write(cfg.to_json())

    print(f"Device: {device} | torch {torch.__version__}")
    train_ds, test_ds, num_classes = load_dataset(cfg.dataset, cfg.data_dir, cfg.seed)
    print(f"Dataset: {cfg.dataset} | train={len(train_ds)} test={len(test_ds)}")

    splits = partition(train_ds, cfg)
    clients = [DroneClient(i, train_ds, idx, cfg, device) for i, idx in enumerate(splits)]
    if cfg.attack != "none":
        from fl.channel import parse_ids
        for cid in parse_ids(cfg.malicious_ids):
            if not 0 <= cid < len(clients):
                raise ValueError(f"malicious client id {cid} is outside the swarm")
            clients[cid].make_malicious(cfg.attack, num_classes)
        print(f"Attack: {cfg.attack} on drones {cfg.malicious_ids}")
    print(f"Channel: {cfg.channel}" + (f" | jammer targeting drones {cfg.jammed_ids}" if cfg.jammed_ids else ""))
    print(f"Topology: {cfg.topology}" + (
        f" | {cfg.num_base_stations} base stations | global sync every {cfg.global_sync_every} rounds"
        if cfg.topology == "hierarchical" else ""
    ))

    assumptions = {
        "measured": ["DeepSense Scenario 23 beam power, GPS and IMU"] if cfg.channel == "trace" else [],
        "derived": ["SINR", "Shannon upload rate", "model upload latency", "deadline staleness"],
        "simulated": ["multi-cell topology", "handover", "packet errors", "jamming"],
        "attacker_knowledge": "honest updates in serving cell" if cfg.attack in {"alie", "ipm"} else "local",
        "trace_limitation": (
            "Scenario 23 is a measured single-BS trace; non-reference BS powers are distance-adjusted."
            if cfg.channel == "trace" else None
        ),
    }
    with open(os.path.join(run_dir, "assumptions.json"), "w") as f:
        json.dump(assumptions, f, indent=2)

    swarm_info = {c.client_id: {"num_samples": c.num_samples, "label_hist": c.label_histogram(num_classes)}
                  for c in clients}
    with open(os.path.join(run_dir, "swarm_partition.json"), "w") as f:
        json.dump({"classes": CIFAR10_CLASSES, "drones": swarm_info}, f, indent=2)
    print(f"Swarm: {cfg.num_clients} drones, partition={cfg.partition}, "
          f"samples/drone min={min(c.num_samples for c in clients)} max={max(c.num_samples for c in clients)}")

    set_seed(cfg.seed)  # identical initial weights for every method
    model = build_model(cfg.model, num_classes)
    print(f"Model: {type(model).__name__} ({count_params(model):,} params) | aggregator={cfg.aggregator}")

    root_client = None
    if cfg.aggregator in {"ccra", "ccra_noctx", "fltrust"}:
        # Trusted reference set held in the aggregator's TEE: 50 clean images per class.
        g = torch.Generator().manual_seed(cfg.seed + 99)
        ref_idx = torch.cat([(train_ds.targets == c).nonzero().flatten()[
            torch.randperm(int((train_ds.targets == c).sum()), generator=g)[:50]] for c in range(num_classes)])
        root_client = DroneClient(-1, train_ds, ref_idx.numpy(), cfg, device)
        print(f"Trusted reference set: {len(ref_idx)} images")

    # Every drone (and the root set) now holds its own copy of its images, so the
    # full training tensor is no longer needed; freeing it roughly halves RAM use.
    del train_ds, splits

    server = FederatedServer(model, clients, test_ds, cfg, device, root_client=root_client)
    t0 = time.time()
    history = server.run(run_dir)
    elapsed = time.time() - t0

    evaluated = [h for h in history if "test_acc" in h]
    accs = [h["test_acc"] for h in evaluated]
    best = max(evaluated, key=lambda item: item["test_acc"])
    summary = {
        "name": cfg.name,
        "final_test_acc": accs[-1],
        "best_test_acc": max(accs),
        "best_round": best["round"],
        "mean_last5_test_acc": sum(accs[-5:]) / len(accs[-5:]),
        "final_per_class_acc": dict(zip(CIFAR10_CLASSES, history[-1]["per_class_acc"])),
        "mean_pdr": sum(h["mean_pdr"] for h in history) / len(history),
        "mean_latency_s": sum(h["mean_latency_s"] for h in history) / len(history),
        "total_handovers": sum(h["handovers"] for h in history),
        "mean_honest_rejection_rate": sum(h["honest_rejection_rate"] for h in history) / len(history),
        "mean_attacker_acceptance_rate": sum(h["attacker_acceptance_rate"] for h in history) / len(history),
        "total_time_min": elapsed / 60,
    }
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("\n=== Baseline summary ===")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main(sys.argv[1:])
