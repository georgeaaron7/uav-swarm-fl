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
    topology: str = "centralized"  # centralized | hierarchical
    num_base_stations: int = 3  # used by hierarchical topology
    bs_radius_m: float = 0.0  # 0 = auto (trace footprint, or 30% synthetic area)
    bs_height_m: float = 1.5
    global_sync_every: int = 5  # edge rounds between inter-BS synchronisations
    handover_hysteresis_db: float = 3.0
    handover_ttt: int = 2  # consecutive rounds before a handover is committed

    # --- local training (on each drone) ---
    local_epochs: int = 2
    batch_size: int = 64
    lr: float = 0.01
    momentum: float = 0.9
    weight_decay: float = 5e-4

    # --- aggregation ---
    # fedavg | cosavg | median | trimmed_mean | krum | multi_krum | fltrust
    # | ccra (ours) | ccra_noctx (ablation)
    aggregator: str = "fedavg"
    ccra_beta: float = 0.5  # reputation memory
    ccra_gate: float = 0.3  # drones below this trust are excluded
    trim_ratio: float = 0.2
    krum_byzantine: int = 3
    multi_krum_m: int = 0  # 0 selects the standard n-f-2 candidates
    staleness_decay: float = 0.5

    # --- Byzantine attack ---
    attack: str = "none"  # none | label_flip | sign_flip | gaussian | alie | ipm
    malicious_ids: str = ""  # e.g. "0,3,6"
    attack_scale: float = 5.0  # sign-flip multiplier / Gaussian RMS multiplier
    alie_z: float = 1.5
    ipm_epsilon: float = 0.5

    # --- wireless channel ---
    channel: str = "ideal"  # ideal | lossy | trace
    channel_trace_path: str = ""  # prepared .npz from scripts/prepare_deepsense23.py
    trace_snr_reference_db: float = 15.0  # assumed SNR at median measured beam power
    trace_snr_spread_scale: float = 1.0  # scale measured relative-power variation
    trace_stride: int = 1  # recorded samples advanced per FL round
    trace_min_sequence_length: int = 50  # reject calibration/aborted flight fragments
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
    bandwidth_hz: float = 20e6
    bits_per_parameter: int = 32
    round_deadline_s: float = 2.0
    stale_policy: str = "drop"  # drop | accept

    # --- evaluation ---
    eval_every: int = 1
    eval_batch_size: int = 512
    root_samples_per_class: int = 50  # held out for fair root-based comparisons

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
