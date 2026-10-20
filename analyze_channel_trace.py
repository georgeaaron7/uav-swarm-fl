"""Validate a prepared trace and quantify absolute-SNR calibration sensitivity."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from fl.channel import WirelessChannel
from fl.channel_traces import ChannelTrace
from fl.config import FLConfig
from fl.topology import SwarmTopology


def quantiles(values) -> dict:
    array = np.asarray(values, dtype=float)
    return {
        "p05": float(np.quantile(array, 0.05)),
        "median": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
    }


def simulate(base: FLConfig, reference_snr_db: float, rounds: int, model_parameters: int) -> dict:
    cfg = replace(base, trace_snr_reference_db=reference_snr_db)
    topology = SwarmTopology(cfg, cfg.num_clients)
    channel = WirelessChannel(cfg, cfg.num_clients, topology)
    sinr, rate, latency, expected_pdr = [], [], [], []
    handovers = 0
    model_bits = model_parameters * cfg.bits_per_parameter
    for rnd in range(1, rounds + 1):
        links = channel.link_state(rnd)
        for link in links:
            sinr.append(link["sinr_db"])
            rate.append(link["rate_bps"] / 1e6)
            latency.append(model_bits / max(link["rate_bps"], 1e-12))
            expected_pdr.append(1.0 - link["per"])
            handovers += int(link["handover"])
    return {
        "reference_snr_db": reference_snr_db,
        "virtual_bs_radius_m": float(np.linalg.norm(topology.base_stations[1]))
        if topology.num_base_stations > 1 else 0.0,
        "sinr_db": quantiles(sinr),
        "rate_mbps": quantiles(rate),
        "upload_latency_s": quantiles(latency),
        "expected_pdr": quantiles(expected_pdr),
        "deadline_miss_fraction": float(np.mean(np.asarray(latency) > cfg.round_deadline_s)),
        "handovers": handovers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--base-stations", type=int, default=3)
    parser.add_argument("--trace-stride", type=int, default=5)
    parser.add_argument("--min-sequence-length", type=int, default=200)
    parser.add_argument("--snr-reference-db", nargs="+", type=float, default=[5, 10, 15, 20, 25])
    parser.add_argument("--model-parameters", type=int, default=156_074)
    parser.add_argument("--out", type=Path, default=Path("results/trace_validation"))
    args = parser.parse_args()

    trace = ChannelTrace(str(args.trace), min_sequence_length=args.min_sequence_length)
    base = FLConfig(
        topology="hierarchical",
        num_clients=args.clients,
        num_base_stations=args.base_stations,
        channel="trace",
        channel_trace_path=str(args.trace),
        trace_stride=args.trace_stride,
        trace_min_sequence_length=args.min_sequence_length,
        jammed_ids="",
    )
    report = {
        "trace": str(args.trace),
        "metadata": trace.metadata,
        "eligible_sequences": {str(key): len(value) for key, value in trace.sequence_indices.items()},
        "simulation": {
            "rounds": args.rounds,
            "clients": args.clients,
            "base_stations": args.base_stations,
            "model_parameters": args.model_parameters,
            "model_size_mib": args.model_parameters * base.bits_per_parameter / 8 / 2**20,
            "bandwidth_hz": base.bandwidth_hz,
            "deadline_s": base.round_deadline_s,
            "trace_stride": args.trace_stride,
            "min_sequence_length": args.min_sequence_length,
            "note": "Absolute SNR anchors are assumptions; relative power variation is measured.",
        },
        "sensitivity": [
            simulate(base, snr, args.rounds, args.model_parameters)
            for snr in args.snr_reference_db
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "trace_validation.json").open("w") as handle:
        json.dump(report, handle, indent=2)
    with (args.out / "TRACE_VALIDATION.md").open("w") as handle:
        handle.write("# Scenario 23 channel-trace validation\n\n")
        handle.write(
            "DeepSense beam powers are treated as relative measurements. Each row below changes "
            "the assumed SNR at median beam power while preserving the measured variation.\n\n"
        )
        handle.write("| Reference SNR | Median SNR | Median rate | Median upload | PDR p05 | Deadline miss | Handovers |\n")
        handle.write("|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in report["sensitivity"]:
            handle.write(
                f"| {row['reference_snr_db']:.1f} dB | {row['sinr_db']['median']:.2f} dB | "
                f"{row['rate_mbps']['median']:.2f} Mbps | {row['upload_latency_s']['median']:.3f} s | "
                f"{row['expected_pdr']['p05']:.3f} | {100 * row['deadline_miss_fraction']:.1f}% | "
                f"{row['handovers']} |\n"
            )
    print(f"wrote validation report to {args.out}")


if __name__ == "__main__":
    main()
