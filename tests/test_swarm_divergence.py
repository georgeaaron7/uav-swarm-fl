"""Exercise the simulator's actual nonfinite check and existing terminal schema."""

import json

import torch
from torch import nn

import run_baseline
from fl.aggregators import FedAvg
from fl.data import TensorImageDataset
from run_context_study import completed


def test_detected_numerical_divergence_keeps_finite_previous_state(
    tmp_path, monkeypatch
):
    generator = torch.Generator().manual_seed(5)
    dataset = TensorImageDataset(
        torch.randn(80, 3, 32, 32, generator=generator), torch.arange(80) % 10
    )
    monkeypatch.setattr(
        run_baseline, "load_dataset", lambda *args: (dataset, dataset, 10)
    )
    monkeypatch.setattr(
        run_baseline,
        "build_model",
        lambda *args: nn.Sequential(nn.Flatten(), nn.Linear(3072, 10)),
    )

    class DivergingAggregator(FedAvg):
        calls = 0

        def aggregate(self, updates):
            self.calls += 1
            delta, info = super().aggregate(updates)
            if self.calls == 2:
                delta[:] = float("nan")
            return delta, info

    monkeypatch.setattr(
        "fl.server.build_aggregator", lambda name, cfg: DivergingAggregator(cfg)
    )
    summary = run_baseline.main(
        [
            "--rounds",
            "4",
            "--num-clients",
            "2",
            "--local-epochs",
            "1",
            "--batch-size",
            "8",
            "--root-samples-per-class",
            "1",
            "--threads",
            "1",
            "--device",
            "cpu",
            "--name",
            "divergence-test",
            "--out-dir",
            str(tmp_path),
            "--data-dir",
            str(tmp_path / "not-on-disk"),
        ]
    )
    assert summary["diverged"] and summary["divergence_round"] == 2
    assert summary["completed_rounds"] == 1 and summary["final_test_acc"] is None
    directory = tmp_path / "divergence-test"
    cfg = json.loads((directory / "config.json").read_text())
    assert completed({"seed": cfg["seed"], "config": cfg})
    weights = torch.load(directory / "final_model.pt", weights_only=True)
    assert all(torch.isfinite(value).all() for value in weights.values())
