"""A drone (worker node) in the federation."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import torch
import torch.nn as nn

from .data import TensorImageDataset, augment_batch
from .attacks import validate_attack


@dataclass
class ClientUpdate:
    """Information transmitted by a drone after local training.

    `oracle_is_malicious` is only for experiment evaluation. Aggregators must
    never use it when deciding whether an update is malicious.
    """

    client_id: int
    state_dict: dict[str, torch.Tensor]
    delta: dict[str, torch.Tensor]
    num_samples: int

    link_telemetry: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    staleness: int = 0
    oracle_is_malicious: bool = False
    metrics: dict = field(default_factory=dict)


class DroneClient:
    def __init__(
        self,
        client_id: int,
        dataset: TensorImageDataset,
        indices: np.ndarray,
        cfg,
        device: torch.device,
    ):
        self.client_id = client_id
        self.cfg = cfg
        self.device = device

        # Local copy of this drone's data. Future attacks may alter self.y
        # without changing the shared global dataset.
        self.x = dataset.images[indices]
        self.y = dataset.targets[indices].clone()

        # Hooks for later phases.
        self.is_malicious = False
        self.attack = "none"
        self.position = None
        self.link_telemetry: dict = {}
        self.context: dict = {}
        self.staleness: int = 0

    def make_malicious(self, attack: str, num_classes: int = 10) -> None:
        """Mark this drone malicious and apply any data-poisoning transform."""
        validate_attack(attack)
        if attack == "none":
            return
        self.is_malicious = True
        self.attack = attack
        if attack == "label_flip":
            self.y = (num_classes - 1) - self.y

    @property
    def num_samples(self) -> int:
        return len(self.y)

    def label_histogram(self, num_classes: int = 10) -> list[int]:
        return torch.bincount(
            self.y,
            minlength=num_classes,
        ).tolist()

    def local_train(self, global_model: nn.Module) -> ClientUpdate:
        cfg = self.cfg

        # Preserve the exact model state received from the server. The update
        # delta will be calculated relative to this state.
        global_state = {
            key: value.detach().cpu().clone()
            for key, value in global_model.state_dict().items()
        }

        model = copy.deepcopy(global_model).to(self.device)
        model.train()

        opt = torch.optim.SGD(
            model.parameters(),
            lr=cfg.lr,
            momentum=cfg.momentum,
            weight_decay=cfg.weight_decay,
        )
        loss_fn = nn.CrossEntropyLoss()

        x_all = self.x.to(self.device)
        y_all = self.y.to(self.device)
        n = len(y_all)

        total_loss = 0.0
        total_correct = 0
        total_seen = 0

        for _ in range(cfg.local_epochs):
            perm = torch.randperm(n, device=self.device)

            for start in range(0, n, cfg.batch_size):
                idx = perm[start:start + cfg.batch_size]
                xb = augment_batch(x_all[idx])
                yb = y_all[idx]

                opt.zero_grad(set_to_none=True)

                output = model(xb)
                loss = loss_fn(output, yb)

                loss.backward()
                opt.step()

                total_loss += loss.item() * len(yb)
                total_correct += (output.argmax(1) == yb).sum().item()
                total_seen += len(yb)

        local_state = {
            key: value.detach().cpu().clone()
            for key, value in model.state_dict().items()
        }

        # Integer buffers do not represent trainable model updates, so only
        # floating-point entries are included in the delta.
        delta = {
            key: local_state[key] - global_state[key]
            for key in local_state
            if torch.is_floating_point(local_state[key])
        }

        return ClientUpdate(
            client_id=self.client_id,
            state_dict=local_state,
            delta=delta,
            num_samples=n,
            link_telemetry=dict(self.link_telemetry),
            context=dict(self.context),
            staleness=self.staleness,
            oracle_is_malicious=self.is_malicious,
            metrics={
                "train_loss": total_loss / total_seen,
                "train_acc": total_correct / total_seen,
            },
        )
