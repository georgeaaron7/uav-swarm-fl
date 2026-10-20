"""Data- and model-poisoning attacks used by the simulator."""
from __future__ import annotations

import torch


DATA_ATTACKS = {"label_flip"}
MODEL_ATTACKS = {"sign_flip", "gaussian", "alie", "ipm"}
ALL_ATTACKS = {"none"} | DATA_ATTACKS | MODEL_ATTACKS


def validate_attack(name: str) -> None:
    if name not in ALL_ATTACKS:
        raise ValueError(f"Unknown attack '{name}'")


def craft_model_updates(records: list[dict], attack: str, malicious_ids: set[int], cfg, rnd: int) -> None:
    """Mutate malicious ``record['delta']`` values in place.

    ALIE and IPM use honest updates in the same edge cell. This is an explicit
    strong/omniscient attacker assumption and is recorded by the experiment.
    """
    validate_attack(attack)
    if attack not in MODEL_ATTACKS:
        return
    malicious = [record for record in records if record["id"] in malicious_ids]
    honest = [record["delta"] for record in records if record["id"] not in malicious_ids]
    if not malicious:
        return
    reference = torch.stack(honest) if honest else torch.stack([r["delta"] for r in records])
    mean = reference.mean(dim=0)
    std = reference.std(dim=0, unbiased=False)
    rms = reference.pow(2).mean().sqrt().clamp(min=1e-12)

    for record in malicious:
        if attack == "sign_flip":
            record["delta"] = -cfg.attack_scale * record["delta"]
        elif attack == "gaussian":
            generator = torch.Generator().manual_seed(
                cfg.seed * 65_537 + rnd * 1_009 + record["id"]
            )
            record["delta"] = cfg.attack_scale * rms * torch.randn(
                record["delta"].shape, generator=generator, dtype=record["delta"].dtype
            )
        elif attack == "alie":
            # "A Little Is Enough": remain near the honest coordinate-wise
            # distribution while shifting in the direction opposite its mean.
            direction = torch.sign(mean)
            record["delta"] = mean - cfg.alie_z * std * direction
        elif attack == "ipm":
            # Inner-product manipulation: oppose the honest mean direction.
            record["delta"] = -cfg.ipm_epsilon * mean
        record["attack"] = attack
