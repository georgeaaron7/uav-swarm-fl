"""Experiment configuration for the federated learning pipeline."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field


@dataclass
class FLConfig:
    # --- experiment ---
    name: str = "fedavg_baseline"
    seed: int = 42
    out_dir: str = "results"
    device: str = "auto"  # auto | cpu | cuda | mps
    threads: int = 8  # CPU threads; physical core count is fastest (hyperthreads slow it down)
    model: str = "tacticaledge"  # tacticaledge (~156k params) | lightcnn (~403k params)

    # --- data ---
    dataset: str = "cifar10_aerial"  # cifar10_aerial | cifar10
    data_dir: str = "data"
    partition: str = "iid"  # iid | dirichlet
    dirichlet_alpha: float = 0.5  # lower = more non-IID across drones

    # --- swarm / federation ---
    num_clients: int = 10  # number of drones (worker nodes)
    client_fraction: float = 1.0  # fraction of drones participating each round
    rounds: int = 50

    # --- local training (on each drone) ---
    local_epochs: int = 2
    batch_size: int = 64
    lr: float = 0.01
    momentum: float = 0.9
    weight_decay: float = 5e-4

    # --- aggregation: fedavg | cosavg (base paper) | ccra (ours) | ccra_noctx (ablation) ---
    aggregator: str = "fedavg"
    ccra_beta: float = 0.5  # reputation memory
    ccra_gate: float = 0.3  # drones below this trust are excluded

    # --- Byzantine attack ---
    attack: str = "none"  # none | label_flip
    malicious_ids: str = ""  # e.g. "0,3,6"

    # --- wireless channel ---
    channel: str = "ideal"  # ideal | lossy
    jammed_ids: str = ""  # drones whose sector the EW jammer targets, e.g. "2,5,9"
    area_m: float = 800.0
    drone_alt_m: float = 100.0
    mobility_m: float = 10.0  # random-walk step per round
    tx_power_dbm: float = 20.0
    noise_dbm: float = -90.0
    pathloss_exp: float = 2.2
    jammer_power_dbm: float = 10.0
    per_threshold_db: float = 3.0
    per_slope: float = 1.0
    packet_size: int = 1024  # parameters per packet
    noise_scale: float = 1.0  # residual channel noise on delivered packets

    # --- evaluation ---
    eval_every: int = 1
    eval_batch_size: int = 512

    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def parse_args(argv=None) -> FLConfig:
    cfg = FLConfig()
    p = argparse.ArgumentParser(description="Federated learning for UAV swarms")
    for name, value in asdict(cfg).items():
        if isinstance(value, dict):
            continue
        p.add_argument(f"--{name.replace('_', '-')}", type=type(value), default=value)
    args = p.parse_args(argv)
    return FLConfig(**vars(args))
