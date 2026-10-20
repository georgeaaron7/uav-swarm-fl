"""Swarm geometry, base-station association, and cellular handover."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HandoverEvent:
    client_id: int
    old_bs: int
    new_bs: int


class SwarmTopology:
    """Owns UAV positions and serving-cell state.

    Association is driven by the received-power matrix supplied by the channel.
    A candidate cell must beat the serving cell by ``handover_hysteresis_db``
    for ``handover_ttt`` consecutive rounds before the handover is committed.
    """

    def __init__(self, cfg, num_clients: int):
        self.cfg = cfg
        self.num_clients = num_clients
        self.num_base_stations = 1 if cfg.topology == "centralized" else cfg.num_base_stations
        if self.num_base_stations < 1:
            raise ValueError("num_base_stations must be at least 1")
        if cfg.handover_ttt < 1:
            raise ValueError("handover_ttt must be at least 1")

        rng = np.random.default_rng(cfg.seed + 1234)
        half = cfg.area_m / 2
        self.positions = rng.uniform(-half, half, size=(num_clients, 2))
        self.altitudes = np.full(num_clients, cfg.drone_alt_m, dtype=float)
        radius = cfg.bs_radius_m
        if radius <= 0:
            # A trace-driven layout is replaced after the trace is loaded.
            radius = cfg.area_m * 0.30
        self.base_stations = self._make_bs_layout(self.num_base_stations, radius)
        self.serving = np.full(num_clients, -1, dtype=int)
        self.pending = np.full(num_clients, -1, dtype=int)
        self.pending_rounds = np.zeros(num_clients, dtype=int)
        self.handover_counts = np.zeros(num_clients, dtype=int)

    @staticmethod
    def _make_bs_layout(n: int, radius: float) -> np.ndarray:
        # BS 0 is the measured/reference site for trace-driven experiments.
        if n == 1:
            return np.zeros((1, 2), dtype=float)
        angles = np.linspace(0, 2 * np.pi, n - 1, endpoint=False)
        ring = np.column_stack((radius * np.cos(angles), radius * np.sin(angles)))
        return np.vstack((np.zeros((1, 2)), ring))

    def move(self, rnd: int) -> None:
        rng = np.random.default_rng(self.cfg.seed * 100_003 + rnd)
        half = self.cfg.area_m / 2
        step = rng.normal(0, self.cfg.mobility_m, size=self.positions.shape)
        self.positions = np.clip(self.positions + step, -half, half)

    def set_trace_positions(self, xy_m: np.ndarray, altitude_m: np.ndarray) -> None:
        if xy_m.shape != self.positions.shape:
            raise ValueError(f"trace positions must have shape {self.positions.shape}")
        self.positions = np.asarray(xy_m, dtype=float)
        self.altitudes = np.asarray(altitude_m, dtype=float)

    def set_base_station_radius(self, radius_m: float) -> None:
        if radius_m <= 0:
            raise ValueError("base-station radius must be positive")
        self.base_stations = self._make_bs_layout(self.num_base_stations, radius_m)

    def distances(self) -> np.ndarray:
        horizontal = np.linalg.norm(
            self.positions[:, None, :] - self.base_stations[None, :, :], axis=2
        )
        vertical = self.altitudes[:, None] - self.cfg.bs_height_m
        return np.sqrt(horizontal**2 + vertical**2)

    def update_associations(self, signal_dbm: np.ndarray) -> list[HandoverEvent]:
        if signal_dbm.shape != (self.num_clients, self.num_base_stations):
            raise ValueError("signal matrix does not match topology dimensions")
        best = signal_dbm.argmax(axis=1)
        events: list[HandoverEvent] = []
        for cid in range(self.num_clients):
            if self.serving[cid] < 0:
                self.serving[cid] = int(best[cid])
                continue
            current = self.serving[cid]
            candidate = int(best[cid])
            improvement = signal_dbm[cid, candidate] - signal_dbm[cid, current]
            if candidate != current and improvement >= self.cfg.handover_hysteresis_db:
                if self.pending[cid] == candidate:
                    self.pending_rounds[cid] += 1
                else:
                    self.pending[cid] = candidate
                    self.pending_rounds[cid] = 1
                if self.pending_rounds[cid] >= self.cfg.handover_ttt:
                    self.serving[cid] = candidate
                    self.handover_counts[cid] += 1
                    events.append(HandoverEvent(cid, int(current), candidate))
                    self.pending[cid] = -1
                    self.pending_rounds[cid] = 0
            else:
                self.pending[cid] = -1
                self.pending_rounds[cid] = 0
        return events

    def client_context(self, client_id: int, handovers: list[HandoverEvent]) -> dict:
        serving_bs = int(self.serving[client_id])
        return {
            "serving_bs": serving_bs,
            "handover": any(e.client_id == client_id for e in handovers),
            "handover_count": int(self.handover_counts[client_id]),
            "distance_m": float(self.distances()[client_id, serving_bs]),
            "altitude_m": float(self.altitudes[client_id]),
        }
