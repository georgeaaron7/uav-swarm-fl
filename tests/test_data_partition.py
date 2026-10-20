from types import SimpleNamespace

import numpy as np
import torch

from fl.data import TensorImageDataset, partition


def test_partition_uses_only_eligible_indices():
    dataset = TensorImageDataset(
        torch.zeros(40, 3, 32, 32),
        torch.tensor([0, 1] * 20),
    )
    reserved = np.array([0, 3, 8, 11])
    eligible = np.setdiff1d(np.arange(len(dataset)), reserved)
    cfg = SimpleNamespace(partition="iid", num_clients=4, seed=7)
    splits = partition(dataset, cfg, eligible_indices=eligible)
    assigned = np.concatenate(splits)
    assert set(assigned) == set(eligible)
    assert not set(assigned).intersection(reserved)
