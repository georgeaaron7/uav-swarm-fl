import csv
import json
import subprocess
import sys
from pathlib import Path


def test_analysis_separates_divergence_from_accuracy(tmp_path):
    metrics = {
        "mean_pdr": 1.0,
        "mean_latency_s": 0.0,
        "total_handovers": 0,
        "mean_honest_rejection_rate": 0.0,
        "mean_attacker_acceptance_rate": 1.0,
        "mean_max_cell_byzantine_fraction": 0.3,
        "total_byzantine_majority_cells": 0,
        "total_krum_fallback_cells": 0,
        "total_robustness_bound_violating_cells": 0,
        "total_time_min": 1.0,
    }
    for seed, diverged, accuracy, pdr in (
        (41, False, 0.5, 1.0),
        (42, True, None, 0.2),
    ):
        run_dir = tmp_path / f"seed{seed}" / "sign_flip_ideal__cosavg"
        run_dir.mkdir(parents=True)
        summary = metrics | {
            "diverged": diverged,
            "final_test_acc": accuracy,
            "mean_last5_test_acc": accuracy,
            "mean_pdr": pdr,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary))

    script = Path(__file__).parents[1] / "analyze_benchmark.py"
    subprocess.run([sys.executable, str(script), str(tmp_path)], check=True)
    with (tmp_path / "benchmark_summary.csv").open(newline="") as handle:
        row = next(csv.DictReader(handle))
    with (tmp_path / "benchmark_runs.csv").open(newline="") as handle:
        run_rows = list(csv.DictReader(handle))
    assert row["successful_seeds"] == "1"
    assert row["diverged_seeds"] == "1"
    assert float(row["divergence_rate"]) == 0.5
    assert float(row["final_test_acc_mean"]) == 0.5
    assert float(row["final_test_acc_all_runs_mean"]) == 0.3
    assert float(row["mean_pdr_mean"]) == 1.0
    assert len(run_rows) == 2
    assert [row["seed"] for row in run_rows] == ["41", "42"]
    assert [row["diverged"] for row in run_rows] == ["False", "True"]
    report = (tmp_path / "BENCHMARK_SUMMARY.md").read_text()
    assert "All-run accuracy" in report
    assert "Success-only accuracy" in report
