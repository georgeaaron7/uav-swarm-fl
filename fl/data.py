"""Dataset loading, "aerial" modification of CIFAR-10, and partitioning across drones.

Aerial modification
-------------------
Imagery captured by a downward-looking (nadir) drone camera has no canonical
"up" direction, and the apparent scale/sharpness depends on flight altitude.
We emulate this on CIFAR-10 by:
  * a fixed, per-image random rotation by k*90 degrees (applied to train AND test,
    so the evaluation set also has arbitrary orientation), and
  * a per-image random "altitude" degradation: downsample then upsample back
    to 32x32 (higher altitude = fewer effective pixels).
During local training we additionally apply random flips / rot90 / crops,
which is the standard augmentation for overhead imagery.

All data is held as in-memory tensors (no per-sample PIL transforms), which is
much faster on CPU and avoids DataLoader worker issues on Windows.
"""
from __future__ import annotations

import os

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset

CIFAR10_MEAN = (0.4914, 0.4822, 0.4465)
CIFAR10_STD = (0.2470, 0.2435, 0.2616)
CIFAR10_CLASSES = (
    "airplane", "automobile", "bird", "cat", "deer",
    "dog", "frog", "horse", "ship", "truck",
)


class TensorImageDataset(Dataset):
    """Normalised float images (N,C,H,W) + integer labels.

    `targets` is a plain tensor so Month 2 label-flipping attacks can simply
    overwrite labels for a malicious drone's subset.
    """

    def __init__(self, images: torch.Tensor, targets: torch.Tensor):
        self.images = images
        self.targets = targets

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, idx):
        return self.images[idx], self.targets[idx]


def _to_tensor(np_images: np.ndarray) -> torch.Tensor:
    x = torch.from_numpy(np_images).permute(0, 3, 1, 2).float().div_(255.0)
    return x


def _normalise(x: torch.Tensor) -> torch.Tensor:
    mean = torch.tensor(CIFAR10_MEAN).view(1, 3, 1, 1)
    std = torch.tensor(CIFAR10_STD).view(1, 3, 1, 1)
    return (x - mean) / std


def aerialize(x: torch.Tensor, seed: int) -> torch.Tensor:
    """Apply the fixed per-image aerial modification (orientation + altitude)."""
    g = torch.Generator().manual_seed(seed)
    n = x.shape[0]
    out = x.clone()

    # 1) arbitrary nadir orientation: rotate each image by k*90 degrees
    ks = torch.randint(0, 4, (n,), generator=g)
    for k in range(1, 4):
        idx = (ks == k).nonzero(as_tuple=True)[0]
        if len(idx):
            out[idx] = torch.rot90(out[idx], k, dims=(2, 3))

    # 2) altitude degradation: resample at a lower effective resolution
    #    32 px = low altitude (no change), 24/16 px = higher altitude
    levels = torch.tensor([32, 24, 16])
    choice = torch.multinomial(torch.tensor([0.5, 0.3, 0.2]), n, replacement=True, generator=g)
    for li, size in enumerate(levels.tolist()):
        if size == 32:
            continue
        idx = (choice == li).nonzero(as_tuple=True)[0]
        if len(idx):
            small = F.interpolate(out[idx], size=(size, size), mode="bilinear", align_corners=False)
            out[idx] = F.interpolate(small, size=(32, 32), mode="bilinear", align_corners=False)
    return out


def load_dataset(name: str, data_dir: str, seed: int):
    """Returns (train_ds, test_ds, num_classes)."""
    if name not in ("cifar10", "cifar10_aerial"):
        raise ValueError(f"Unknown dataset '{name}'")

    cache = os.path.join(data_dir, "cifar10.npz")
    if os.path.exists(cache):  # created by prepare_data.py (fast mirror)
        d = np.load(cache)
        np_train, y_train, np_test, y_test = d["x_train"], d["y_train"], d["x_test"], d["y_test"]
    else:
        from torchvision.datasets import CIFAR10
        train_raw = CIFAR10(data_dir, train=True, download=True)
        test_raw = CIFAR10(data_dir, train=False, download=True)
        np_train, y_train = train_raw.data, np.array(train_raw.targets)
        np_test, y_test = test_raw.data, np.array(test_raw.targets)

    x_train, x_test = _to_tensor(np_train), _to_tensor(np_test)
    if name == "cifar10_aerial":
        x_train = aerialize(x_train, seed)
        x_test = aerialize(x_test, seed + 1)

    train_ds = TensorImageDataset(_normalise(x_train), torch.as_tensor(y_train, dtype=torch.long))
    test_ds = TensorImageDataset(_normalise(x_test), torch.as_tensor(y_test, dtype=torch.long))
    return train_ds, test_ds, 10


def augment_batch(x: torch.Tensor) -> torch.Tensor:
    """Per-batch augmentation for overhead imagery (runs on the training device)."""
    n = x.shape[0]
    # random horizontal + vertical flips
    hf = torch.rand(n, device=x.device) < 0.5
    vf = torch.rand(n, device=x.device) < 0.5
    x = torch.where(hf.view(-1, 1, 1, 1), x.flip(3), x)
    x = torch.where(vf.view(-1, 1, 1, 1), x.flip(2), x)
    # random transpose (combined with flips gives all 8 dihedral orientations)
    tp = torch.rand(n, device=x.device) < 0.5
    x = torch.where(tp.view(-1, 1, 1, 1), x.transpose(2, 3), x)
    # random crop with 4px padding
    pad = F.pad(x, (4, 4, 4, 4), mode="reflect")
    i, j = np.random.randint(0, 9, size=2)
    return pad[:, :, i:i + 32, j:j + 32]


# ---------------------------------------------------------------------------
# Partitioning the training set across drones
# ---------------------------------------------------------------------------

def partition_iid(num_samples: int, num_clients: int, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(num_samples)
    return [np.sort(s) for s in np.array_split(perm, num_clients)]


def partition_dirichlet(targets: np.ndarray, num_clients: int, alpha: float, seed: int,
                        min_size: int = 10) -> list[np.ndarray]:
    """Label-skewed non-IID split: each drone sees a different class mix
    (e.g. drones covering different terrain sectors)."""
    rng = np.random.default_rng(seed)
    num_classes = int(targets.max()) + 1
    while True:
        buckets: list[list[int]] = [[] for _ in range(num_clients)]
        for c in range(num_classes):
            idx_c = rng.permutation(np.where(targets == c)[0])
            props = rng.dirichlet(np.full(num_clients, alpha))
            cuts = (np.cumsum(props) * len(idx_c)).astype(int)[:-1]
            for b, part in zip(buckets, np.split(idx_c, cuts)):
                b.extend(part.tolist())
        if min(len(b) for b in buckets) >= min_size:
            return [np.sort(np.array(b)) for b in buckets]


def partition(
    train_ds: TensorImageDataset,
    cfg,
    eligible_indices: np.ndarray | None = None,
) -> list[np.ndarray]:
    eligible = (
        np.arange(len(train_ds), dtype=int)
        if eligible_indices is None else np.asarray(eligible_indices, dtype=int)
    )
    if eligible.ndim != 1 or len(eligible) == 0:
        raise ValueError("eligible_indices must be a non-empty one-dimensional array")
    if cfg.partition == "iid":
        relative = partition_iid(len(eligible), cfg.num_clients, cfg.seed)
        return [eligible[indices] for indices in relative]
    if cfg.partition == "dirichlet":
        relative = partition_dirichlet(
            train_ds.targets[eligible].numpy(), cfg.num_clients, cfg.dirichlet_alpha, cfg.seed
        )
        return [eligible[indices] for indices in relative]
    raise ValueError(f"Unknown partition '{cfg.partition}'")
