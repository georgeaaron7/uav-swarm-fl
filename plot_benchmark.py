"""Create meeting-ready plots from analyze_benchmark.py output."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def accuracy_heatmap(rows: list[dict], out: Path) -> None:
    scenarios = sorted({row["scenario"] for row in rows})
    aggregators = sorted({row["aggregator"] for row in rows})
    lookup = {(row["scenario"], row["aggregator"]): row for row in rows}
    values = np.full((len(scenarios), len(aggregators)), np.nan)
    for i, scenario in enumerate(scenarios):
        for j, aggregator in enumerate(aggregators):
            if (scenario, aggregator) in lookup:
                values[i, j] = 100 * float(lookup[scenario, aggregator]["final_test_acc_mean"])

    width = max(8, 1.1 * len(aggregators))
    height = max(4, 0.55 * len(scenarios))
    fig, ax = plt.subplots(figsize=(width, height))
    image = ax.imshow(values, aspect="auto", cmap="viridis", vmin=0, vmax=100)
    ax.set_xticks(range(len(aggregators)), aggregators, rotation=35, ha="right")
    ax.set_yticks(range(len(scenarios)), scenarios)
    ax.set_title("Final test accuracy across benchmark scenarios")
    for i in range(len(scenarios)):
        for j in range(len(aggregators)):
            if np.isfinite(values[i, j]):
                ax.text(j, i, f"{values[i, j]:.1f}", ha="center", va="center", fontsize=8,
                        color="white" if values[i, j] < 55 else "black")
    fig.colorbar(image, ax=ax, label="Accuracy (%)")
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)


def defense_tradeoff(rows: list[dict], out: Path) -> None:
    attacked = [row for row in rows if not row["scenario"].startswith("clean")]
    fig, ax = plt.subplots(figsize=(8, 6))
    for row in attacked:
        if int(row.get("successful_seeds", row["seeds"])) == 0:
            continue
        honest_rejection = 100 * float(row["mean_honest_rejection_rate_mean"])
        attacker_acceptance = 100 * float(row["mean_attacker_acceptance_rate_mean"])
        ax.scatter(honest_rejection, attacker_acceptance, s=35)
        ax.annotate(
            f"{row['aggregator']}\n{row['scenario'].split('_hfl')[0]}",
            (honest_rejection, attacker_acceptance), fontsize=7, xytext=(3, 3),
            textcoords="offset points",
        )
    ax.set_xlabel("Honest-update rejection rate (%) — lower is better")
    ax.set_ylabel("Attacker acceptance rate (%) — lower is better")
    ax.set_title("Defense trade-off under Byzantine attacks")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("results/benchmark"))
    args = parser.parse_args()
    summary = args.root / "benchmark_summary.csv"
    if not summary.exists():
        raise SystemExit(f"missing {summary}; run analyze_benchmark.py first")
    rows = read_rows(summary)
    accuracy_heatmap(rows, args.root / "accuracy_heatmap.png")
    defense_tradeoff(rows, args.root / "defense_tradeoff.png")
    print(f"wrote plots under {args.root}")


if __name__ == "__main__":
    main()
