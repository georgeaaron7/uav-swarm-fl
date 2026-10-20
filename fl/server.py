"""Centralized and hierarchical federated training orchestration."""
from __future__ import annotations

import copy
import csv
import json
import math
import os
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from .aggregators import FedAvg, build_aggregator  # noqa: F401 (public compatibility)
from .attacks import craft_model_updates
from .channel import WirelessChannel
from .client import DroneClient
from .topology import SwarmTopology


class NumericalDivergenceError(RuntimeError):
    """Terminal, explicitly reportable numerical failure of an FL run."""

    def __init__(self, round_number: int, stage: str):
        self.round_number = round_number
        self.stage = stage
        super().__init__(f"numerical divergence at round {round_number} during {stage}")


def flatten(state: dict) -> torch.Tensor:
    return torch.cat([v.detach().float().reshape(-1).cpu() for v in state.values()])


def unflatten(vec: torch.Tensor, like: dict) -> dict:
    out, index = {}, 0
    for key, value in like.items():
        count = value.numel()
        out[key] = vec[index:index + count].view_as(value).to(value.dtype)
        index += count
    return out


@torch.no_grad()
def evaluate(model: nn.Module, dataset, device, batch_size: int = 512, num_classes: int = 10):
    model.eval()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    loss_fn = nn.CrossEntropyLoss(reduction="sum")
    total_loss, correct, count = 0.0, 0, 0
    class_correct = torch.zeros(num_classes)
    class_total = torch.zeros(num_classes)
    for images, targets in loader:
        images, targets = images.to(device), targets.to(device)
        output = model(images)
        total_loss += loss_fn(output, targets).item()
        prediction = output.argmax(1)
        correct += (prediction == targets).sum().item()
        count += len(targets)
        class_total += torch.bincount(targets.cpu(), minlength=num_classes).float()
        class_correct += torch.bincount(
            targets[prediction == targets].cpu(), minlength=num_classes
        ).float()
    return {
        "test_loss": total_loss / count,
        "test_acc": correct / count,
        "per_class_acc": (class_correct / class_total.clamp(min=1)).tolist(),
    }


class FederatedServer:
    def __init__(self, model: nn.Module, clients: list[DroneClient], test_ds, cfg, device,
                 root_client: DroneClient | None = None):
        self.root_client = root_client
        self.model = model.to(device)  # globally synchronized model
        self.clients = clients
        self.test_ds = test_ds
        self.cfg = cfg
        self.device = device
        self.aggregator = build_aggregator(cfg.aggregator, cfg)
        self.topology = SwarmTopology(cfg, len(clients))
        self.channel = WirelessChannel(cfg, len(clients), self.topology)
        self.edge_models = [copy.deepcopy(self.model).to(device)
                            for _ in range(self.topology.num_base_stations)]
        self.rng = np.random.default_rng(cfg.seed)
        self.history: list[dict] = []
        self.delivery_sum = np.zeros(len(clients), dtype=float)
        self.delivery_attempts = np.zeros(len(clients), dtype=int)

    def _training_seed(self, rnd: int, client_id: int) -> int:
        return int(
            (self.cfg.seed * 1_000_003 + rnd * 1_009 + (client_id + 1) * 9_176)
            % (2**63 - 1)
        )

    def sample_clients(self) -> list[DroneClient]:
        count = max(1, int(round(self.cfg.client_fraction * len(self.clients))))
        indices = self.rng.choice(len(self.clients), size=count, replace=False)
        return [self.clients[index] for index in sorted(indices)]

    def _reliability(self, client_id: int) -> float:
        attempts = self.delivery_attempts[client_id]
        return 1.0 if attempts == 0 else float(self.delivery_sum[client_id] / attempts)

    def _aggregate(self, updates: list[dict], root: torch.Tensor | None):
        # Krum is undefined for fewer than three updates. Sparse cells use an
        # explicit FedAvg fallback and record it in the cell diagnostics.
        if self.cfg.aggregator in {"krum", "multi_krum"} and len(updates) < 3:
            delta, info = FedAvg(self.cfg).aggregate(updates)
            info["fallback"] = "fedavg_insufficient_krum_clients"
            return delta, info
        if getattr(self.aggregator, "needs_root", False):
            return self.aggregator.aggregate(updates, root=root)
        return self.aggregator.aggregate(updates)

    def _cell_population_weights(self) -> dict[int, float]:
        populations = {
            bs: sum(c.num_samples for c in self.clients if self.topology.serving[c.client_id] == bs)
            for bs in range(self.topology.num_base_stations)
        }
        active = [bs for bs, population in populations.items() if population > 0]
        if not active:
            return {}
        weights = np.array([populations[bs] for bs in active], dtype=float)
        weights /= weights.sum()
        return {bs: float(weight) for bs, weight in zip(active, weights)}

    def _synchronize_global(self, rnd: int) -> dict[int, float]:
        population_weights = self._cell_population_weights()
        active = list(population_weights)
        if not active:
            return {}
        states = [self.edge_models[bs].state_dict() for bs in active]
        vectors = torch.stack([flatten(state) for state in states])
        weights = torch.tensor(
            [population_weights[bs] for bs in active], dtype=torch.float32
        )
        global_vector = (weights[:, None] * vectors).sum(0)
        if not torch.isfinite(global_vector).all():
            raise NumericalDivergenceError(rnd, "global synchronization")
        template = self.model.state_dict()
        self.model.load_state_dict(unflatten(global_vector, template))
        synced_state = copy.deepcopy(self.model.state_dict())
        for edge_model in self.edge_models:
            edge_model.load_state_dict(synced_state)
        return population_weights

    def run(self, run_dir: str) -> list[dict]:
        cfg = self.cfg
        csv_path = os.path.join(run_dir, "metrics.csv")
        fields = [
            "round", "test_acc", "test_loss", "train_loss", "num_received", "mean_pdr",
            "mean_latency_s", "deadline_drop_rate", "stale_update_rate", "handovers",
            "malicious_weight", "honest_rejection_rate", "attacker_acceptance_rate",
            "max_cell_byzantine_fraction", "byzantine_majority_cells",
            "krum_fallback_cells", "robustness_bound_violating_cells",
            "global_sync", "round_time_s",
        ]
        with open(csv_path, "w", newline="") as handle:
            csv.DictWriter(handle, fieldnames=fields).writeheader()

        best_accuracy = 0.0
        malicious = {c.client_id for c in self.clients if c.is_malicious}
        for rnd in range(1, cfg.rounds + 1):
            # Keep a known-good globally synchronized state. If an attack makes
            # a run diverge, the caller can save this state without persisting
            # NaN/Inf parameters as if they were a trained model.
            self.last_valid_global_state = copy.deepcopy(self.model.state_dict())
            start_time = time.time()
            links = self.channel.link_state(rnd)
            selected = self.sample_clients()
            pending: dict[int, list[dict]] = {
                bs: [] for bs in range(self.topology.num_base_stations)
            }
            train_losses = []
            drones: dict[int, dict] = {}

            for client in selected:
                cid = client.client_id
                link = links[cid]
                bs = int(link["serving_bs"])
                context = {
                    key: link[key] for key in (
                        "serving_bs", "handover", "handover_count", "distance_m", "altitude_m"
                    )
                } | {"reliability": self._reliability(cid)}
                if "trace_speed_normalized" in link:
                    context["trace_speed_normalized"] = link["trace_speed_normalized"]
                if "trace_source_index" in link:
                    context["trace_source_index"] = link["trace_source_index"]
                client.link_telemetry = dict(link)
                client.context = dict(context)
                client.staleness = 0
                update = client.local_train(
                    self.edge_models[bs], seed=self._training_seed(rnd, cid)
                )
                if not math.isfinite(update.metrics["train_loss"]):
                    raise NumericalDivergenceError(rnd, f"client {cid} local training")
                train_losses.append(update.metrics["train_loss"])
                base_state = {
                    key: value.detach().cpu().clone()
                    for key, value in self.edge_models[bs].state_dict().items()
                }
                pending[bs].append({
                    "id": cid,
                    "delta": flatten(update.state_dict) - flatten(base_state),
                    "n": update.num_samples,
                    "ctx": context,
                })

            for records in pending.values():
                craft_model_updates(records, cfg.attack, malicious, cfg, rnd)

            received_by_bs: dict[int, list[dict]] = {
                bs: [] for bs in range(self.topology.num_base_stations)
            }
            for bs, records in pending.items():
                for record in records:
                    cid = record["id"]
                    received_delta, mask, telemetry = self.channel.transmit(
                        record["delta"], links[cid], rnd, cid
                    )
                    self.delivery_attempts[cid] += 1
                    self.delivery_sum[cid] += telemetry["pdr"]
                    record["ctx"]["reliability"] = self._reliability(cid)
                    record.update({
                        "delta": received_delta,
                        "mask": mask,
                        "tel": telemetry,
                        "staleness": telemetry["staleness"],
                    })
                    if not torch.isfinite(record["delta"]).all():
                        raise NumericalDivergenceError(rnd, f"client {cid} transmitted update")
                    # Ideal links use +Inf internally for unbounded SNR/rate.
                    # JSON diagnostics use null for those not-applicable limits
                    # so every artifact remains standards-compliant JSON.
                    serializable_telemetry = {
                        key: (
                            None
                            if isinstance(value, float) and not math.isfinite(value)
                            else value
                        )
                        for key, value in telemetry.items()
                    }
                    drones[cid] = serializable_telemetry | {
                        "oracle_is_malicious": cid in malicious,
                        "weight": 0.0,
                        "reliability": record["ctx"]["reliability"],
                    }
                    if mask.any():
                        received_by_bs[bs].append(record)

            cell_info = {}
            for bs, updates in received_by_bs.items():
                if not updates:
                    cell_info[bs] = {"selected": len(pending[bs]), "received": 0}
                    continue
                edge_model = self.edge_models[bs]
                edge_state = {
                    key: value.detach().cpu().clone()
                    for key, value in edge_model.state_dict().items()
                }
                edge_vector = flatten(edge_state)
                root = None
                if getattr(self.aggregator, "needs_root", False):
                    if self.root_client is None:
                        raise RuntimeError(f"{cfg.aggregator} requires a trusted root client")
                    root = flatten(self.root_client.local_train(
                        edge_model, seed=self._training_seed(rnd, -1)
                    ).state_dict) - edge_vector
                aggregate, info = self._aggregate(updates, root)
                if not torch.isfinite(aggregate).all():
                    raise NumericalDivergenceError(rnd, f"base station {bs} aggregation")
                candidate = edge_vector + aggregate
                if not torch.isfinite(candidate).all():
                    raise NumericalDivergenceError(rnd, f"base station {bs} model update")
                edge_model.load_state_dict(unflatten(candidate, edge_state))
                for cid, weight in info["weights"].items():
                    drones[cid]["weight"] = weight
                if "trust" in info:
                    for cid in drones:
                        drones[cid]["trust"] = info["trust"].get(cid)
                actual_f = sum(u["id"] in malicious for u in updates)
                bound_violated = False
                if cfg.aggregator in {"krum", "multi_krum"}:
                    bound_violated = actual_f > info.get("effective_f", 0)
                elif cfg.aggregator == "median":
                    bound_violated = 2 * actual_f >= len(updates)
                elif cfg.aggregator == "trimmed_mean":
                    bound_violated = actual_f > int(len(updates) * cfg.trim_ratio)
                cell_info[bs] = {
                    "selected": len(pending[bs]),
                    "received": len(updates),
                    "client_ids": [u["id"] for u in updates],
                    "malicious_received": sum(u["id"] in malicious for u in updates),
                    "byzantine_fraction": sum(u["id"] in malicious for u in updates) / len(updates),
                    "robustness_bound_violated": bound_violated,
                    **({"fallback": info["fallback"]} if "fallback" in info else {}),
                    **({"effective_f": info["effective_f"]} if "effective_f" in info else {}),
                }

            should_sync = (
                cfg.topology == "centralized"
                or rnd % cfg.global_sync_every == 0
                or rnd == cfg.rounds
            )
            sync_weights = self._synchronize_global(rnd) if should_sync else {}
            received = [update for updates in received_by_bs.values() for update in updates]
            cell_population_weights = self._cell_population_weights()
            for bs, updates in received_by_bs.items():
                for update in updates:
                    drones[update["id"]]["effective_weight"] = (
                        drones[update["id"]]["weight"]
                        * cell_population_weights.get(bs, 0.0)
                    )
            selected_drones = list(drones.values())
            honest_received = [u for u in received if u["id"] not in malicious]
            malicious_received = [u for u in received if u["id"] in malicious]
            record = {
                "round": rnd,
                "train_loss": float(np.mean(train_losses)),
                "num_received": len(received),
                "mean_pdr": float(np.mean([d["pdr"] for d in selected_drones])),
                "mean_latency_s": float(np.mean([d["latency_s"] for d in selected_drones])),
                "deadline_drop_rate": float(np.mean([
                    d["drop_reason"] == "deadline" for d in selected_drones
                ])),
                "stale_update_rate": float(np.mean([d["staleness"] > 0 for d in selected_drones])),
                "handovers": int(sum(link["handover"] for link in links)),
                "malicious_weight": float(sum(
                    drones[u["id"]].get("effective_weight", 0.0) for u in malicious_received
                )),
                "honest_rejection_rate": float(np.mean([
                    drones[u["id"]]["weight"] <= 0 for u in honest_received
                ])) if honest_received else 0.0,
                "attacker_acceptance_rate": float(np.mean([
                    drones[u["id"]]["weight"] > 0 for u in malicious_received
                ])) if malicious_received else 0.0,
                "max_cell_byzantine_fraction": max(
                    (info.get("byzantine_fraction", 0.0) for info in cell_info.values()),
                    default=0.0,
                ),
                "byzantine_majority_cells": sum(
                    info.get("byzantine_fraction", 0.0) >= 0.5
                    for info in cell_info.values() if info.get("received", 0) > 0
                ),
                "krum_fallback_cells": sum(
                    info.get("fallback") == "fedavg_insufficient_krum_clients"
                    for info in cell_info.values()
                ),
                "robustness_bound_violating_cells": sum(
                    info.get("robustness_bound_violated", False)
                    for info in cell_info.values()
                ),
                "global_sync": should_sync,
                "sync_weights": sync_weights,
                "cells": cell_info,
                "associations": {cid: int(link["serving_bs"]) for cid, link in enumerate(links)},
                "drones": drones,
            }
            if rnd % cfg.eval_every == 0 or rnd == cfg.rounds:
                evaluation = evaluate(self.model, self.test_ds, self.device, cfg.eval_batch_size)
                numeric_values = [evaluation["test_loss"], evaluation["test_acc"]]
                numeric_values.extend(evaluation["per_class_acc"])
                if not all(math.isfinite(value) for value in numeric_values):
                    raise NumericalDivergenceError(rnd, "model evaluation")
                record.update(evaluation)
            record["round_time_s"] = time.time() - start_time
            self.history.append(record)

            with open(csv_path, "a", newline="") as handle:
                csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore").writerow(record)

            accuracy = record.get("test_acc")
            if accuracy is not None and accuracy > best_accuracy:
                best_accuracy = accuracy
                torch.save(self.model.state_dict(), os.path.join(run_dir, "best_model.pt"))
            accuracy_text = f"{accuracy * 100:6.2f}%" if accuracy is not None else "   -   "
            print(
                f"[{cfg.name} r{rnd:3d}/{cfg.rounds}] acc={accuracy_text} "
                f"pdr={record['mean_pdr']:.2f} handovers={record['handovers']} "
                f"mal_w={record['malicious_weight']:.2f} ({record['round_time_s']:.1f}s)",
                flush=True,
            )

        torch.save(self.model.state_dict(), os.path.join(run_dir, "final_model.pt"))
        with open(os.path.join(run_dir, "history.json"), "w") as handle:
            json.dump(self.history, handle, indent=2, allow_nan=False)
        return self.history
