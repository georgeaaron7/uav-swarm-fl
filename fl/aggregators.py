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


def _stale_factor(update, cfg) -> float:
    return math.exp(-getattr(cfg, "staleness_decay", 0.0) * update.get("staleness", 0))


def _masked_weighted_average(D: torch.Tensor, M: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    num = (weights[:, None] * D * M).sum(0)
    den = (weights[:, None] * M).sum(0)
    return torch.where(den > 0, num / den.clamp(min=1e-12), torch.zeros_like(num))


class FedAvg:
    name = "fedavg"

    def __init__(self, cfg):
        self.cfg = cfg

    def aggregate(self, updates):
        n = torch.tensor(
            [u["n"] * _stale_factor(u, self.cfg) for u in updates], dtype=torch.float32
        )
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


class CoordinateMedian:
    name = "median"

    def __init__(self, cfg):
        self.cfg = cfg

    def aggregate(self, updates):
        D = torch.stack([u["delta"] for u in updates])
        M = torch.stack([u["mask"] for u in updates])
        masked = torch.where(M, D, torch.full_like(D, float("nan")))
        out = torch.nanmedian(masked, dim=0).values
        out = torch.nan_to_num(out, nan=0.0)
        equal = 1.0 / len(updates)
        return out, {"weights": {u["id"]: equal for u in updates}}


class TrimmedMean:
    name = "trimmed_mean"

    def __init__(self, cfg):
        self.cfg = cfg

    def aggregate(self, updates):
        ratio = getattr(self.cfg, "trim_ratio", 0.2)
        if not 0 <= ratio < 0.5:
            raise ValueError("trim_ratio must be in [0, 0.5)")
        D = torch.stack([u["delta"] for u in updates])
        M = torch.stack([u["mask"] for u in updates])
        values = torch.where(M, D, torch.full_like(D, float("inf")))
        values = values.sort(dim=0).values
        counts = M.sum(dim=0)
        trim = torch.floor(counts * ratio).long()
        rank = torch.arange(len(updates))[:, None]
        keep = (rank >= trim[None, :]) & (rank < (counts - trim)[None, :])
        safe = torch.where(keep, values, torch.zeros_like(values))
        out = safe.sum(0) / keep.sum(0).clamp(min=1)
        equal = 1.0 / len(updates)
        return out, {"weights": {u["id"]: equal for u in updates}}


def _pair_distance(a: dict, b: dict) -> torch.Tensor:
    overlap = a["mask"] & b["mask"]
    if not overlap.any():
        return torch.tensor(float("inf"))
    diff = a["delta"][overlap] - b["delta"][overlap]
    # Normalize for different overlap sizes so losses do not look artificially close.
    return diff.pow(2).mean()


class MultiKrum:
    name = "multi_krum"

    def __init__(self, cfg, single: bool = False):
        self.cfg = cfg
        self.single = single
        self.name = "krum" if single else "multi_krum"

    def aggregate(self, updates):
        n = len(updates)
        f = min(getattr(self.cfg, "krum_byzantine", 0), max(0, n - 3))
        neighbour_count = n - f - 2
        if neighbour_count < 1:
            raise ValueError("Krum requires at least f + 3 received updates")
        scores = []
        for i, update in enumerate(updates):
            distances = sorted(
                float(_pair_distance(update, other))
                for j, other in enumerate(updates) if i != j
            )
            scores.append(sum(distances[:neighbour_count]))
        order = sorted(range(n), key=lambda idx: scores[idx])
        requested = getattr(self.cfg, "multi_krum_m", 0)
        selected_count = 1 if self.single else (requested or neighbour_count)
        selected = order[:min(selected_count, n)]
        chosen = [updates[idx] for idx in selected]
        D = torch.stack([u["delta"] for u in chosen])
        M = torch.stack([u["mask"] for u in chosen])
        weights = torch.tensor(
            [u["n"] * _stale_factor(u, self.cfg) for u in chosen], dtype=torch.float32
        )
        out = _masked_weighted_average(D, M, weights)
        total = float(weights.sum()) or 1.0
        result_weights = {u["id"]: 0.0 for u in updates}
        for update, weight in zip(chosen, weights):
            result_weights[update["id"]] = float(weight) / total
        return out, {
            "weights": result_weights,
            "krum_scores": {u["id"]: scores[idx] for idx, u in enumerate(updates)},
            "selected": [u["id"] for u in chosen],
            "effective_f": f,
        }


class FLTrust:
    name = "fltrust"
    needs_root = True

    def __init__(self, cfg):
        self.cfg = cfg

    def aggregate(self, updates, root=None):
        if root is None:
            raise ValueError("FLTrust requires a trusted root update")
        D = torch.stack([u["delta"] for u in updates])
        M = torch.stack([u["mask"] for u in updates])
        scores, normalized = [], []
        for idx, update in enumerate(updates):
            mask = M[idx]
            score = max(_cos(D[idx][mask], root[mask]), 0.0) if mask.any() else 0.0
            scores.append(score * _stale_factor(update, self.cfg))
            local_norm = D[idx][mask].norm() if mask.any() else torch.tensor(0.0)
            root_norm = root[mask].norm() if mask.any() else torch.tensor(0.0)
            scale = root_norm / (local_norm + 1e-12)
            normalized.append(D[idx] * scale)
        weights = torch.tensor(scores, dtype=torch.float32)
        if float(weights.sum()) <= 0:
            return torch.zeros_like(root), {"weights": {u["id"]: 0.0 for u in updates}}
        Dn = torch.stack(normalized)
        out = _masked_weighted_average(Dn, M, weights)
        weights /= weights.sum()
        return out, {
            "weights": {u["id"]: float(w) for u, w in zip(updates, weights)},
            "trust_score": {u["id"]: float(s) for u, s in zip(updates, scores)},
        }


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
        use_context = self.use_context
        D = torch.stack([u["delta"] for u in updates])                 # K x P
        M = (torch.stack([u["mask"] for u in updates]) if use_context
             else torch.ones_like(D, dtype=torch.bool))
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
            if use_context and cfg.noise_scale > 0 and math.isfinite(u["tel"]["sinr_db"]):
                rho = 1.0 / math.sqrt(1.0 + (cfg.noise_scale * 10 ** (-u["tel"]["sinr_db"] / 20)) ** 2)
                c = c / rho
            cal.append(c)
        cal_t = torch.tensor(cal)
        pos = cal_t[cal_t > 0]
        med_c = float(pos.median()) if len(pos) else 0.0

        # 4. behaviour score, 5. reputation. Poor links reduce the strength of
        # the evidence rather than being treated as evidence of maliciousness.
        weights = {}
        for k, u in enumerate(updates):
            b = min(max(cal[k] / med_c, 0.0), 1.0) if med_c > 0 else 0.0
            prev = self.trust.get(u["id"], 1.0)
            context = u.get("ctx", {}) if use_context else {}
            pdr = float(u["tel"].get("pdr", 1.0))
            reliability = float(context.get("reliability", 1.0))
            handover_factor = 0.5 if context.get("handover", False) else 1.0
            distance = float(context.get("distance_m", 0.0))
            geometry_factor = 1.0 / (1.0 + distance / max(cfg.area_m, 1.0))
            speed = abs(float(context.get("speed_mps", 0.0)))
            mobility_factor = 1.0 / (1.0 + speed / 30.0)
            evidence = min(max(
                pdr * reliability * handover_factor * geometry_factor * mobility_factor,
                0.0,
            ), 1.0)
            step = (1 - cfg.ccra_beta) * evidence
            t = prev + step * (b - prev)
            self.trust[u["id"]] = t
            stale = _stale_factor(u, cfg)
            weights[u["id"]] = t * stale if t >= cfg.ccra_gate else 0.0

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
    if name == "median":
        return CoordinateMedian(cfg)
    if name == "trimmed_mean":
        return TrimmedMean(cfg)
    if name == "krum":
        return MultiKrum(cfg, single=True)
    if name == "multi_krum":
        return MultiKrum(cfg)
    if name == "fltrust":
        return FLTrust(cfg)
    if name == "ccra":
        return CCRA(cfg, use_context=True)
    if name == "ccra_noctx":  # ablation: CCRA without channel context
        return CCRA(cfg, use_context=False)
    raise ValueError(f"Unknown aggregator '{name}'")
