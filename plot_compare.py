"""Figures + table for the FedAvg / CosAvg / CCRA comparison.

    python plot_compare.py      # reads results/compare/*, writes results/compare/*.png + RESULTS.md
"""
from __future__ import annotations

import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = "results/compare"
SCEN_TITLES = {
    "clean_ideal": "No attack, ideal channel",
    "clean_lossy": "No attack, EW-jammed lossy channel",
    "attack_ideal": "30% label-flip, ideal channel",
    "attack_lossy": "30% label-flip + EW-jammed lossy channel",
}
AGG_LABELS = {"fedavg": "FedAvg", "cosavg": "CosAvg (base paper)", "ccra": "CCRA (ours)",
              "ccra_noctx": "CCRA w/o channel context"}
COLORS = {"fedavg": "#7f7f7f", "cosavg": "#1f77b4", "ccra": "#d62728", "ccra_noctx": "#ff9896"}
MALICIOUS, JAMMED = {0, 3, 6}, {2, 5, 9}


def load():
    runs = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "*__*"))):
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "history.json")):
            continue
        scen, agg = os.path.basename(d).split("__")
        with open(os.path.join(d, "history.json")) as f:
            runs[(scen, agg)] = json.load(f)
    return runs


def final_acc(h, k=5):
    return 100 * float(np.mean([r["test_acc"] for r in h[-k:]]))


def main():
    runs = load()
    scens = [s for s in SCEN_TITLES if any(k[0] == s for k in runs)]

    # 1. accuracy curves, one panel per scenario
    fig, axes = plt.subplots(1, len(scens), figsize=(5 * len(scens), 4.2), sharey=True, squeeze=False)
    for ax, s in zip(axes[0], scens):
        for agg in AGG_LABELS:
            if (s, agg) in runs:
                h = runs[(s, agg)]
                ax.plot([r["round"] for r in h], [100 * r["test_acc"] for r in h],
                        label=AGG_LABELS[agg], color=COLORS[agg], lw=2,
                        ls="--" if agg == "ccra_noctx" else "-")
        ax.set_title(SCEN_TITLES[s], fontsize=10)
        ax.set_xlabel("Communication round")
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("Global test accuracy (%)")
    axes[0][0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "accuracy_curves.png"), dpi=150)

    # 2. bar chart of final accuracy
    aggs = [a for a in AGG_LABELS if any(k[1] == a for k in runs)]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    width = 0.8 / len(aggs)
    for i, agg in enumerate(aggs):
        vals = [final_acc(runs[(s, agg)]) if (s, agg) in runs else 0 for s in scens]
        bars = ax.bar(np.arange(len(scens)) + i * width, vals, width, label=AGG_LABELS[agg], color=COLORS[agg])
        ax.bar_label(bars, fmt="%.1f", fontsize=7)
    ax.set_xticks(np.arange(len(scens)) + width * (len(aggs) - 1) / 2)
    ax.set_xticklabels([SCEN_TITLES[s] for s in scens], fontsize=8)
    ax.set_ylabel("Final accuracy (%) (mean of last 5 rounds)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "final_accuracy_bars.png"), dpi=150)

    # 3. who gets the weight? (attack + lossy channel)
    s = "attack_lossy"
    if any(k[0] == s for k in runs):
        fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
        for ax, agg in zip(axes, ["fedavg", "cosavg", "ccra"]):
            if (s, agg) not in runs:
                continue
            h = runs[(s, agg)]
            rounds = [r["round"] for r in h]
            groups = {"malicious (0,3,6)": MALICIOUS, "honest + jammed (2,5,9)": JAMMED,
                      "honest, clear link": set(range(10)) - MALICIOUS - JAMMED}
            for (lab, ids), col in zip(groups.items(), ["#d62728", "#ff7f0e", "#2ca02c"]):
                ax.plot(rounds, [sum(r["drones"].get(str(i), {}).get("weight", 0.0) for i in ids) for r in h],
                        label=lab, color=col, lw=2)
            ax.set_title(f"{AGG_LABELS[agg]}: aggregation weight share", fontsize=10)
            ax.set_xlabel("Communication round")
            ax.grid(alpha=0.3)
        axes[0].set_ylabel("Total weight of group")
        axes[0].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(ROOT, "weight_share_attack_lossy.png"), dpi=150)

    # 4. table
    lines = ["| Scenario | " + " | ".join(AGG_LABELS[a] for a in aggs) + " |",
             "|---|" + "---|" * len(aggs)]
    for sc in scens:
        cells = [f"{final_acc(runs[(sc, a)]):.2f}" if (sc, a) in runs else "–" for a in aggs]
        lines.append(f"| {SCEN_TITLES[sc]} | " + " | ".join(cells) + " |")
    mal = ["", "Average weight given to malicious drones (last 10 rounds):", ""]
    for sc in ("attack_ideal", "attack_lossy"):
        for a in aggs:
            if (sc, a) in runs:
                mw = np.mean([r["malicious_weight"] for r in runs[(sc, a)][-10:]])
                mal.append(f"- {SCEN_TITLES[sc]} / {AGG_LABELS[a]}: {mw:.3f}")
    with open(os.path.join(ROOT, "RESULTS.md"), "w", encoding="utf-8") as f:
        f.write("# FedAvg vs CosAvg vs CCRA\n\nFinal accuracy (%), mean of last 5 rounds:\n\n")
        f.write("\n".join(lines + mal) + "\n")
    print("\n".join(lines + mal))


if __name__ == "__main__":
    main()
