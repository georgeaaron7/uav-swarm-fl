from pathlib import Path

import numpy as np
import pytest
import torch

from fl.channel import WirelessChannel
from fl.config import FLConfig
from fl.topology import SwarmTopology


def test_handover_requires_hysteresis_and_time_to_trigger():
    cfg = FLConfig(
        topology="hierarchical", num_clients=1, num_base_stations=2,
        handover_hysteresis_db=3.0, handover_ttt=2,
    )
    topology = SwarmTopology(cfg, 1)
    topology.update_associations(np.array([[0.0, -10.0]]))
    assert topology.serving.tolist() == [0]

    assert topology.update_associations(np.array([[0.0, 4.0]])) == []
    events = topology.update_associations(np.array([[0.0, 4.0]]))
    assert topology.serving.tolist() == [1]
    assert [(e.client_id, e.old_bs, e.new_bs) for e in events] == [(0, 0, 1)]


def make_trace(path: Path):
    size = 6
    np.savez_compressed(
        path,
        rx_power_db=np.full(size, -60.0),
        x_m=np.linspace(0, 10, size),
        y_m=np.zeros(size),
        distance_m=np.linspace(10, 20, size),
        height_m=np.full(size, 10.0),
        speed_mps=np.ones(size),
        pitch_deg=np.zeros(size),
        roll_deg=np.zeros(size),
        sequence_id=np.ones(size, dtype=int),
        timestamp_ms=np.arange(size) * 100.0,
        metadata_json=np.array("{}"),
    )


def test_trace_channel_preserves_source_and_computes_latency(tmp_path):
    trace = tmp_path / "trace.npz"
    make_trace(trace)
    cfg = FLConfig(
        topology="centralized", num_clients=2, channel="trace",
        channel_trace_path=str(trace), noise_dbm=-90.0, bandwidth_hz=1e6,
        round_deadline_s=10.0, noise_scale=0.0,
    )
    topology = SwarmTopology(cfg, 2)
    channel = WirelessChannel(cfg, 2, topology)
    links = channel.link_state(1)
    assert all("trace_source_index" in link for link in links)
    assert links[0]["serving_bs"] == 0

    delta = torch.ones(100)
    received, mask, telemetry = channel.transmit(delta, links[0], 1, 0)
    assert received.shape == delta.shape
    assert mask.dtype == torch.bool
    assert telemetry["latency_s"] > 0
    assert 0 <= telemetry["pdr"] <= 1


def test_trace_channel_requires_existing_file(tmp_path):
    cfg = FLConfig(channel="trace", channel_trace_path=str(tmp_path / "missing.npz"))
    topology = SwarmTopology(cfg, cfg.num_clients)
    with pytest.raises(FileNotFoundError):
        WirelessChannel(cfg, cfg.num_clients, topology)
