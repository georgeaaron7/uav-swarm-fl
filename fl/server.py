"""Federated training loop: local training -> lossy wireless uplink -> aggregation.

The aggregation rule is pluggable (see fl/aggregators.py). For a fair comparison,
every rule sees the same data split, the same malicious drones, the same channel
realisation (seeded by round and drone id) and the same model initialisation.
"""
from __future__ import annotations

import csv
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from .aggregators import FedAvg, build_aggregator  # noqa: F401  (re-exported for callers/tests)
from .channel import WirelessChannel
from .client import DroneClient


def flatten(state: dict) -> torch.Tensor:
    return torch.cat([v.detach().float().reshape(-1).cpu() for v in state.values()])


def unflatten(vec: torch.Tensor, like: dict) -> dict:
    out, i = {}, 0
    for k, v in like.items():
        n = v.numel()
        out[k] = vec[i:i + n].view_as(v).to(v.dtype)
        i += n
    return out


@torch.no_grad()
def evaluate(model: nn.Module, dataset, device, batch_size: int = 512, num_classes: int = 10):
    model.eval()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    loss_fn = nn.CrossEntropyLoss(reduction="sum")
    total_loss, correct, n = 0.0, 0, 0
    class_correct = torch.zeros(num_classes)
    class_total = torch.zeros(num_classes)
    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        out = model(xb)
        total_loss += loss_fn(out, yb).item()
        pred = out.argmax(1)
        correct += (pred == yb).sum().item()
        n += len(yb)
        class_total += torch.bincount(yb.cpu(), minlength=num_classes).float()
        class_correct += torch.bincount(yb[pred == yb].cpu(), minlength=num_classes).float()
    per_class = (class_correct / class_total.clamp(min=1)).tolist()
    return {"test_loss": total_loss / n, "test_acc": correct / n, "per_class_acc": per_class}


class FederatedServer:
    def __init__(self, model: nn.Module, clients: list[DroneClient], test_ds, cfg, device,
                 root_client: DroneClient | None = None):
        self.root_client = root_client  # TEE-held trusted reference set (used by CCRA)
        self.model = model.to(device)
        self.clients = clients
        self.test_ds = test_ds
        self.cfg = cfg
        self.device = device
        self.aggregator = build_aggregator(cfg.aggregator, cfg)
        self.channel = WirelessChannel(cfg, len(clients))
        self.rng = np.random.default_rng(cfg.seed)
        self.history: list[dict] = []

    def sample_clients(self) -> list[DroneClient]:
        m = max(1, int(round(self.cfg.client_fraction * len(self.clients))))
        idx = self.rng.choice(len(self.clients), size=m, replace=False)
        return [self.clients[i] for i in sorted(idx)]

    def run(self, run_dir: str) -> list[dict]:
        cfg = self.cfg
        csv_path = os.path.join(run_dir, "metrics.csv")
        fields = ["round", "test_acc", "test_loss", "train_loss", "num_received",
                  "mean_pdr", "malicious_weight", "round_time_s"]
        with open(csv_path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()

        best_acc = 0.0
        malicious = {c.client_id for c in self.clients if c.is_malicious}
        for rnd in range(1, cfg.rounds + 1):
            t0 = time.time()
            selected = self.sample_clients()
            global_state = {k: v.detach().cpu().clone() for k, v in self.model.state_dict().items()}
            g_vec = flatten(global_state)
            links = self.channel.link_state(rnd)

            received, drones = [], {}
            train_losses = []
            for c in selected:
                upd = c.local_train(self.model)
                train_losses.append(upd.metrics["train_loss"])
                delta = flatten(upd.state_dict) - g_vec
                rx, mask, tel = self.channel.transmit(delta, links[c.client_id], rnd, c.client_id)
                drones[c.client_id] = {k: tel[k] for k in ("sinr_db", "per", "pdr")}
                if tel["pdr"] > 0:  # nothing arrived -> drone silently missing this round
                    received.append({"id": c.client_id, "delta": rx, "mask": mask,
                                     "n": upd.num_samples, "tel": tel})

            if received:
                if getattr(self.aggregator, "needs_root", False) and self.root_client is not None:
                    root = flatten(self.root_client.local_train(self.model).state_dict) - g_vec
                    agg_delta, info = self.aggregator.aggregate(received, root=root)
                else:
                    agg_delta, info = self.aggregator.aggregate(received)
                self.model.load_state_dict(unflatten(g_vec + agg_delta, global_state))
                for cid, w in info["weights"].items():
                    drones[cid]["weight"] = w
                if "trust" in info:
                    for cid in drones:
                        drones[cid]["trust"] = info["trust"].get(cid)

            record = {
                "round": rnd,
                "train_loss": float(np.mean(train_losses)),
                "num_received": len(received),
                "mean_pdr": float(np.mean([d["pdr"] for d in drones.values()])),
                "malicious_weight": float(sum(d.get("weight", 0.0) for cid, d in drones.items()
                                              if cid in malicious)),
                "drones": drones,
            }
            if rnd % cfg.eval_every == 0 or rnd == cfg.rounds:
                record.update(evaluate(self.model, self.test_ds, self.device, cfg.eval_batch_size))
            record["round_time_s"] = time.time() - t0
            self.history.append(record)

            with open(csv_path, "a", newline="") as f:
                csv.DictWriter(f, fieldnames=fields, extrasaction="ignore").writerow(record)

            acc = record.get("test_acc")
            if acc is not None and acc > best_acc:
                best_acc = acc
                torch.save(self.model.state_dict(), os.path.join(run_dir, "best_model.pt"))
            acc_str = f"{acc * 100:6.2f}%" if acc is not None else "   -   "
            print(f"[{cfg.name} r{rnd:3d}/{cfg.rounds}] acc={acc_str} pdr={record['mean_pdr']:.2f} "
                  f"mal_w={record['malicious_weight']:.2f} ({record['round_time_s']:.1f}s)", flush=True)

        torch.save(self.model.state_dict(), os.path.join(run_dir, "final_model.pt"))
        with open(os.path.join(run_dir, "history.json"), "w") as f:
            json.dump(self.history, f, indent=2)
        return self.history
