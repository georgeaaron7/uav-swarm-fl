import pytest
import torch

from fl.aggregators import build_aggregator
from fl.config import FLConfig


def update(client_id, values, mask=None):
    delta = torch.tensor(values, dtype=torch.float32)
    return {
        "id": client_id,
        "delta": delta,
        "mask": torch.ones_like(delta, dtype=torch.bool) if mask is None else torch.tensor(mask),
        "n": 1,
        "staleness": 0,
        "tel": {"sinr_db": 20.0, "pdr": 1.0},
        "ctx": {},
    }


def test_coordinate_median_rejects_large_outlier():
    aggregator = build_aggregator("median", FLConfig())
    result, _ = aggregator.aggregate([
        update(0, [1.0, 1.0]), update(1, [1.1, 0.9]), update(2, [100.0, -100.0])
    ])
    assert torch.allclose(result, torch.tensor([1.1, 0.9]))


def test_trimmed_mean_rejects_extremes():
    aggregator = build_aggregator("trimmed_mean", FLConfig(trim_ratio=0.2))
    result, _ = aggregator.aggregate([
        update(0, [-100.0]), update(1, [1.0]), update(2, [2.0]),
        update(3, [3.0]), update(4, [100.0]),
    ])
    assert result.item() == pytest.approx(2.0)


def test_krum_selects_cluster_member():
    aggregator = build_aggregator("krum", FLConfig(krum_byzantine=1))
    _, info = aggregator.aggregate([
        update(0, [0.0, 0.0]), update(1, [0.1, 0.0]),
        update(2, [0.0, 0.1]), update(3, [20.0, 20.0]),
    ])
    assert info["selected"][0] in {0, 1, 2}
    assert info["weights"][3] == 0.0


def test_fltrust_needs_and_uses_root_update():
    aggregator = build_aggregator("fltrust", FLConfig())
    updates = [update(0, [1.0, 0.0]), update(1, [-1.0, 0.0])]
    with pytest.raises(ValueError):
        aggregator.aggregate(updates)
    result, info = aggregator.aggregate(updates, root=torch.tensor([1.0, 0.0]))
    assert torch.allclose(result, torch.tensor([1.0, 0.0]))
    assert info["weights"][1] == 0.0
