"""Aggregation rules. All of them see exactly the same input, so the comparison is fair.

Each received update is a dict:
    id      drone id
    delta   flat update vector as received (lost packets = 0)
    mask    bool vector: True where the packet was delivered
    n       local sample count
    tel     link telemetry: sinr_db, per, pdr

aggregate() returns (global_delta, info) where info["weights"] maps id -> weight.

* FedAvg : McMahan et al. 2017. Trusts everything and ignores the channel.
* CosAvg : base paper (Electronics 2023, 12(18):3938). Each update is weighted by
           its cosine similarity to the mean update, and negative similarity is
           dropped. Channel-unaware.
* CCRA   : ours (Context-Calibrated Robust Aggregation). See CCRA docstring.
"""
from __future__ import annotations

import math

import torch


def _cos(a: torch.Tensor, b: torch.Tensor) -> float:
    return float(torch.dot(a, b) / (a.norm() * b.norm() + 1e-12))


class FedAvg:
    name = "fedavg"

    def __init__(self, cfg):
        self.cfg = cfg

    def aggregate(self, updates):
        n = torch.tensor([u["n"] for u in updates], dtype=torch.float32)
        w = n / n.sum()
        out = sum(wi * u["delta"] for wi, u in zip(w, updates))
        return out, {"weights": {u["id"]: float(wi) for wi, u in zip(w, updates)}}


class CosAvg:
    """Cosine-similarity weighted averaging (base paper).

    ref   = sample-weighted mean of all received updates
    c_k   = cos(delta_k, ref)
    w_k   = max(c_k, 0) * n_k  (normalised)
    """
    name = "cosavg"

    def __init__(self, cfg):
        self.cfg = cfg

    def aggregate(self, updates):
        ref, _ = FedAvg(self.cfg).aggregate(updates)
        cos = [_cos(u["delta"], ref) for u in updates]
        raw = [max(c, 0.0) * u["n"] for c, u in zip(cos, updates)]
        s = sum(raw)
        if s <= 0:
            return torch.zeros_like(ref), {"weights": {u["id"]: 0.0 for u in updates}, "cos": cos}
        w = [r / s for r in raw]
        out = sum(wi * u["delta"] for wi, u in zip(w, updates))
        return out, {"weights": {u["id"]: wi for wi, u in zip(w, updates)},
                     "cos": {u["id"]: c for c, u in zip(cos, updates)}}


class CCRA:
    """Context-Calibrated Robust Aggregation.

    1. Trusted reference direction: the aggregator's TEE holds a small clean
       reference set (50 images/class) and computes a reference update on it each
       round (the `root` argument). Under non-IID data, the median/mean of the
       drone updates is NOT a reliable reference: in our diagnostics, attackers
       and honest-but-skewed drones had the same cosine to it.
       If no root update is given, CCRA falls back to the masked coordinate-wise
       median.
    2. Masked cosine: similarity is computed only on delivered coordinates, so
       packet loss does not make an honest drone look dissimilar.
    3. Channel calibration: residual channel noise at SINR_k is expected to
       reduce cosine by rho_k = 1 / sqrt(1 + (s * 10^(-SINR_k/20))^2). Dividing by
       rho_k removes that expected drop, so legitimate noise is not punished.
    4. Behaviour score: B_k = clip(c_k / median(positive c), 0, 1). Flipped-label
       updates point away from the trusted direction (c < 0) and get B = 0.
    5. Reputation: T_k <- beta * T_k + (1 - beta) * B_k (memory across rounds).
       Drones with T_k < gate are excluded.
    6. Norm clipping to the median per-coordinate RMS (stops scaling attacks).
    7. Masked weighted average: each coordinate is averaged only over the
       drones that delivered it (FedAvg / CosAvg dilute it with zeros).
    """
    name = "ccra"

    def __init__(self, cfg, use_context: bool = True):
        self.cfg = cfg
        self.use_context = use_context
        self.trust: dict[int, float] = {}

    needs_root = True

    def aggregate(self, updates, root=None):
        cfg = self.cfg
        ctx = self.use_context
        D = torch.stack([u["delta"] for u in updates])                 # K x P
        M = torch.stack([u["mask"] for u in updates]) if ctx else torch.ones_like(D, dtype=torch.bool)
        n = torch.tensor([u["n"] for u in updates], dtype=torch.float32)

        # 1. reference direction: trusted root update, else masked coordinate-wise median
        if root is not None:
            ref = root
        else:
            ref = torch.nanmedian(torch.where(M, D, torch.full_like(D, float("nan"))), dim=0).values
            ref = torch.nan_to_num(ref, nan=0.0)

        # 6. norm clipping on per-coordinate RMS over delivered entries
        rms = torch.stack([(D[k][M[k]].pow(2).mean().sqrt() if M[k].any() else torch.tensor(0.0))
                           for k in range(len(updates))])
        med_rms = rms.median()
        scale = torch.clamp(med_rms / (rms + 1e-12), max=1.0)
        D = D * scale[:, None]

        # 2 + 3. masked, channel-calibrated cosine
        cal = []
        for k, u in enumerate(updates):
            m = M[k]
            c = _cos(D[k][m], ref[m]) if m.any() else 0.0
            if ctx and cfg.noise_scale > 0 and math.isfinite(u["tel"]["sinr_db"]):
                rho = 1.0 / math.sqrt(1.0 + (cfg.noise_scale * 10 ** (-u["tel"]["sinr_db"] / 20)) ** 2)
                c = c / rho
            cal.append(c)
        cal_t = torch.tensor(cal)
        pos = cal_t[cal_t > 0]
        med_c = float(pos.median()) if len(pos) else 0.0

        # 4. behaviour score, 5. reputation
        weights = {}
        for k, u in enumerate(updates):
            b = min(max(cal[k] / med_c, 0.0), 1.0) if med_c > 0 else 0.0
            prev = self.trust.get(u["id"], 1.0)
            t = cfg.ccra_beta * prev + (1 - cfg.ccra_beta) * b
            self.trust[u["id"]] = t
            weights[u["id"]] = t if t >= cfg.ccra_gate else 0.0

        w = torch.tensor([weights[u["id"]] for u in updates]) * n          # K
        # 7. masked weighted average
        num = (w[:, None] * D * M).sum(0)
        den = (w[:, None] * M).sum(0)
        out = torch.where(den > 0, num / den.clamp(min=1e-12), torch.zeros_like(num))
        tot = float(w.sum()) or 1.0
        return out, {"weights": {u["id"]: float(wk) / tot for wk, u in zip(w, updates)},
                     "trust": dict(self.trust),
                     "cos_cal": {u["id"]: c for c, u in zip(cal, updates)}}


def build_aggregator(name: str, cfg):
    if name == "fedavg":
        return FedAvg(cfg)
    if name == "cosavg":
        return CosAvg(cfg)
    if name == "ccra":
        return CCRA(cfg, use_context=True)
    if name == "ccra_noctx":  # ablation: CCRA without channel context
        return CCRA(cfg, use_context=False)
    raise ValueError(f"Unknown aggregator '{name}'")
