"""Wireless uplink models for ideal, synthetic-lossy, and measured-trace runs."""
from __future__ import annotations

import math

import numpy as np
import torch

from .channel_traces import ChannelTrace


def parse_ids(s: str) -> list[int]:
    return [int(x) for x in s.split(",") if x.strip() != ""] if s else []


class WirelessChannel:
    """Produce BS-side link observations and transmit flattened model updates.

    ``lossy`` uses log-distance path loss, Rayleigh fading, jamming, and a
    logistic packet-error curve. ``trace`` anchors received power to recorded
    DeepSense samples, then adjusts it for each simulated BS by relative 3-D
    distance. The trace source index is retained in every telemetry record.
    """

    def __init__(self, cfg, num_clients: int, topology=None):
        self.cfg = cfg
        self.mode = cfg.channel
        self.n = num_clients
        self.topology = topology
        self.trace = (
            ChannelTrace(cfg.channel_trace_path, cfg.trace_min_sequence_length)
            if self.mode == "trace" else None
        )
        if (
            self.trace is not None
            and topology is not None
            and cfg.bs_radius_m <= 0
            and topology.num_base_stations > 1
        ):
            topology.set_base_station_radius(self.trace.virtual_bs_radius_m)
        self.jammed = set(parse_ids(cfg.jammed_ids))
        rng = np.random.default_rng(cfg.seed + 4321)
        self.jammer = None
        if self.jammed and topology is not None and self.mode != "trace":
            ids = [cid for cid in self.jammed if 0 <= cid < num_clients]
            if ids:
                self.jammer = topology.positions[ids].mean(axis=0) + rng.normal(0, 20, size=2)

    def _path_loss_db(self, distance_m: np.ndarray) -> np.ndarray:
        return 40.0 + 10.0 * self.cfg.pathloss_exp * np.log10(np.maximum(distance_m, 1.0))

    def _synthetic_signal(self, rnd: int) -> np.ndarray:
        topology = self.topology
        topology.move(rnd)
        distances = topology.distances()
        rng = np.random.default_rng(self.cfg.seed * 100_003 + rnd)
        fading_db = 10 * np.log10(rng.exponential(1.0, size=distances.shape) + 1e-12)
        return self.cfg.tx_power_dbm - self._path_loss_db(distances) + fading_db

    def _trace_signal(self, rnd: int) -> tuple[np.ndarray, list[dict]]:
        rows = self.trace.rows(self.n, rnd, self.cfg.seed, self.cfg.trace_stride)
        xy = np.array([[r["x_m"], r["y_m"]] for r in rows], dtype=float)
        altitude = np.array([max(0.0, float(r["height_m"])) for r in rows])
        self.topology.set_trace_positions(xy, altitude)
        distances = self.topology.distances()
        # BS 0 is the physical measurement site. Using its geometry as the
        # reference leaves that measured link unchanged; only virtual BS links
        # receive a relative path-loss adjustment.
        reference_distance = distances[:, [0]]
        measured_relative_db = np.array([
            float(r["rx_power_db"]) - self.trace.power_reference_db for r in rows
        ], dtype=float)[:, None]
        reference_snr_db = (
            self.cfg.trace_snr_reference_db
            + self.cfg.trace_snr_spread_scale * measured_relative_db
        )
        relative_loss = 10.0 * self.cfg.pathloss_exp * np.log10(
            np.maximum(distances, 1.0) / reference_distance
        )
        # DeepSense power values are uncalibrated linear measurements. Only
        # their relative dB variation is measured; the absolute SNR anchor is
        # an explicit experiment assumption.
        signal_dbm = self.cfg.noise_dbm + reference_snr_db - relative_loss
        return signal_dbm, rows

    def link_state(self, rnd: int) -> list[dict]:
        topology = self.topology
        if topology is None:
            raise RuntimeError("WirelessChannel requires a SwarmTopology")

        trace_rows = None
        if self.mode == "trace":
            signal_dbm, trace_rows = self._trace_signal(rnd)
            if self.jammed and self.jammer is None:
                affected = [cid for cid in self.jammed if 0 <= cid < self.n]
                if affected:
                    rng = np.random.default_rng(self.cfg.seed + 4321)
                    self.jammer = (
                        topology.positions[affected].mean(axis=0)
                        + rng.normal(0, 20, size=2)
                    )
        else:
            signal_dbm = self._synthetic_signal(rnd)

        handovers = topology.update_associations(signal_dbm)
        serving = topology.serving
        chosen_signal = signal_dbm[np.arange(self.n), serving]

        noise_mw = 10 ** (self.cfg.noise_dbm / 10)
        jam_mw = np.zeros(self.n)
        if self.jammer is not None:
            horizontal = np.linalg.norm(topology.positions - self.jammer, axis=1)
            distance = np.sqrt(horizontal**2 + topology.altitudes**2)
            interference = 10 ** ((self.cfg.jammer_power_dbm - self._path_loss_db(distance)) / 10)
            affected = [cid for cid in self.jammed if 0 <= cid < self.n]
            jam_mw[affected] = interference[affected]

        if self.mode == "ideal":
            sinr_db = np.full(self.n, np.inf)
            per = np.zeros(self.n)
            rate_bps = np.full(self.n, np.inf)
        else:
            sinr_db = chosen_signal - 10 * np.log10(noise_mw + jam_mw)
            exponent = np.clip(self.cfg.per_slope * (sinr_db - self.cfg.per_threshold_db), -60, 60)
            per = 1.0 / (1.0 + np.exp(exponent))
            snr_linear = np.power(10.0, np.clip(sinr_db, -100, 100) / 10.0)
            rate_bps = self.cfg.bandwidth_hz * np.log2(1.0 + snr_linear)

        states = []
        for cid in range(self.n):
            ctx = topology.client_context(cid, handovers)
            state = {
                "sinr_db": float(sinr_db[cid]),
                "per": float(per[cid]),
                "rate_bps": float(rate_bps[cid]),
                "rx_power_dbm": float(chosen_signal[cid]),
                "jam_dbm": float(10 * np.log10(jam_mw[cid] + 1e-30)),
                **ctx,
            }
            if trace_rows is not None:
                row = trace_rows[cid]
                state.update({
                    "trace_source_index": row["source_index"],
                    "trace_sequence_id": int(row["sequence_id"]),
                    "trace_timestamp_ms": float(row["timestamp_ms"]),
                    "trace_power_db_arbitrary": float(row["rx_power_db"]),
                    "trace_power_rel_db": float(
                        row["rx_power_db"] - self.trace.power_reference_db
                    ),
                    "trace_snr_reference_db": float(self.cfg.trace_snr_reference_db),
                    "trace_speed": float(row["speed"]),
                    "trace_speed_normalized": float(row["speed"] / self.trace.speed_reference),
                    "pitch_deg": float(row["pitch_deg"]),
                    "roll_deg": float(row["roll_deg"]),
                })
            states.append(state)
        return states

    def transmit(self, delta: torch.Tensor, link: dict, rnd: int, client_id: int):
        cfg = self.cfg
        model_bits = delta.numel() * cfg.bits_per_parameter
        rate_bps = link["rate_bps"]
        latency_s = 0.0 if math.isinf(rate_bps) else model_bits / max(rate_bps, 1e-12)
        staleness = (
            0 if cfg.round_deadline_s <= 0
            else max(0, math.ceil(latency_s / cfg.round_deadline_s) - 1)
        )
        deadline_missed = cfg.round_deadline_s > 0 and latency_s > cfg.round_deadline_s

        if self.mode == "ideal":
            mask = torch.ones_like(delta, dtype=torch.bool)
            tel = dict(link) | {
                "pdr": 1.0,
                "model_bits": int(model_bits),
                "latency_s": latency_s,
                "staleness": staleness,
                "deadline_missed": deadline_missed,
                "drop_reason": None,
            }
            return delta.clone(), mask, tel

        generator = torch.Generator().manual_seed(cfg.seed * 7_919 + rnd * 1_009 + client_id)
        n_params = delta.numel()
        n_packets = (n_params + cfg.packet_size - 1) // cfg.packet_size
        packet_ok = torch.rand(n_packets, generator=generator) >= link["per"]
        drop_reason = None
        if deadline_missed and cfg.stale_policy == "drop":
            packet_ok[:] = False
            drop_reason = "deadline"
        mask = packet_ok.repeat_interleave(cfg.packet_size)[:n_params]

        received = delta.clone()
        if cfg.noise_scale > 0 and math.isfinite(link["sinr_db"]):
            sigma = cfg.noise_scale * delta.std() * 10 ** (-link["sinr_db"] / 20)
            received += sigma * torch.randn(n_params, generator=generator)
        received[~mask] = 0.0
        tel = dict(link) | {
            "pdr": float(packet_ok.float().mean()),
            "model_bits": int(model_bits),
            "latency_s": float(latency_s),
            "staleness": int(staleness),
            "deadline_missed": bool(deadline_missed),
            "drop_reason": drop_reason,
        }
        return received, mask, tel
