from types import SimpleNamespace

import pytest
import torch

from fl.server import FedAvg, build_aggregator


def make_update(client_id, delta, num_samples):
    """Update as received by the aggregator after the wireless channel."""
    delta = torch.tensor(delta)
    return {
        "id": client_id,
        "delta": delta,
        "mask": torch.ones_like(delta, dtype=torch.bool),
        "n": num_samples,
        "tel": {"sinr_db": float("inf"), "per": 0.0, "pdr": 1.0},
    }


def test_fedavg_computes_sample_weighted_average():
    cfg = SimpleNamespace(aggregator="fedavg")
    aggregator = FedAvg(cfg)

    update_1 = make_update(client_id=0, delta=[1.0, 2.0], num_samples=1)
    update_2 = make_update(client_id=1, delta=[3.0, 4.0], num_samples=3)

    new_delta, info = aggregator.aggregate([update_1, update_2])

    # Weighted average:
    # (1/4) * [1, 2] + (3/4) * [3, 4] = [2.5, 3.5]
    assert torch.allclose(new_delta, torch.tensor([2.5, 3.5]))

    assert info["weights"] == {
        0: pytest.approx(0.25),
        1: pytest.approx(0.75),
    }


def test_build_aggregator_passes_configuration():
    cfg = SimpleNamespace(aggregator="fedavg")

    aggregator = build_aggregator("fedavg", cfg)

    assert isinstance(aggregator, FedAvg)
    assert aggregator.cfg is cfg


def test_build_aggregator_rejects_unknown_name():
    cfg = SimpleNamespace(aggregator="unknown")

    with pytest.raises(ValueError, match="Unknown aggregator"):
        build_aggregator("unknown", cfg)
