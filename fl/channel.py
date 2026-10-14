"""Lossy wireless channel between drones and the aggregator (Python stand-in for NS-3).

Model (per round, per drone k)
------------------------------
* Geometry: drones fly at `drone_alt` m over a square area, doing a bounded
  random walk each round. The aggregator (swarm leader / ground node) is at the centre.
* Path loss (log-distance, air-to-ground LoS-ish):
      PL(d) = PL0 + 10 * n * log10(d)        [dB], PL0 = 40 dB @ 1 m (2.4 GHz)
* Small-scale fading: Rayleigh block fading, |h|^2 ~ Exp(1), new each round.
* EW jamming: a ground jammer of power P_J placed over the targeted sector.
  The interference it puts on drone k's link is P_J - PL(dist(jammer, drone k)).
  (A link with ARQ/ACKs breaks if either endpoint is jammed.)
* SINR_k = S_k / (N0 + J_k)
* Packet error rate: logistic PER(SINR) curve (the shape of NS-3's
  table-based error models): PER = 1 / (1 + exp(slope * (SINR_dB - thr_dB)))
* The model update is split into packets of `packet_size` parameters. Each packet
  is lost independently with probability PER (CRC detects the loss).
* Received packets carry residual noise (soft errors that pass CRC / analog
  over-the-air aggregation):
      sigma_k = noise_scale * std(update_k) * 10^(-SINR_dB / 20)
  so a drone in a bad channel delivers a *noisy but honest* update.
  This is the "legitimate noise" that a robust aggregator must not reject.

transmit() returns the update as received at the aggregator (lost entries = 0),
a boolean mask of delivered parameters, and the telemetry (SINR, PER, PDR).
"""
from __future__ import annotations

import numpy as np
import torch


def parse_ids(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip() != ""] if s else []


class WirelessChannel:
    def __init__(self, cfg, num_clients: int):
        self.cfg = cfg
        self.mode = cfg.channel
        self.n = num_clients
        rng = np.random.default_rng(cfg.seed + 1234)
        half = cfg.area_m / 2
        self.pos = rng.uniform(-half, half, size=(num_clients, 2))
        self.rx = np.zeros(2)
        jammed = parse_ids(cfg.jammed_ids)
        if jammed:
            # jammer sits over the sector the targeted drones are patrolling
            self.jammer = self.pos[jammed].mean(axis=0) + rng.normal(0, 20, size=2)
        else:
            self.jammer = None

    # ------------------------------------------------------------------
    def _path_loss_db(self, d2d: np.ndarray, dz: float) -> np.ndarray:
        d = np.sqrt(d2d ** 2 + dz ** 2)
        return 40.0 + 10.0 * self.cfg.pathloss_exp * np.log10(np.maximum(d, 1.0))

    def link_state(self, rnd: int) -> list[dict]:
        """Per-drone link telemetry for this round (deterministic in seed + round)."""
        cfg = self.cfg
        rng = np.random.default_rng(cfg.seed * 100_003 + rnd)
        half = cfg.area_m / 2
        # bounded random-walk mobility
        self.pos = np.clip(self.pos + rng.normal(0, cfg.mobility_m, size=self.pos.shape), -half, half)

        d_rx = np.linalg.norm(self.pos - self.rx, axis=1)
        fading_db = 10 * np.log10(rng.exponential(1.0, size=self.n) + 1e-12)
        sig_dbm = cfg.tx_power_dbm - self._path_loss_db(d_rx, cfg.drone_alt_m) + fading_db

        noise_mw = 10 ** (cfg.noise_dbm / 10)
        if self.jammer is not None:
            d_j = np.linalg.norm(self.pos - self.jammer, axis=1)
            jam_mw = 10 ** ((cfg.jammer_power_dbm - self._path_loss_db(d_j, cfg.drone_alt_m)) / 10)
        else:
            jam_mw = np.zeros(self.n)
        sinr_db = sig_dbm - 10 * np.log10(noise_mw + jam_mw)
        per = 1.0 / (1.0 + np.exp(cfg.per_slope * (sinr_db - cfg.per_threshold_db)))
        return [{"sinr_db": float(sinr_db[k]), "per": float(per[k]),
                 "dist_m": float(d_rx[k]), "jam_dbm": float(10 * np.log10(jam_mw[k] + 1e-30))}
                for k in range(self.n)]

    # ------------------------------------------------------------------
    def transmit(self, delta: torch.Tensor, link: dict, rnd: int, client_id: int):
        """Send a flat update vector over the link. Returns (received, mask, telemetry)."""
        if self.mode == "ideal":
            mask = torch.ones_like(delta, dtype=torch.bool)
            return delta.clone(), mask, {"sinr_db": float("inf"), "per": 0.0, "pdr": 1.0}

        cfg = self.cfg
        g = torch.Generator().manual_seed(cfg.seed * 7_919 + rnd * 1_009 + client_id)
        n_params = delta.numel()
        n_pkts = (n_params + cfg.packet_size - 1) // cfg.packet_size
        pkt_ok = torch.rand(n_pkts, generator=g) >= link["per"]
        mask = pkt_ok.repeat_interleave(cfg.packet_size)[:n_params]

        received = delta.clone()
        if cfg.noise_scale > 0:
            sigma = cfg.noise_scale * delta.std() * 10 ** (-link["sinr_db"] / 20)
            received += sigma * torch.randn(n_params, generator=g)
        received[~mask] = 0.0
        tel = dict(link)
        tel["pdr"] = float(pkt_ok.float().mean())
        return received, mask, tel
