import torch

from fl.attacks import craft_model_updates
from fl.config import FLConfig


def records():
    return [
        {"id": 0, "delta": torch.tensor([1.0, 2.0])},
        {"id": 1, "delta": torch.tensor([2.0, 4.0])},
        {"id": 2, "delta": torch.tensor([3.0, 6.0])},
    ]


def test_sign_flip_only_changes_malicious_update():
    updates = records()
    cfg = FLConfig(attack_scale=2.0)
    craft_model_updates(updates, "sign_flip", {2}, cfg, rnd=1)
    assert torch.equal(updates[0]["delta"], torch.tensor([1.0, 2.0]))
    assert torch.equal(updates[2]["delta"], torch.tensor([-6.0, -12.0]))


def test_ipm_opposes_honest_mean():
    updates = records()
    cfg = FLConfig(ipm_epsilon=0.5)
    craft_model_updates(updates, "ipm", {2}, cfg, rnd=1)
    assert torch.allclose(updates[2]["delta"], torch.tensor([-0.75, -1.5]))


def test_gaussian_attack_is_deterministic():
    cfg = FLConfig(seed=7)
    first, second = records(), records()
    craft_model_updates(first, "gaussian", {2}, cfg, rnd=3)
    craft_model_updates(second, "gaussian", {2}, cfg, rnd=3)
    assert torch.equal(first[2]["delta"], second[2]["delta"])
