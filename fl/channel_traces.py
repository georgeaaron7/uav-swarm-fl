"""Loader for compact, provenance-preserving UAV wireless traces."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


REQUIRED_FIELDS = (
    "rx_power_db",
    "x_m",
    "y_m",
    "distance_m",
    "height_m",
    "speed",
    "pitch_deg",
    "roll_deg",
    "sequence_id",
    "timestamp_ms",
)


class ChannelTrace:
    """A prepared trace whose rows remain tied to their source sample."""

    def __init__(self, path: str, min_sequence_length: int = 1):
        if not path:
            raise ValueError("channel_trace_path is required when channel=trace")
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"channel trace not found: {self.path}")
        data = np.load(self.path, allow_pickle=False)
        missing = [name for name in REQUIRED_FIELDS if name not in data]
        if missing:
            raise ValueError(f"channel trace is missing fields: {', '.join(missing)}")
        self.arrays = {name: np.asarray(data[name]) for name in REQUIRED_FIELDS}
        sizes = {len(v) for v in self.arrays.values()}
        if len(sizes) != 1 or next(iter(sizes)) == 0:
            raise ValueError("channel trace fields must have the same non-zero length")
        self.size = next(iter(sizes))
        raw_meta = str(data["metadata_json"].item()) if "metadata_json" in data else "{}"
        self.metadata = json.loads(raw_meta)
        self.power_reference_db = float(np.median(self.arrays["rx_power_db"]))
        horizontal_range = np.hypot(self.arrays["x_m"], self.arrays["y_m"])
        # Put virtual-cell boundaries inside, rather than outside, the measured
        # flight footprint. With the reference BS at the origin and a virtual
        # BS at this radius, the nearest-cell boundary lies at half the radius.
        self.virtual_bs_radius_m = max(float(np.quantile(horizontal_range, 0.95)) / 2.0, 1.0)
        all_sequences = {
            int(sequence): np.flatnonzero(self.arrays["sequence_id"] == sequence)
            for sequence in np.unique(self.arrays["sequence_id"])
        }
        self.sequence_indices = {
            sequence: indices for sequence, indices in all_sequences.items()
            if len(indices) >= min_sequence_length
        }
        if not self.sequence_indices:
            raise ValueError(
                f"no trace sequences contain at least {min_sequence_length} samples"
            )
        self.speed_reference = max(float(np.quantile(self.arrays["speed"], 0.95)), 1e-12)

    def rows(self, num_clients: int, rnd: int, seed: int, stride: int = 1) -> list[dict]:
        if stride < 1:
            raise ValueError("trace_stride must be at least 1")
        # Each simulated client replays one complete recorded flight sequence.
        # This avoids discontinuous jumps across sequence boundaries. Multiple
        # clients may reuse a sequence with deterministic phase offsets; they are
        # not represented as simultaneous real-world measurements. At an endpoint
        # the replay reverses direction, avoiding a non-physical teleport from the
        # last sample back to the first.
        sequences = sorted(self.sequence_indices)
        indices = []
        for cid in range(num_clients):
            sequence = sequences[(seed + cid) % len(sequences)]
            candidates = self.sequence_indices[sequence]
            phase = (seed * 17 + cid * 31) % len(candidates)
            if len(candidates) == 1:
                position = 0
            else:
                period = 2 * (len(candidates) - 1)
                position = (phase + (rnd - 1) * stride) % period
                if position >= len(candidates):
                    position = period - position
            indices.append(int(candidates[position]))
        return [
            {name: self.arrays[name][idx].item() for name in REQUIRED_FIELDS}
            | {"source_index": int(idx)}
            for idx in indices
        ]
