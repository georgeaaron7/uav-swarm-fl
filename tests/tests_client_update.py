from types import SimpleNamespace

import numpy as np
import torch
import torch.nn as nn

from fl.client import DroneClient
from fl.data import TensorImageDataset


class TinyClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(3 * 32 * 32, 2),
        )

    def forward(self, x):
        return self.classifier(x)


def make_config():
    return SimpleNamespace(
        local_epochs=1,
        batch_size=4,
        lr=0.01,
        momentum=0.0,
        weight_decay=0.0,
    )


def make_dataset():
    images = torch.randn(8, 3, 32, 32)
    targets = torch.tensor([0, 1, 0, 1, 0, 1, 0, 1])
    return TensorImageDataset(images, targets)


def test_client_update_contains_delta_and_metadata():
    dataset = make_dataset()
    model = TinyClassifier()

    client = DroneClient(
        client_id=3,
        dataset=dataset,
        indices=np.arange(len(dataset)),
        cfg=make_config(),
        device=torch.device("cpu"),
    )

    client.link_telemetry = {
        "snr_db": 12.5,
        "packet_loss": 0.1,
    }
    client.context = {
        "altitude_m": 50,
        "visibility": "fog",
    }
    client.staleness = 2
    client.is_malicious = True

    global_state = {
        key: value.detach().cpu().clone()
        for key, value in model.state_dict().items()
    }

    update = client.local_train(model)

    assert update.client_id == 3
    assert update.num_samples == len(dataset)

    assert update.link_telemetry == {
        "snr_db": 12.5,
        "packet_loss": 0.1,
    }
    assert update.context == {
        "altitude_m": 50,
        "visibility": "fog",
    }
    assert update.staleness == 2
    assert update.oracle_is_malicious is True

    assert set(update.delta) == {
        key
        for key, value in global_state.items()
        if torch.is_floating_point(value)
    }

    for key, tensor in global_state.items():
        if not torch.is_floating_point(tensor):
            continue

        reconstructed = tensor + update.delta[key]

        assert torch.allclose(
            reconstructed,
            update.state_dict[key],
            atol=1e-6,
        )


def test_update_metadata_is_copied_from_client():
    dataset = make_dataset()

    client = DroneClient(
        client_id=0,
        dataset=dataset,
        indices=np.arange(len(dataset)),
        cfg=make_config(),
        device=torch.device("cpu"),
    )

    client.link_telemetry = {"snr_db": 20.0}
    client.context = {"weather": "clear"}

    update = client.local_train(TinyClassifier())

    client.link_telemetry["snr_db"] = 1.0
    client.context["weather"] = "storm"

    assert update.link_telemetry["snr_db"] == 20.0
    assert update.context["weather"] == "clear"