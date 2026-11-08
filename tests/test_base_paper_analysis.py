import copy
import itertools
import json

import pytest

from scripts.analyze_base_paper import ATTACKS, CONDITIONS, METHODS, analyze_rows, publish


def matrix():
    return [{"seed": seed, "scenario": f"{attack}_{channel}", "aggregator": method,
             "diverged": False, "final_accuracy": 0.6 if method == "bp_fresh" else 0.5}
            for seed, attack, channel, method in itertools.product((41, 42), ATTACKS, CONDITIONS, METHODS)]


def test_followup_uses_paired_seeds_and_does_not_inflate_replication():
    report = analyze_rows(matrix(), seeds=(41, 42))
    assert report["terminal_runs"] == 48
    pooled = next(e for e in report["estimates"] if e["scope"] == "attacked_stress")
    assert pooled["n_seeds"] == 2  # not six independent attack/seed cells
    assert pooled["mean_pp"] == pytest.approx(10)
    assert pooled["ci95_pp"] == pytest.approx([10, 10])
    assert analyze_rows(matrix(), seeds=(41, 42)) == report


def test_divergence_is_retained_in_all_run_estimates():
    data = matrix()
    for r in data:
        if r["aggregator"] == "bp_fresh" and r["scenario"].startswith("sign_flip"):
            r.update(diverged=True, final_accuracy=0.1)
    report = analyze_rows(data, seeds=(41, 42))
    assert report["outcomes"]["bp_fresh"]["runs"] == 24
    assert report["outcomes"]["bp_fresh"]["diverged"] == 6
    assert report["outcomes"]["bp_fresh"]["all_run_final_accuracy_pct"] == pytest.approx(47.5)
    data[0].update(diverged=True, final_accuracy=0.99)
    with pytest.raises(ValueError, match="chance"):
        analyze_rows(data, seeds=(41, 42))


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra"])
def test_incomplete_or_duplicated_factorial_design_is_rejected(change):
    data = matrix()
    if change == "missing":
        data.pop()
    elif change == "duplicate":
        data[-1] = copy.deepcopy(data[0])
    else:
        data.append({**data[0], "aggregator": "ccra"})
    with pytest.raises(ValueError, match="exactly one"):
        analyze_rows(data, seeds=(41, 42))


def test_export_cannot_be_published_without_complete_terminal_evidence(tmp_path):
    (tmp_path / "study_manifest.json").write_text(json.dumps({"jobs": []}))
    with pytest.raises(ValueError, match="complete 240-run"):
        publish(tmp_path, tmp_path / "published")
    assert not (tmp_path / "published").exists()
