"""A drone (worker node) in the federation."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import torch
import torch.nn as nn

from .data import TensorImageDataset, augment_batch


@dataclass
class ClientUpdate:
    """What a drone transmits to the aggregator after local training."""
    client_id: int
    state_dict: dict
    num_samples: int
    metrics: dict = field(default_factory=dict)


class DroneClient:
    def __init__(self, client_id: int, dataset: TensorImageDataset, indices: np.ndarray, cfg,
                 device: torch.device):
        self.client_id = client_id
        self.cfg = cfg
        self.device = device
        # Local copy of this drone's data (Month 2 will poison self.y on malicious drones).
        self.x = dataset.images[indices]
        self.y = dataset.targets[indices].clone()
        # Hooks for later phases -------------------------------------------
        self.is_malicious = False          # Month 2: Byzantine / label-flipping
        self.position = None               # Month 3: simulated (x, y, z) coordinates
        self.link_telemetry: dict = {}     # Month 3: SNR / packet-loss from the network sim

    def make_malicious(self, attack: str, num_classes: int = 10) -> None:
        """Byzantine drone. label_flip: every label c becomes (C-1-c), e.g. airplane<->truck."""
        self.is_malicious = True
        if attack == "label_flip":
            self.y = (num_classes - 1) - self.y
        else:
            raise ValueError(f"Unknown attack '{attack}'")

    @property
    def num_samples(self) -> int:
        return len(self.y)

    def label_histogram(self, num_classes: int = 10) -> list[int]:
        return torch.bincount(self.y, minlength=num_classes).tolist()

    def local_train(self, global_model: nn.Module) -> ClientUpdate:
        cfg = self.cfg
        model = copy.deepcopy(global_model).to(self.device)
        model.train()
        opt = torch.optim.SGD(model.parameters(), lr=cfg.lr, momentum=cfg.momentum,
                              weight_decay=cfg.weight_decay)
        loss_fn = nn.CrossEntropyLoss()

        x_all, y_all = self.x.to(self.device), self.y.to(self.device)
        n = len(y_all)
        total_loss, total_correct, total_seen = 0.0, 0, 0
        for _ in range(cfg.local_epochs):
            perm = torch.randperm(n, device=self.device)
            for s in range(0, n, cfg.batch_size):
                idx = perm[s:s + cfg.batch_size]
                xb, yb = augment_batch(x_all[idx]), y_all[idx]
                opt.zero_grad(set_to_none=True)
                out = model(xb)
                loss = loss_fn(out, yb)
                loss.backward()
                opt.step()
                total_loss += loss.item() * len(yb)
                total_correct += (out.argmax(1) == yb).sum().item()
                total_seen += len(yb)

        state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
        return ClientUpdate(
            client_id=self.client_id,
            state_dict=state,
            num_samples=n,
            metrics={"train_loss": total_loss / total_seen, "train_acc": total_correct / total_seen},
        )
