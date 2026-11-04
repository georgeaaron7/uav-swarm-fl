import argparse
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from analyze_context_study import analyze, classify, interval
from fl.config import FLConfig
from run_context_study import build_jobs, completed, write_json


def args(tmp_path):
    return argparse.Namespace(
        seeds=[41, 42], attacks=["clean", "ipm"], conditions=["hfl_ideal", "hfl_trace_stress"],
        aggs=["ccra", "ccra_maskonly"], out_dir=tmp_path, device="cpu", threads=1,
        rounds=2, trace_path=Path("trace.npz"),
    )


def test_study_pairs_attacker_placement_and_changes_only_severity(tmp_path):
    options = args(tmp_path)
    options.attacks = ["ipm"]
    options.conditions = ["hfl_trace", "hfl_trace_stress"]
    jobs = build_jobs(options, tmp_path)
    assert len(jobs) == 8
    for seed in options.seeds:
        configs = [j["config"] for j in jobs if j["seed"] == seed]
        identities = {c["malicious_ids"] for c in configs}
        assert len(identities) == 1
        assert len(next(iter(identities)).split(",")) == 3
        assert all(c["noise_scale"] == 0 for c in configs)
        assert {c["trace_snr_reference_db"] for c in configs} == {5.0, 15.0}
        without_manipulations = [
            {k: v for k, v in c.items() if k not in {"name", "aggregator", "trace_snr_reference_db"}}
            for c in configs
        ]
        assert all(c == without_manipulations[0] for c in without_manipulations)
    assert build_jobs(options, tmp_path) == jobs


def save_run(root, seed, scenario, method, accuracy, diverged=False):
    cfg = asdict(FLConfig(
        seed=seed, name=f"{scenario}__{method}", out_dir=str(root / f"seed{seed}"),
        aggregator=method, rounds=2, eval_every=1,
    ))
    job = {"seed": seed, "scenario": scenario, "config": cfg}
    directory = Path(cfg["out_dir"]) / cfg["name"]
    directory.mkdir(parents=True)
    write_json(directory / "config.json", cfg)
    history = [{"round": 1, "test_acc": accuracy}]
    if not diverged:
        history.append({"round": 2, "test_acc": accuracy})
    write_json(directory / "history.json", history)
    write_json(directory / "summary.json", {
        "diverged": diverged, "completed_rounds": len(history),
        "divergence_round": 2 if diverged else None,
        "final_test_acc": None if diverged else accuracy,
        "mean_pdr": 0.9, "mean_latency_s": 0.1, "total_handovers": 1,
        "mean_honest_rejection_rate": 0.1, "mean_attacker_acceptance_rate": 0.2,
        "total_robustness_bound_violating_cells": 0,
    })
    (directory / "final_model.pt").write_bytes(b"checkpoint fixture")
    return job


def test_resume_requires_summary_matching_config_and_full_history(tmp_path):
    job = save_run(tmp_path, 41, "ipm_hfl_trace", "ccra", 0.5)
    directory = Path(job["config"]["out_dir"]) / job["config"]["name"]
    assert completed(job)
    job["config"]["rounds"] = 3
    assert not completed(job)
    job["config"]["rounds"] = 2
    (directory / "summary.json").unlink()
    assert not completed(job)
    failed = save_run(tmp_path, 42, "ipm_hfl_trace", "ccra", 0.5, True)
    assert completed(failed)  # divergence is terminal, not a job to retry


def test_analysis_uses_paired_interaction_and_chance_for_divergence(tmp_path):
    jobs = []
    for seed in (41, 42):
        for condition in ("hfl_trace", "hfl_trace_stress"):
            for method in ("ccra", "ccra_maskonly"):
                # base gain +0.10, stress gain +0.20 => interaction +0.10
                value = 0.4 if method == "ccra_maskonly" else (0.6 if condition.endswith("stress") else 0.5)
                jobs.append(save_run(tmp_path, seed, f"ipm_{condition}", method, value))
    write_json(tmp_path / "study_manifest.json", {"profile": "pilot", "seeds": [41, 42], "jobs": jobs})
    result = analyze(tmp_path)
    assert result["primary"][0]["mean_pp"] == pytest.approx(10.0)
    assert result["primary"][0]["n_seeds"] == 2
    assert np.allclose(result["primary"][0]["ci95_pp"], [10, 10])
    # A diverged run contributes 10%, regardless of its last finite 50% score.
    directory = Path(jobs[0]["config"]["out_dir"]) / jobs[0]["config"]["name"]
    (directory / "summary.json").unlink()
    with pytest.raises(ValueError, match="missing/incomplete"):
        analyze(tmp_path)
    partial = analyze(tmp_path, allow_incomplete=True)
    assert partial["terminal_runs"] == 7
    assert partial["primary"][0]["n_seeds"] == 1


def test_diverged_curve_uses_fixed_horizon(tmp_path):
    from analyze_context_study import run_metrics
    job = save_run(tmp_path, 41, "ipm_hfl_trace", "ccra", 0.5, True)
    metrics = run_metrics(job, 0.1)
    assert metrics["final_accuracy"] == 0.1
    assert metrics["mean_round_accuracy"] == pytest.approx(0.3)


def test_bootstrap_does_not_treat_scenarios_as_extra_seeds():
    result = interval([0.1, -0.1])
    assert result["n_seeds"] == 2
    assert result["mean_pp"] == 0.0
    assert result["ci95_pp"] == pytest.approx([-10, 10])
    assert interval([0.1])["ci95_pp"] is None


def test_practical_conclusion_requires_precision_and_replication():
    assert classify({"n_seeds": 10, "ci95_pp": [1.1, 2.0]}, 1.0) == "meaningful positive effect supported"
    assert classify({"n_seeds": 10, "ci95_pp": [-0.2, 0.3]}, 1.0) == "effect bounded within the predefined negligible range"
    assert classify({"n_seeds": 10, "ci95_pp": [-0.2, 2.0]}, 1.0).startswith("inconclusive")
    assert classify({"n_seeds": 2, "ci95_pp": [2, 3]}, 1.0) == "insufficient replication"


def test_copied_study_can_be_analyzed_without_rewriting_provenance(tmp_path):
    import shutil
    original = tmp_path / "remote"
    job = save_run(original, 41, "ipm_hfl_trace", "ccra", 0.5)
    write_json(original / "study_manifest.json", {"profile": "pilot", "seeds": [41], "jobs": [job]})
    copied = tmp_path / "local"
    shutil.copytree(original, copied)
    shutil.rmtree(original)
    assert not completed(job)
    assert completed(job, copied)
    assert analyze(copied)["terminal_runs"] == 1



def test_interrupted_job_resumes_from_checkpoint_or_restarts_clean(tmp_path, monkeypatch):
    import fl.checkpoint
    from run_context_study import job_directory, resume_arguments

    job = build_jobs(args(tmp_path), tmp_path)[0]
    directory = job_directory(job)
    assert resume_arguments(job) == []  # nothing on disk yet

    # Partial run without a usable checkpoint: cleared so run_baseline can start over.
    directory.mkdir(parents=True)
    write_json(directory / "config.json", job["config"])
    (directory / "metrics.csv").write_text("round\n1\n")
    assert resume_arguments(job) == []
    assert not directory.exists()

    # Partial run with a valid checkpoint for the same configuration: resumed from it.
    directory.mkdir(parents=True)
    write_json(directory / "config.json", job["config"])
    checkpoint = directory / "checkpoints" / "round_0001"
    monkeypatch.setattr(fl.checkpoint, "latest_valid", lambda root, expected=None: checkpoint)
    assert resume_arguments(job) == ["--resume-from", str(checkpoint)]
    assert directory.exists()

    # A different configuration on disk is never resumed.
    write_json(directory / "config.json", {**job["config"], "seed": 999})
    assert resume_arguments(job) == []
    assert not directory.exists()
