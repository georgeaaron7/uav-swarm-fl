import numpy as np
import torch
import torch.nn as nn

from fl.client import DroneClient
from fl.config import FLConfig
from fl.data import TensorImageDataset
from fl.server import FederatedServer


class TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.classifier = nn.Sequential(nn.Flatten(), nn.Linear(3 * 32 * 32, 2))

    def forward(self, images):
        return self.classifier(images)


def test_hierarchical_server_runs_and_records_context(tmp_path):
    generator = torch.Generator().manual_seed(3)
    dataset = TensorImageDataset(
        torch.randn(16, 3, 32, 32, generator=generator),
        torch.tensor([0, 1] * 8),
    )
    cfg = FLConfig(
        name="tiny", num_clients=4, rounds=2, local_epochs=1, batch_size=2,
        lr=0.01, momentum=0.0, weight_decay=0.0, topology="hierarchical",
        num_base_stations=2, global_sync_every=1, channel="ideal",
        aggregator="median", attack="sign_flip", malicious_ids="0",
        eval_batch_size=4,
    )
    clients = [
        DroneClient(cid, dataset, np.arange(cid * 4, (cid + 1) * 4), cfg, torch.device("cpu"))
        for cid in range(4)
    ]
    clients[0].make_malicious("sign_flip", num_classes=2)
    server = FederatedServer(TinyModel(), clients, dataset, cfg, torch.device("cpu"))
    history = server.run(str(tmp_path))

    assert len(history) == 2
    assert all(record["global_sync"] for record in history)
    assert all("associations" in record for record in history)
    assert all(len(record["cells"]) == 2 for record in history)
    assert (tmp_path / "history.json").exists()
