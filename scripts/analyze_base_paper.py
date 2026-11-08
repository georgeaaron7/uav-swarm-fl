"""Publish compact, path-free evidence from the completed SwarmCompute export.

No simulator or scientific configuration is modified. Divergence remains terminal.
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import io
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from analyze_context_study import interval, run_metrics
from run_context_study import completed, job_directory, read_json
from swarmcompute.shared.hashing import scientific_config, sha256

METHODS = ("bp_fresh", "bp_reuse")
ATTACKS = ("clean", "sign_flip", "alie", "ipm")
CONDITIONS = ("hfl_ideal", "hfl_trace", "hfl_trace_stress")
SEEDS = tuple(range(41, 51))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def analyze_rows(rows, seeds=SEEDS):
    by_key = {(r["seed"], r["scenario"], r["aggregator"]): r for r in rows}
    scenarios = [f"{a}_{c}" for a, c in itertools.product(ATTACKS, CONDITIONS)]
    expected = set(itertools.product(seeds, scenarios, METHODS))
    if len(by_key) != len(rows) or set(by_key) != expected:
        raise ValueError("Expected exactly one run per seed, scenario and method")
    for r in rows:
        if not 0 <= r["final_accuracy"] <= 1:
            raise ValueError("Invalid final accuracy")
        if r["diverged"] and r["final_accuracy"] != 0.1:
            raise ValueError("Diverged runs must be scored at chance")
    outcomes = {}
    for method in METHODS:
        subset = [r for r in rows if r["aggregator"] == method]
        outcomes[method] = {
            "runs": len(subset), "succeeded": sum(not r["diverged"] for r in subset),
            "diverged": sum(r["diverged"] for r in subset),
            "all_run_final_accuracy_pct": 100 * sum(r["final_accuracy"] for r in subset) / len(subset),
        }
    estimates = []
    scopes = {s: [s] for s in scenarios}
    scopes["attacked_suite"] = [s for s in scenarios if not s.startswith("clean_")]
    scopes["attacked_stress"] = [f"{a}_hfl_trace_stress" for a in ATTACKS if a != "clean"]
    for scope, cells in scopes.items():
        means = {}
        for method in METHODS:
            seed_means = [sum(by_key[(seed, cell, method)]["final_accuracy"] for cell in cells) / len(cells)
                          for seed in seeds]
            means[method] = 100 * sum(seed_means) / len(seed_means)
        differences = [sum(by_key[(seed, cell, "bp_fresh")]["final_accuracy"]
                           - by_key[(seed, cell, "bp_reuse")]["final_accuracy"]
                           for cell in cells) / len(cells) for seed in seeds]
        estimates.append({"scope": scope, "comparison": "bp_fresh_minus_bp_reuse",
                          "accuracy_pct": means, **interval(differences)})
    return {"planned_runs": len(expected), "terminal_runs": len(rows),
            "chance_accuracy": 0.1, "outcomes": outcomes, "estimates": estimates,
            "interpretation": "Separate exploratory follow-up; 10,000 percentile bootstrap resamples of paired seeds, "
                              "RNG seed 501927; attack cells averaged within seed; no multiplicity adjustment. "
                              "Numerical divergence contributes 10% final accuracy, never an excluded run. "
                              "This comparison was not part of the prespecified 720-run ablation."}


def load_summary(path):
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        if row["diverged"] not in {"True", "False"}:
            raise ValueError("Invalid divergence flag")
        row["seed"] = int(row["seed"])
        row["diverged"] = row["diverged"] == "True"
        row["final_accuracy"] = float(row["final_accuracy"])
    return rows


def publish(export, destination):
    manifest = read_json(export / "study_manifest.json")
    if not (export / "COMPLETE").is_file() or len(manifest["jobs"]) != 240:
        raise ValueError("A complete 240-run export is required")
    rows, checksums, protocols, curves = [], [], [], []
    partitions = collections.defaultdict(list)
    profiles = collections.Counter()
    resumed = 0
    for job in manifest["jobs"]:
        if not completed(job, export):
            raise ValueError(f"Missing or inconsistent terminal run: {job['config']['name']}, seed {job['seed']}")
        directory = job_directory(job, export)
        runtime = read_json(directory / "runtime.json")
        summary = read_json(directory / "summary.json")
        history = read_json(directory / "history.json")
        assumptions = read_json(directory / "assumptions.json")
        partition = read_json(directory / "swarm_partition.json")
        partitions[(job["seed"], job["scenario"])].append(partition)
        if [h["round"] for h in history] != list(range(1, len(history) + 1)):
            raise ValueError("Missing or duplicated round in terminal history")
        if runtime["source_sha256"] != manifest["source_sha256"]:
            raise ValueError("Runtime source fingerprint differs from frozen study")
        if runtime["dataset_sha256"] != manifest["dataset_sha256"]:
            raise ValueError("Runtime dataset fingerprint differs from frozen study")
        if job["config"]["channel"] == "trace" and runtime["trace_sha256"] != manifest["trace_sha256"]:
            raise ValueError("Runtime trace fingerprint differs from frozen study")
        if sum(d["num_samples"] for d in partition["drones"].values()) != 49_500:
            raise ValueError("Expected the same 49,500-image client pool as the ablation")
        if assumptions["trusted_root"]["total_samples"] != 500:
            raise ValueError("Expected a disjoint 500-image root reserve")
        row = run_metrics(job, chance=0.1, root=export)
        row.update(completed_rounds=summary["completed_rounds"],
                   divergence_round=summary["divergence_round"],
                   divergence_stage=summary["divergence_stage"],
                   gpu=runtime["gpu"], python=runtime["python"], torch=runtime["torch"],
                   numpy=runtime["numpy"], resumed_round=runtime["resumed_round"])
        rows.append(row)
        profiles[(runtime["gpu"], runtime["python"], runtime["torch"], runtime["numpy"])]+=1
        resumed += runtime["resumed_round"] > 0
        config = scientific_config(job["config"])
        protocols.append({"seed": job["seed"], "scenario": job["scenario"], "config": config})
        for name in ("config.json", "summary.json", "history.json", "runtime.json",
                     "assumptions.json", "swarm_partition.json", "final_model.pt"):
            checksums.append({"file": str((directory / name).relative_to(export)),
                              "sha256": sha256(directory / name)})
        for h in history:
            curves.append({"seed": job["seed"], "scenario": job["scenario"],
                           "aggregator": job["config"]["aggregator"], "round": h["round"],
                           "test_acc": h["test_acc"], "train_loss": h["train_loss"]})
    # Verify that the only scientific input difference within each pair is its rule.
    pairs = collections.defaultdict(list)
    for p in protocols:
        pairs[(p["seed"], p["scenario"])].append({k: v for k, v in p["config"].items()
                                                if k != "aggregator"})
    if any(len(v) != 2 or v[0] != v[1] for v in pairs.values()):
        raise ValueError("Scientific configurations are not paired")
    if any(len(v) != 2 or v[0] != v[1] for v in partitions.values()):
        raise ValueError("Client partition summaries are not paired")
    rows.sort(key=lambda r: (r["seed"], r["scenario"], r["aggregator"]))
    report = analyze_rows(rows)
    destination.mkdir(parents=True, exist_ok=True)
    for filename, values in (("base_paper_runs.csv", rows), ("evidence_checksums.csv", checksums)):
        with (destination / filename).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(values)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(curves[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(curves)
    (destination / "accuracy_history.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
    write_json(destination / "base_paper_analysis.json", report)
    write_json(destination / "study_protocol.json", {
        "source_sha256": manifest["source_sha256"], "dataset_sha256": manifest["dataset_sha256"],
        "trace_sha256": manifest["trace_sha256"], "seeds": manifest["seeds"], "jobs": protocols})
    write_json(destination / "ARTIFACT_VALIDATION.json", {
        "valid": True, "terminal_runs": len(rows), "missing_jobs": [],
        "scientific_pairs": len(pairs), "paired_partition_summaries": len(partitions),
        "client_images": 49_500, "reserved_root_images": 500,
        "export_manifest_sha256": sha256(export / "study_manifest.json"),
        "checksums_csv_sha256": sha256(destination / "evidence_checksums.csv"),
        "source_sha256": manifest["source_sha256"], "resumed_final_attempts": resumed,
        "runtime_profiles": [{"gpu": k[0], "python": k[1], "torch": k[2], "numpy": k[3],
                              "final_attempts": n} for k, n in sorted(profiles.items())],
        "scope": "Terminal records, exact frozen configurations, model presence, source/data fingerprints, "
                 "root reserve and paired scientific inputs checked against the completed export. "
                 "The coordinator separately validated all 240 result archives before export. "
                 "Runtime profiles describe final attempts; resumed work may span earlier attempts."})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, nargs="?")
    parser.add_argument("--csv", type=Path, help="Recompute estimates from the committed summary CSV")
    parser.add_argument("--out", type=Path, default=REPO / "results/base_paper_comparison")
    args = parser.parse_args()
    if bool(args.export) == bool(args.csv):
        parser.error("Supply either a completed export or --csv")
    if args.csv:
        result = analyze_rows(load_summary(args.csv))
        args.out.mkdir(parents=True, exist_ok=True)
        write_json(args.out / "base_paper_analysis.json", result)
    else:
        result = publish(args.export.resolve(), args.out.resolve())
    print(json.dumps({"terminal_runs": result["terminal_runs"], "outcomes": result["outcomes"]}, indent=2))


if __name__ == "__main__":
    main()
