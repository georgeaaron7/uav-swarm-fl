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
    "speed_mps",
    "pitch_deg",
    "roll_deg",
    "sequence_id",
    "timestamp_ms",
)


class ChannelTrace:
    """A prepared trace whose rows remain tied to their source sample."""

    def __init__(self, path: str):
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
        self.sequence_indices = {
            int(sequence): np.flatnonzero(self.arrays["sequence_id"] == sequence)
            for sequence in np.unique(self.arrays["sequence_id"])
        }

    def rows(self, num_clients: int, rnd: int, seed: int) -> list[dict]:
        # Each simulated client replays one complete recorded flight sequence.
        # This avoids discontinuous jumps across sequence boundaries. Multiple
        # clients may reuse a sequence with deterministic phase offsets; they are
        # not represented as simultaneous real-world measurements.
        sequences = sorted(self.sequence_indices)
        indices = []
        for cid in range(num_clients):
            sequence = sequences[(seed + cid) % len(sequences)]
            candidates = self.sequence_indices[sequence]
            phase = (seed * 17 + cid * 31) % len(candidates)
            indices.append(int(candidates[(phase + rnd - 1) % len(candidates)]))
        return [
            {name: self.arrays[name][idx].item() for name in REQUIRED_FIELDS}
            | {"source_index": int(idx)}
            for idx in indices
        ]
