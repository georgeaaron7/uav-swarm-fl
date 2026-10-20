"""Aggregate completed benchmark runs across seeds into CSV and Markdown."""
from __future__ import annotations

import argparse
import csv
import json
import math
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

RUN_FIELDS = (
    "diverged",
    "divergence_round",
    "divergence_stage",
    "completed_rounds",
    "final_test_acc",
    "last_finite_test_acc",
    "best_test_acc",
    "best_round",
    "mean_last5_test_acc",
) + METRICS


def find_summaries(root: Path):
    for path in root.rglob("summary.json"):
        run_name = path.parent.name
        if "__" not in run_name:
            continue
        scenario, aggregator = run_name.rsplit("__", 1)
        seed_dir = path.parent.parent.name
        seed = seed_dir.removeprefix("seed") if seed_dir.startswith("seed") else ""
        with path.open() as handle:
            yield scenario, aggregator, seed, json.load(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("results/benchmark"))
    args = parser.parse_args()
    groups = defaultdict(list)
    run_rows = []
    for scenario, aggregator, seed, summary in find_summaries(args.root):
        groups[(scenario, aggregator)].append(summary)
        run_rows.append({
            "seed": seed,
            "scenario": scenario,
            "aggregator": aggregator,
            **{field: summary.get(field) for field in RUN_FIELDS},
        })
    if not groups:
        raise SystemExit(f"no benchmark summary.json files found under {args.root}")

    runs_csv_path = args.root / "benchmark_runs.csv"
    with runs_csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(run_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(sorted(
            run_rows,
            key=lambda row: (int(row["seed"]) if row["seed"] else -1,
                             row["scenario"], row["aggregator"]),
        ))

    rows = []
    for (scenario, aggregator), summaries in sorted(groups.items()):
        diverged = sum(bool(summary.get("diverged", False)) for summary in summaries)
        completed_summaries = [
            summary for summary in summaries if not summary.get("diverged", False)
        ]
        row = {
            "scenario": scenario,
            "aggregator": aggregator,
            "seeds": len(summaries),
            "successful_seeds": len(summaries) - diverged,
            "diverged_seeds": diverged,
            "divergence_rate": diverged / len(summaries),
        }
        for metric in METRICS:
            values = []
            for summary in completed_summaries:
                value = summary.get(metric)
                if value is None:
                    continue
                value = float(value)
                if math.isfinite(value):
                    values.append(value)
            row[f"{metric}_mean"] = statistics.fmean(values) if values else float("nan")
            row[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        rows.append(row)

    csv_path = args.root / "benchmark_summary.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    md_path = args.root / "BENCHMARK_SUMMARY.md"
    with md_path.open("w") as handle:
        handle.write("# Multi-seed benchmark summary\n\n")
        handle.write(
            "Accuracy is reported as mean ± sample standard deviation across non-diverged seeds; "
            "divergence is reported separately and is never silently imputed.\n\n"
        )
        handle.write("| Scenario | Aggregator | Successful/total | Diverged | Final accuracy | PDR | Latency (s) | Handovers |\n")
        handle.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
        for row in rows:
            accuracy = (
                f"{100 * row['final_test_acc_mean']:.2f} ± "
                f"{100 * row['final_test_acc_std']:.2f}"
                if math.isfinite(row["final_test_acc_mean"]) else "—"
            )
            handle.write(
                f"| {row['scenario']} | {row['aggregator']} | "
                f"{row['successful_seeds']}/{row['seeds']} | {row['diverged_seeds']} | "
                f"{accuracy} | "
                f"{row['mean_pdr_mean']:.3f} | {row['mean_latency_s_mean']:.3f} | "
                f"{row['total_handovers_mean']:.1f} |\n"
            )
    print(f"wrote {runs_csv_path}, {csv_path}, and {md_path}")


if __name__ == "__main__":
    main()
