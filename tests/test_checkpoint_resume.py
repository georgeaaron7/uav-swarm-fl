import csv
import random

import numpy as np
import pytest
import torch
from torch import nn

from fl.checkpoint import (
    identity,
    latest_valid,
    load_checkpoint,
    restore_rng,
    save_checkpoint,
)
from fl.client import DroneClient
from fl.config import FLConfig
from fl.data import TensorImageDataset
from fl.server import FederatedServer
from fl.utils import set_seed


def make_server(aggregator, rounds=8):
    set_seed(41)
    torch.set_num_threads(1)
    cfg = FLConfig(
        data_dir="__swarm_test_dataset_not_on_disk__",
        name="recovery",
        rounds=rounds,
        seed=41,
        num_clients=4,
        client_fraction=0.75,
        local_epochs=1,
        batch_size=2,
        topology="hierarchical",
        num_base_stations=2,
        global_sync_every=3,
        aggregator=aggregator,
        channel="lossy",
        noise_scale=0.02,
        jammed_ids="1",
        tx_power_dbm=50,
        round_deadline_s=0,
        attack="label_flip",
        eval_batch_size=8,
    )
    generator = torch.Generator().manual_seed(6)
    data = TensorImageDataset(
        torch.randn(16, 3, 32, 32, generator=generator), torch.arange(16) % 10
    )
    clients = [
        DroneClient(i, data, np.arange(i * 4, (i + 1) * 4), cfg, torch.device("cpu"))
        for i in range(4)
    ]
    clients[1].make_malicious("label_flip")
    root = (
        DroneClient(-1, data, np.arange(4), cfg, torch.device("cpu"))
        if aggregator.startswith("ccra") or aggregator == "fltrust"
        else None
    )
    model = nn.Sequential(nn.Flatten(), nn.Linear(3072, 10))
    return FederatedServer(model, clients, data, cfg, torch.device("cpu"), root)


def equal(a, b):
    if isinstance(a, torch.Tensor):
        assert torch.equal(a, b)
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a:
            if key not in {"round_time_s", "elapsed_s"}:
                equal(a[key], b[key])
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            equal(x, y)
    else:
        assert a == b


@pytest.mark.parametrize(
    "aggregator",
    ["fedavg", "ccra", "median", "cosavg", "fltrust", "bp_fresh", "bp_reuse"],
)
def test_resume_preserves_scientific_trajectory(tmp_path, aggregator):
    rounds = 100 if aggregator in {"ccra", "bp_reuse"} else 8
    boundary = 40 if rounds == 100 else 4
    original = make_server(aggregator, rounds)
    a = tmp_path / "a"
    a.mkdir()
    original.run(str(a))
    interrupted = make_server(aggregator, rounds)
    b = tmp_path / "b"
    b.mkdir()

    class Stop(Exception):
        pass

    def checkpoint(server, record):
        if record["round"] == boundary:
            save_checkpoint(server, tmp_path / "checkpoints")
            raise Stop()

    with pytest.raises(Stop):
        interrupted.run(str(b), checkpoint)
    restored = make_server(aggregator, rounds)
    state, rng, _ = load_checkpoint(
        latest_valid(tmp_path / "checkpoints"), identity(restored.cfg)
    )
    restored.load_state_dict(state)
    restore_rng(rng)
    restored.run(str(b))
    equal(original.state_dict(), restored.state_dict())
    with (b / "metrics.csv").open() as f:
        assert [int(r["round"]) for r in csv.DictReader(f)] == list(
            range(1, rounds + 1)
        )
    equal(
        torch.load(a / "best_model.pt", weights_only=True),
        torch.load(b / "best_model.pt", weights_only=True),
    )


def test_integrity_identity_rng_and_fallback(tmp_path):
    server = make_server("fedavg")
    a = tmp_path / "run"
    a.mkdir()
    paths = []

    class Stop(Exception):
        pass

    def checkpoint(s, record):
        paths.append(save_checkpoint(s, tmp_path / "cp"))
        if record["round"] == 2:
            raise Stop()

    with pytest.raises(Stop):
        server.run(str(a), checkpoint)
    state, rng, meta = load_checkpoint(paths[-1], identity(server.cfg))
    restore_rng(rng)
    expected = (random.random(), np.random.rand(), torch.rand(2))
    restore_rng(rng)
    actual = (random.random(), np.random.rand(), torch.rand(2))
    equal(expected, actual)
    with pytest.raises(ValueError, match="identity"):
        load_checkpoint(paths[-1], {"dataset_sha256": "different"})
    with (paths[-1] / "state.pt").open("ab") as f:
        f.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        load_checkpoint(paths[-1])
    assert latest_valid(tmp_path / "cp") == paths[0]


def test_keep_prunes_old_checkpoints_but_keeps_newest(tmp_path):
    server = make_server("fedavg", rounds=4)
    run = tmp_path / "run"
    run.mkdir()
    server.run(str(run), lambda s, record: save_checkpoint(s, tmp_path / "cp", keep=2))
    kept = sorted(p.name for p in (tmp_path / "cp").glob("round_*"))
    assert kept == ["round_0003", "round_0004"]
    assert latest_valid(tmp_path / "cp", identity(server.cfg)).name == "round_0004"
