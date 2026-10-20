"""Aggregate completed benchmark runs across seeds into CSV and Markdown."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


METRICS = (
    "final_test_acc",
    "mean_last5_test_acc",
    "mean_pdr",
    "mean_latency_s",
    "total_handovers",
    "mean_honest_rejection_rate",
    "mean_attacker_acceptance_rate",
    "mean_max_cell_byzantine_fraction",
    "total_byzantine_majority_cells",
    "total_krum_fallback_cells",
    "total_robustness_bound_violating_cells",
    "total_time_min",
)


def find_summaries(root: Path):
    for path in root.rglob("summary.json"):
        run_name = path.parent.name
        if "__" not in run_name:
            continue
        scenario, aggregator = run_name.rsplit("__", 1)
        with path.open() as handle:
            yield scenario, aggregator, json.load(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("results/benchmark"))
    args = parser.parse_args()
    groups = defaultdict(list)
    for scenario, aggregator, summary in find_summaries(args.root):
        groups[(scenario, aggregator)].append(summary)
    if not groups:
        raise SystemExit(f"no benchmark summary.json files found under {args.root}")

    rows = []
    for (scenario, aggregator), summaries in sorted(groups.items()):
        row = {"scenario": scenario, "aggregator": aggregator, "seeds": len(summaries)}
        for metric in METRICS:
            values = [float(summary[metric]) for summary in summaries if metric in summary]
            row[f"{metric}_mean"] = statistics.fmean(values) if values else float("nan")
            row[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        rows.append(row)

    csv_path = args.root / "benchmark_summary.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    md_path = args.root / "BENCHMARK_SUMMARY.md"
    with md_path.open("w") as handle:
        handle.write("# Multi-seed benchmark summary\n\n")
        handle.write("Accuracy is reported as mean ± sample standard deviation across completed seeds.\n\n")
        handle.write("| Scenario | Aggregator | Seeds | Final accuracy | PDR | Latency (s) | Handovers |\n")
        handle.write("|---|---|---:|---:|---:|---:|---:|\n")
        for row in rows:
            handle.write(
                f"| {row['scenario']} | {row['aggregator']} | {row['seeds']} | "
                f"{100 * row['final_test_acc_mean']:.2f} ± {100 * row['final_test_acc_std']:.2f} | "
                f"{row['mean_pdr_mean']:.3f} | {row['mean_latency_s_mean']:.3f} | "
                f"{row['total_handovers_mean']:.1f} |\n"
            )
    print(f"wrote {csv_path} and {md_path}")


if __name__ == "__main__":
    main()
