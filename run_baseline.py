"""Month 1: standard (non-robust) FedAvg baseline for a UAV swarm.

Examples
--------
    python run_baseline.py                                  # IID, 10 drones, 50 rounds
    python run_baseline.py --partition dirichlet --dirichlet-alpha 0.5 --name fedavg_noniid
    python run_baseline.py --rounds 2 --name smoke_test     # quick sanity check
"""
from __future__ import annotations

import argparse
from pathlib import Path
import platform
import json
import os
import sys
import time

import numpy as np
import torch

from fl.client import DroneClient
from fl.config import parse_args
from fl.data import CIFAR10_CLASSES, load_dataset, partition
from fl.models import build_model
from fl.server import FederatedServer, NumericalDivergenceError, evaluate
from fl.attacks import validate_attack
from fl.utils import count_params, get_device, set_seed


def main(argv=None):
    execution = argparse.ArgumentParser(add_help=False)
    execution.add_argument("--resume-from")
    execution.add_argument("--checkpoint-dir")
    execution.add_argument("--checkpoint-every-rounds", type=int, default=10)
    execution.add_argument("--checkpoint-every-seconds", type=float, default=180)
    execution.add_argument("--stop-file")
    execution.add_argument("--lease-file")
    execution.add_argument("--progress-file")
    execution.add_argument("--provenance-file")
    options, scientific = execution.parse_known_args(argv)
    cfg = parse_args(scientific)
    if options.checkpoint_every_rounds < 1 or options.checkpoint_every_seconds <= 0:
        raise ValueError("checkpoint intervals must be positive")
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
    if Path(run_dir, "summary.json").exists():
        raise FileExistsError("completed result exists; use a fresh attempt output directory")
    if Path(run_dir, "metrics.csv").exists() and not options.resume_from:
        raise FileExistsError("partial run exists; resume or use a fresh output directory")
    os.makedirs(run_dir, exist_ok=True)
    if options.resume_from and Path(run_dir, "config.json").is_file():
        from fl.checkpoint import scientific_config
        previous = json.loads(Path(run_dir, "config.json").read_text())
        if scientific_config(previous) != scientific_config(cfg):
            raise ValueError("existing run has different scientific configuration")

    print(f"Device: {device} | torch {torch.__version__}")
    train_ds, test_ds, num_classes = load_dataset(cfg.dataset, cfg.data_dir, cfg.seed)
    print(f"Dataset: {cfg.dataset} | train={len(train_ds)} test={len(test_ds)}")

    if cfg.root_samples_per_class < 1:
        raise ValueError("root_samples_per_class must be at least 1")
    generator = torch.Generator().manual_seed(cfg.seed + 99)
    root_idx = torch.cat([
        (train_ds.targets == class_id).nonzero().flatten()[
            torch.randperm(
                int((train_ds.targets == class_id).sum()), generator=generator
            )[:cfg.root_samples_per_class]
        ]
        for class_id in range(num_classes)
    ])
    root_numpy = root_idx.numpy()
    eligible = np.setdiff1d(np.arange(len(train_ds)), root_numpy, assume_unique=False)
    splits = partition(train_ds, cfg, eligible_indices=eligible)
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
        "rate_model": (
            "Shannon capacity upper bound; protocol overhead and retransmissions are excluded"
        ),
        "packet_error_model": "logistic PER curve around configured SINR threshold",
        "delivered_parameter_noise": (
            "none; delivered digital parameters are unchanged" if cfg.noise_scale == 0
            else "simulated additive parameter noise; not a measured digital-link effect"
        ),
        "context_trust": (
            "BS-observed or authenticated telemetry is assumed; adversarial telemetry "
            "spoofing is not modelled"
        ),
        "staleness_model": (
            "deadline excess is converted to round staleness; accept mode is a same-round "
            "down-weighted approximation rather than an event-driven asynchronous queue"
        ),
        "attacker_knowledge": "honest updates in serving cell" if cfg.attack in {"alie", "ipm"} else "local",
        "trace_limitation": (
            "Scenario 23 is a single-BS trace with uncalibrated linear beam power. "
            "Only relative dB variation is measured; absolute SNR is assumed, and "
            "non-reference BS powers are distance-adjusted."
            if cfg.channel == "trace" else None
        ),
        "trace_snr_reference_db": cfg.trace_snr_reference_db if cfg.channel == "trace" else None,
        "trace_snr_spread_scale": cfg.trace_snr_spread_scale if cfg.channel == "trace" else None,
        "trace_stride": cfg.trace_stride if cfg.channel == "trace" else None,
        "trace_replay": (
            "one recorded flight sequence per simulated client with deterministic phase; "
            "sequences are not simultaneous multi-UAV measurements and reverse at endpoints"
            if cfg.channel == "trace" else None
        ),
        "trusted_root": {
            "samples_per_class": cfg.root_samples_per_class,
            "total_samples": int(len(root_idx)),
            "excluded_from_all_client_partitions": True,
            "used_by_aggregator": cfg.aggregator in {"ccra", "ccra_noctx", "ccra_maskonly", "fltrust"},
            "fltrust_step_policy": (
                "repeat the root set to match the median optimizer-step count of "
                "the received clients in each cell"
                if cfg.aggregator == "fltrust" else None
            ),
        },
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
    if cfg.aggregator in {"ccra", "ccra_noctx", "ccra_maskonly", "fltrust"}:
        root_client = DroneClient(-1, train_ds, root_numpy, cfg, device)
        print(f"Trusted reference set: {len(root_idx)} images (disjoint from client data)")

    # Every drone (and the root set) now holds its own copy of its images, so the
    # full training tensor is no longer needed; freeing it roughly halves RAM use.
    del train_ds, splits

    server = FederatedServer(model, clients, test_ds, cfg, device, root_client=root_client)
    from fl.checkpoint import identity, load_checkpoint, restore_rng, save_checkpoint
    provenance = json.loads(Path(options.provenance_file).read_text()) if options.provenance_file else {}
    if options.resume_from:
        state, rng, metadata = load_checkpoint(options.resume_from, identity(cfg))
        server.load_state_dict(state)
        restore_rng(rng)
    Path(run_dir, "config.json").write_text(cfg.to_json())
    Path(run_dir, "runtime.json").write_text(json.dumps({
        "python": platform.python_version(), "torch": str(torch.__version__),
        "numpy": np.__version__, "device": str(device),
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "resumed_from": options.resume_from, "resumed_round": server.completed_round,
        "provenance": provenance, **identity(cfg)}, indent=2))
    checkpoint_root = options.checkpoint_dir or str(Path(run_dir) / "checkpoints")
    last_checkpoint = time.monotonic()

    class PausedAtBoundary(Exception):
        pass

    def on_round(server, record):
        nonlocal last_checkpoint
        stop = bool(options.stop_file and Path(options.stop_file).exists())
        if options.lease_file:
            try:
                lease = json.loads(Path(options.lease_file).read_text())
                stop = stop or time.monotonic() >= lease["expires_monotonic"]
            except (OSError, ValueError, KeyError):
                stop = True
        if (record["round"] % options.checkpoint_every_rounds == 0
                or time.monotonic() - last_checkpoint >= options.checkpoint_every_seconds
                or stop or record["round"] == cfg.rounds):
            save_checkpoint(server, checkpoint_root, provenance)
            last_checkpoint = time.monotonic()
        if options.progress_file:
            target = Path(options.progress_file)
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(record, allow_nan=False))
            temp.replace(target)
        if stop:
            raise PausedAtBoundary()

    t0 = time.time()
    divergence = None
    try:
        history = server.run(run_dir, on_round=on_round)
    except PausedAtBoundary:
        print("PAUSED: durable local checkpoint saved at round boundary", flush=True)
        return {"paused": True, "completed_rounds": server.completed_round}
    except NumericalDivergenceError as exc:
        divergence = {
            "diverged": True,
            "divergence_round": exc.round_number,
            "divergence_stage": exc.stage,
        }
        history = server.history
        server.model.load_state_dict(server.last_valid_global_state)
        print(f"DIVERGED: {exc}", flush=True)
        with open(os.path.join(run_dir, "history.json"), "w") as handle:
            json.dump(history, handle, indent=2, allow_nan=False)
        torch.save(server.model.state_dict(), os.path.join(run_dir, "final_model.pt"))
    elapsed = time.time() - t0

    evaluated = [h for h in history if "test_acc" in h]
    accs = [h["test_acc"] for h in evaluated]
    terminal_evaluation = (
        evaluate(server.model, test_ds, device, cfg.eval_batch_size)
        if divergence else evaluated[-1]
    )
    best = max(evaluated, key=lambda item: item["test_acc"]) if evaluated else None
    completed = history or [{}]
    summary = {
        "name": cfg.name,
        "diverged": divergence is not None,
        "divergence_round": divergence["divergence_round"] if divergence else None,
        "divergence_stage": divergence["divergence_stage"] if divergence else None,
        "completed_rounds": len(history),
        # A diverged run has no valid final-round accuracy. Keeping this null
        # prevents failed runs from being silently averaged with completed runs.
        "final_test_acc": None if divergence else accs[-1],
        "last_finite_test_acc": terminal_evaluation["test_acc"],
        "best_test_acc": max(accs) if accs else terminal_evaluation["test_acc"],
        "best_round": best["round"] if best else 0,
        "mean_last5_test_acc": (sum(accs[-5:]) / len(accs[-5:])) if accs and not divergence else None,
        "final_per_class_acc": dict(zip(CIFAR10_CLASSES, terminal_evaluation["per_class_acc"])),
        "mean_pdr": sum(h.get("mean_pdr", 0.0) for h in history) / len(completed),
        "mean_latency_s": sum(h.get("mean_latency_s", 0.0) for h in history) / len(completed),
        "total_handovers": sum(h.get("handovers", 0) for h in history),
        "mean_honest_rejection_rate": sum(h.get("honest_rejection_rate", 0.0) for h in history) / len(completed),
        "mean_attacker_acceptance_rate": sum(h.get("attacker_acceptance_rate", 0.0) for h in history) / len(completed),
        "mean_max_cell_byzantine_fraction": sum(
            h.get("max_cell_byzantine_fraction", 0.0) for h in history
        ) / len(completed),
        "total_byzantine_majority_cells": sum(h.get("byzantine_majority_cells", 0) for h in history),
        "total_krum_fallback_cells": sum(h.get("krum_fallback_cells", 0) for h in history),
        "total_robustness_bound_violating_cells": sum(
            h.get("robustness_bound_violating_cells", 0) for h in history
        ),
        "total_time_min": server.elapsed_s / 60,
    }
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, allow_nan=False)
    print("\n=== Baseline summary ===")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main(sys.argv[1:])
