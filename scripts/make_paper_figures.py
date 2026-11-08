"""Build every figure, table, and number used by paper/ from the committed study CSV.

Input : results/context_study/context_runs.csv (720 terminal runs, see docs/CONTEXT_STUDY.md)
Output: paper/figures/*.pdf, paper/generated/numbers.tex, paper/generated/table_outcomes.tex,
        and copies of those (plus earlier-phase plots) in report/figures and report/generated

The paper never hard-codes a result: it reads the macros written here. Rerun after
any change to the study data:

    python scripts/make_paper_figures.py
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
ATTACKS = ["sign_flip", "alie", "ipm"]
CONDITIONS = ["hfl_ideal", "hfl_trace", "hfl_trace_stress"]
CONDITION_LABELS = ["Ideal", "Trace, 15 dB", "Trace, 5 dB"]
METHODS = ["fedavg", "median", "fltrust", "ccra_noctx", "ccra_maskonly", "ccra"]
METHOD_LABELS = {
    "fedavg": "FedAvg", "median": "Median", "fltrust": "FLTrust",
    "ccra_noctx": "No-context", "ccra_maskonly": "Mask-only", "ccra": "CCRA (full)",
    "bp_fresh": "Fresh-only*", "bp_reuse": "Reuse-old*",
}
# Validated categorical order (dataviz reference palette), fixed per method.
COLORS = {
    "fedavg": "#2a78d6", "median": "#eb6834", "fltrust": "#1baf7a",
    "ccra_noctx": "#eda100", "ccra_maskonly": "#e87ba4", "ccra": "#008300",
    "bp_fresh": "#7552a1", "bp_reuse": "#7a6353",
}
MARKERS = {"fedavg": "o", "median": "s", "fltrust": "^",
           "ccra_noctx": "v", "ccra_maskonly": "D", "ccra": "P",
           "bp_fresh": "X", "bp_reuse": "h"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
CHANCE = 0.10
BOOTSTRAP = 10_000


def load(path: Path, expected=720) -> list[dict]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for r in rows:
        r["seed"] = int(r["seed"])
        r["diverged"] = r["diverged"] == "True"
        # Diverged runs are scored at chance, matching analyze_context_study.py.
        r["acc"] = CHANCE if r["diverged"] else float(r["final_accuracy"])
        for key in ("mean_pdr", "honest_rejection", "attacker_acceptance"):
            r[key] = float(r[key])
    if len(rows) != expected:
        raise SystemExit(f"expected {expected} runs, found {len(rows)}")
    return rows


def index(rows):
    table = {}
    for r in rows:
        attack, condition = r["scenario"].split("_hfl_")
        table[(r["seed"], attack, "hfl_" + condition, r["aggregator"])] = r
    return table


def seed_means(table, seeds, conditions, methods, key="acc", attacks=ATTACKS):
    """Per-seed mean over the attack suite, for one method or a paired difference."""
    out = []
    for s in seeds:
        vals = []
        for a in attacks:
            for c in conditions:
                if isinstance(methods, tuple):
                    m1, m2 = methods
                    vals.append(table[(s, a, c, m1)][key] - table[(s, a, c, m2)][key])
                else:
                    vals.append(table[(s, a, c, methods)][key])
        out.append(np.mean(vals))
    return np.array(out)


def bootstrap_ci(values: np.ndarray, rng) -> tuple[float, float]:
    idx = rng.integers(0, len(values), size=(BOOTSTRAP, len(values)))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def style():
    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix", "font.size": 8, "axes.labelsize": 8,
        "axes.titlesize": 8, "legend.fontsize": 7, "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.6, "axes.axisbelow": True, "pdf.fonttype": 42,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def save(fig, out: Path):
    """PDF for LaTeX, PNG for the README and slides.

    Timestamps are omitted so rerunning the script leaves unchanged figures
    byte-identical in Git.
    """
    fig.savefig(out, metadata={"CreationDate": None})
    fig.savefig(out.with_suffix(".png"), dpi=220, metadata={"Software": None})
    plt.close(fig)


def fig_accuracy_vs_channel(table, seeds, rng, out: Path, base_table=None):
    fig, ax = plt.subplots(figsize=(3.5, 2.35))
    x = np.arange(len(CONDITIONS))
    for m in METHODS + (["bp_fresh", "bp_reuse"] if base_table else []):
        # Preserve every existing ablation interval and RNG draw. The follow-up
        # methods get their own independent bootstrap stream.
        data = base_table if m.startswith("bp_") else table
        stream = np.random.default_rng(20261108) if m.startswith("bp_") else rng
        means, lo, hi = [], [], []
        for c in CONDITIONS:
            v = seed_means(data, seeds, [c], m) * 100
            l, h = bootstrap_ci(v, stream)
            means.append(v.mean()); lo.append(v.mean() - l); hi.append(h - v.mean())
        ax.errorbar(x, means, yerr=[lo, hi], color=COLORS[m], marker=MARKERS[m],
                    markersize=4.5, linewidth=1.4, capsize=2, elinewidth=0.8,
                    markeredgecolor="white", markeredgewidth=0.6,
                    linestyle="--" if m.startswith("bp_") else "-",
                    label=METHOD_LABELS[m])
    ax.set_xticks(x, CONDITION_LABELS)
    ax.set_xlim(-0.25, len(CONDITIONS) - 0.75)
    ax.set_ylabel("Final test accuracy under attack (%)")
    ax.legend(ncol=4 if base_table else 3, fontsize=6.6 if base_table else 7,
              frameon=False, loc="lower left", bbox_to_anchor=(-0.04, 1.0),
              handlelength=1.4, columnspacing=0.7)
    save(fig, out)


CONTRASTS = [
    ("Telemetry\n(CCRA $-$ mask-only)", ("ccra", "ccra_maskonly")),
    ("Packet mask\n(mask-only $-$ no-ctx)", ("ccra_maskonly", "ccra_noctx")),
    ("Both\n(CCRA $-$ no-ctx)", ("ccra", "ccra_noctx")),
]


def contrast_estimates(table, seeds, rng):
    est = {}
    for _, pair in CONTRASTS:
        for c in CONDITIONS:
            v = seed_means(table, seeds, [c], pair) * 100
            est[(pair, c)] = (float(v.mean()), *bootstrap_ci(v, rng))
    return est


def fig_ablation(est, out: Path):
    fig, ax = plt.subplots(figsize=(3.5, 2.3))
    offsets = [-0.22, 0.0, 0.22]
    shades = ["#9ec5f0", "#5a9be2", "#1d5fae"]  # one hue, light -> dark = milder -> harsher channel
    for i, (label, pair) in enumerate(CONTRASTS):
        for j, c in enumerate(CONDITIONS):
            mean, lo, hi = est[(pair, c)]
            y = i + offsets[j]
            ax.plot([lo, hi], [y, y], color=shades[j], linewidth=2, solid_capstyle="round")
            ax.plot(mean, y, "o", color=shades[j], markersize=5,
                    markeredgecolor="white", markeredgewidth=0.6,
                    label=CONDITION_LABELS[j] if i == 0 else None)
    ax.axvspan(-1, 1, color=GRID, alpha=0.6, linewidth=0)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.set_yticks(range(len(CONTRASTS)), [c[0] for c in CONTRASTS])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Paired accuracy gain under attack (pp), 95% CI")
    ax.legend(frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(-0.02, 1.0),
              handletextpad=0.2, columnspacing=0.8)
    save(fig, out)


GATE_METHODS = ["fltrust", "ccra_noctx", "ccra_maskonly", "ccra"]


def gate_rates(table, seeds):
    rates = {}
    for m in GATE_METHODS:
        for key in ("honest_rejection", "attacker_acceptance"):
            rates[(m, key)] = float(
                seed_means(table, seeds, ["hfl_trace_stress"], m, key=key).mean() * 100)
    return rates


def fig_gate(rates, out: Path):
    fig, axes = plt.subplots(1, 2, figsize=(3.5, 1.75), sharey=True)
    titles = {"honest_rejection": "Honest updates rejected (%)",
              "attacker_acceptance": "Attacker updates accepted (%)"}
    y = np.arange(len(GATE_METHODS))
    for ax, key in zip(axes, titles):
        vals = [rates[(m, key)] for m in GATE_METHODS]
        ax.barh(y, vals, height=0.62, color=[COLORS[m] for m in GATE_METHODS],
                edgecolor="white", linewidth=1)
        for yi, v in zip(y, vals):
            ax.text(v + 0.8, yi, f"{v:.1f}", va="center", fontsize=7, color=INK)
        ax.set_title(titles[key], color=INK)
        ax.set_xlim(0, max(vals) * 1.3 + 2)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, [METHOD_LABELS[m] for m in GATE_METHODS])
    axes[0].invert_yaxis()
    fig.tight_layout(w_pad=0.6)
    save(fig, out)


def outcomes(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["aggregator"]].append(r)
    return {m: (len(v), sum(r["diverged"] for r in v), 100 * np.mean([r["acc"] for r in v]))
            for m, v in by.items()}


def write_table(out_rows, table, seeds, path: Path):
    lines = [
        r"\begin{tabular}{@{}lccc@{}}",
        r"\toprule",
        r"Method & Diverged & All runs (\%) & Attacked, 5\,dB (\%) \\",
        r"\midrule",
    ]
    stress = {m: seed_means(table, seeds, ["hfl_trace_stress"], m).mean() * 100 for m in METHODS}
    best_all = max(METHODS, key=lambda m: out_rows[m][2])
    best_stress = max(METHODS, key=lambda m: stress[m])

    def cell(value, bold):
        return rf"\textbf{{{value:.1f}}}" if bold else f"{value:.1f}"

    for m in METHODS:
        n, div, acc = out_rows[m]
        lines.append(f"{METHOD_LABELS[m]} & {div}/{n} & {cell(acc, m == best_all)} & "
                     f"{cell(stress[m], m == best_stress)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")


def tex_number(name: str, value: float, digits: int = 1) -> str:
    return f"\\newcommand{{\\{name}}}{{{value:.{digits}f}}}"


def write_numbers(table, seeds, est, rates, out_rows, rows, rng, path: Path):
    def pdr(condition):
        return 100 * np.mean([r["mean_pdr"] for r in rows if r["scenario"].endswith(condition)])

    def versus_fltrust(condition):
        # Exploratory: not part of the prespecified analysis in docs/CONTEXT_STUDY.md.
        v = seed_means(table, seeds, [condition], ("ccra_maskonly", "fltrust")) * 100
        return (float(v.mean()), *bootstrap_ci(v, rng))

    tel = est[(("ccra", "ccra_maskonly"), "hfl_trace_stress")]
    msk = est[(("ccra_maskonly", "ccra_noctx"), "hfl_trace_stress")]
    vft = versus_fltrust("hfl_trace")
    vfs = versus_fltrust("hfl_trace_stress")
    # Prespecified primary estimand (docs/CONTEXT_STUDY.md): telemetry effect at 5 dB
    # minus the same effect on the identical 15 dB trace, averaged over attacks per seed.
    pair = ("ccra", "ccra_maskonly")
    primary = (seed_means(table, seeds, ["hfl_trace_stress"], pair)
               - seed_means(table, seeds, ["hfl_trace"], pair)) * 100
    prim = (float(primary.mean()), *bootstrap_ci(primary, rng))
    acc5 = {m: seed_means(table, seeds, ["hfl_trace_stress"], m).mean() * 100 for m in METHODS}
    lines = [
        "% Generated by scripts/make_paper_figures.py -- do not edit by hand.",
        f"\\newcommand{{\\NumRuns}}{{{len(rows)}}}",
        f"\\newcommand{{\\NumSeeds}}{{{len(seeds)}}}",
        tex_number("PdrTrace", pdr("_hfl_trace")),
        tex_number("PdrStress", pdr("_hfl_trace_stress")),
        tex_number("TelGain", tel[0]), tex_number("TelLo", tel[1]), tex_number("TelHi", tel[2]),
        tex_number("MaskGain", msk[0]), tex_number("MaskLo", msk[1]), tex_number("MaskHi", msk[2]),
        tex_number("PrimGain", prim[0]), tex_number("PrimLo", prim[1]), tex_number("PrimHi", prim[2]),
        tex_number("AccCcraStress", acc5["ccra"]),
        tex_number("AccMaskStress", acc5["ccra_maskonly"]),
        tex_number("AccNoctxStress", acc5["ccra_noctx"]),
        tex_number("AccFltrustStress", acc5["fltrust"]),
        tex_number("RejCcra", rates[("ccra", "honest_rejection")]),
        tex_number("RejMask", rates[("ccra_maskonly", "honest_rejection")]),
        tex_number("AccptCcra", rates[("ccra", "attacker_acceptance")]),
        tex_number("AccptMask", rates[("ccra_maskonly", "attacker_acceptance")]),
        tex_number("RejFltrust", rates[("fltrust", "honest_rejection")]),
        tex_number("VsFltTrace", vft[0]), tex_number("VsFltTraceLo", vft[1]),
        tex_number("VsFltTraceHi", vft[2]),
        tex_number("VsFltStress", vfs[0]), tex_number("VsFltStressLo", vfs[1]),
        tex_number("VsFltStressHi", vfs[2]),
        f"\\newcommand{{\\DivFedavg}}{{{out_rows['fedavg'][1]}}}",
        f"\\newcommand{{\\DivMedian}}{{{out_rows['median'][1]}}}",
        tex_number("AllMask", out_rows["ccra_maskonly"][2]),
        tex_number("AllFedavg", out_rows["fedavg"][2]),
    ]
    path.write_text("\n".join(lines) + "\n")


ATTACK_LABELS = {"clean": "No attack", "sign_flip": "Sign flip", "alie": "ALIE", "ipm": "IPM"}


def write_attack_table(table, seeds, path: Path):
    """Mean final accuracy per attack, method and channel; best per column block in bold."""
    lines = [
        r"\begin{tabular}{@{}llccc@{}}",
        r"\toprule",
        r"Attack & Method & " + " & ".join(CONDITION_LABELS) + r" \\",
        r"\midrule",
    ]
    for attack, label in ATTACK_LABELS.items():
        acc = {(m, c): seed_means(table, seeds, [c], m, attacks=[attack]).mean() * 100
               for m in METHODS for c in CONDITIONS}
        best = {c: max(METHODS, key=lambda m: acc[(m, c)]) for c in CONDITIONS}
        for i, m in enumerate(METHODS):
            cells = [rf"\textbf{{{acc[(m, c)]:.1f}}}" if best[c] == m else f"{acc[(m, c)]:.1f}"
                     for c in CONDITIONS]
            head = label if i == 0 else ""
            lines.append(f"{head} & {METHOD_LABELS[m]} & " + " & ".join(cells) + r" \\")
        lines.append(r"\midrule" if attack != "ipm" else r"\bottomrule")
    lines.append(r"\end{tabular}")
    path.write_text("\n".join(lines) + "\n")


def write_base_assets(analysis, out):
    """Keep follow-up numbers separate from the prespecified ablation macros."""
    estimates = {r["scope"]: r for r in analysis["estimates"]}
    clean = estimates["clean_hfl_trace_stress"]
    attacked = estimates["attacked_stress"]
    lines = ["% Generated by scripts/make_paper_figures.py; do not edit.",
             r"\newcommand{\BpNumRuns}{240}", r"\newcommand{\NumCombinedRuns}{960}"]
    for method, label in [("bp_fresh", "Fresh"), ("bp_reuse", "Reuse")]:
        row = analysis["outcomes"][method]
        lines += [f"\\newcommand{{\\BpDiv{label}}}{{{row['diverged']}}}",
                  tex_number("BpAll" + label, row["all_run_final_accuracy_pct"], 2),
                  tex_number("BpCleanStress" + label, clean["accuracy_pct"][method], 2),
                  tex_number("BpAttackStress" + label, attacked["accuracy_pct"][method], 2)]
    for prefix, row in [("BpClean", clean), ("BpAttack", attacked)]:
        lines += [tex_number(prefix + "Gain", row["mean_pp"], 2),
                  tex_number(prefix + "Lo", row["ci95_pp"][0], 2),
                  tex_number(prefix + "Hi", row["ci95_pp"][1], 2)]
    (out / "generated/base_paper_numbers.tex").write_text("\n".join(lines) + "\n")
    lines = [r"\begin{tabular}{@{}llrrr@{}}", r"\toprule",
             r"Attack & Channel & Fresh (\%) & Reuse (\%) & Fresh $-$ reuse: pp [95\% CI] \\",
             r"\midrule"]
    channel_labels = {"hfl_ideal": "Ideal", "hfl_trace": r"15\,dB", "hfl_trace_stress": r"5\,dB"}
    for attack, label in ATTACK_LABELS.items():
        for i, condition in enumerate(CONDITIONS):
            row = estimates[f"{attack}_{condition}"]
            low, high = row["ci95_pp"]
            lines.append(f"{label if i == 0 else ''} & {channel_labels[condition]} & "
                         f"{row['accuracy_pct']['bp_fresh']:.2f} & {row['accuracy_pct']['bp_reuse']:.2f} & "
                         f"${row['mean_pp']:+.2f}\\;[{low:+.2f},\\,{high:+.2f}]$ \\\\")
        lines.append(r"\midrule" if attack != "ipm" else r"\bottomrule")
    lines.append(r"\end{tabular}")
    (out / "generated/table_base_paper.tex").write_text("\n".join(lines) + "\n")


def per_curves():
    """Our logistic packet-error curve against the base paper's normal approximation.

    The base paper (its Eq. 1) gives the packet error rate of a k-bit packet sent in n
    channel uses at SNR g as Q((n log2(1+g) - k + log2 n) / sqrt(n V(g))), with
    V(g) = (1 - (1+g)^-2) log2(e)^2. With k = our packet size and the code rate whose
    capacity threshold is our 3 dB midpoint, that curve is a near-vertical waterfall.
    Averaging it over a Gaussian SNR spread (in dB) within the round reproduces the
    gentler logistic curve; the spread is fitted here, not assumed.
    """
    import sys
    from math import erfc

    sys.path.insert(0, str(REPO))
    from fl.config import FLConfig

    cfg = FLConfig()
    k = cfg.packet_size * cfg.bits_per_parameter
    rate = float(np.log2(1 + 10 ** (cfg.per_threshold_db / 10)))
    n = k / rate
    q = np.vectorize(lambda x: 0.5 * erfc(x / np.sqrt(2)))

    def normal_approx(g_db):
        g = 10 ** (np.asarray(g_db, dtype=float) / 10)
        dispersion = (1 - (1 + g) ** -2) * np.log2(np.e) ** 2
        return q((n * np.log2(1 + g) - k + np.log2(n)) / np.sqrt(n * dispersion))

    def logistic(g_db):
        return 1 / (1 + np.exp(cfg.per_slope * (np.asarray(g_db) - cfg.per_threshold_db)))

    def averaged(g_db, spread):
        offsets = np.linspace(-5 * spread, 5 * spread, 401)
        weights = np.exp(-0.5 * (offsets / spread) ** 2)
        weights /= weights.sum()
        return np.array([(normal_approx(g + offsets) * weights).sum() for g in g_db])

    snr = np.linspace(-6, 12, 361)
    target = logistic(snr)
    spread = min(np.arange(1.0, 3.01, 0.05),
                 key=lambda s: float(np.sqrt(np.mean((averaged(snr, s) - target) ** 2))))
    fine = np.linspace(cfg.per_threshold_db - 1, cfg.per_threshold_db + 1, 4001)
    sharp = normal_approx(fine)
    waterfall = fine[np.argmin(abs(sharp - 0.1))] - fine[np.argmin(abs(sharp - 0.9))]
    return {"snr": snr, "logistic": target, "sharp": normal_approx(snr),
            "averaged": averaged(snr, spread), "spread": float(spread),
            "max_gap": float(np.max(np.abs(averaged(snr, spread) - target))),
            "bits": k, "rate": rate, "uses": n, "waterfall": float(waterfall),
            "threshold": cfg.per_threshold_db, "slope": cfg.per_slope}


def fig_per_curve(curves, out: Path):
    fig, ax = plt.subplots(figsize=(3.5, 2.1))
    ax.plot(curves["snr"], curves["sharp"], color=MUTED, linewidth=1.2, linestyle="--",
            label="Base-paper normal approx.")
    ax.plot(curves["snr"], curves["averaged"], color=COLORS["bp_fresh"], linewidth=2.4, alpha=0.55,
            label=f"Same, averaged over {curves['spread']:.1f} dB spread")
    ax.plot(curves["snr"], curves["logistic"], color=COLORS["fedavg"], linewidth=1.4,
            label=f"Our logistic ($a$={curves['slope']:g}, {curves['threshold']:g} dB)")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("Packet error rate")
    ax.set_ylim(-0.02, 1.02)
    # Right of 5 dB every curve is near zero, so the legend sits clear of them there.
    ax.legend(frameon=False, fontsize=6.5, loc="upper left", bbox_to_anchor=(0.6, 0.85))
    fig.tight_layout()
    save(fig, out)


def write_channel_numbers(curves, path: Path):
    lines = ["% Generated by scripts/make_paper_figures.py; do not edit.",
             f"\\newcommand{{\\PerBits}}{{{curves['bits']:,}}}".replace(",", "{,}"),
             tex_number("PerRate", curves["rate"], 2),
             f"\\newcommand{{\\PerUses}}{{{round(curves['uses']):,}}}".replace(",", "{,}"),
             tex_number("PerWaterfall", curves["waterfall"], 2),
             tex_number("PerSpread", curves["spread"]),
             tex_number("PerMaxGap", 100 * curves["max_gap"])]
    path.write_text("\n".join(lines) + "\n")


def write_cross_study(table, base_table, seeds, out):
    """Mask-only versus the base paper's better rule, and the hardware cross-check.

    Both studies share seeds, data partitions and attacker identities, so the
    differences are paired by seed; they are still cross-study and exploratory.
    A separate RNG stream leaves every other macro unchanged.
    """
    rng = np.random.default_rng(20261109)
    lines = []
    for label, attacks in [("Attack", ATTACKS), ("Clean", ["clean"])]:
        diff = np.array([
            np.mean([table[(s, a, "hfl_trace_stress", "ccra_maskonly")]["acc"]
                     - base_table[(s, a, "hfl_trace_stress", "bp_fresh")]["acc"] for a in attacks])
            for s in seeds]) * 100
        lo, hi = bootstrap_ci(diff, rng)
        lines += [tex_number(f"VsBp{label}", float(diff.mean())),
                  tex_number(f"VsBp{label}Lo", lo), tex_number(f"VsBp{label}Hi", hi)]
    clean_mask = np.mean([table[(s, "clean", "hfl_trace_stress", "ccra_maskonly")]["acc"] for s in seeds])
    lines.append(tex_number("AccMaskCleanStress", 100 * float(clean_mask)))
    # On the ideal channel nothing is erased, so fresh-only reduces to FedAvg:
    # any difference between the two studies there comes from hardware and software.
    gaps, same_divergence = [], True
    for s in seeds:
        for a in ["clean"] + ATTACKS:
            ours = table[(s, a, "hfl_ideal", "fedavg")]
            theirs = base_table[(s, a, "hfl_ideal", "bp_fresh")]
            same_divergence &= ours["diverged"] == theirs["diverged"]
            if not ours["diverged"] and not theirs["diverged"]:
                gaps.append(abs(ours["acc"] - theirs["acc"]) * 100)
    if not same_divergence:
        raise ValueError("ideal-channel divergence differs between studies; revisit the cross-check")
    lines += [tex_number("XcheckMax", max(gaps)), tex_number("XcheckMean", float(np.mean(gaps)), 2),
              f"\\newcommand{{\\XcheckRuns}}{{{len(gaps)}}}"]
    with (out / "generated/base_paper_numbers.tex").open("a") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--csv", type=Path, default=REPO / "results/context_study/context_runs.csv")
    p.add_argument("--out", type=Path, default=REPO / "paper")
    p.add_argument("--base-csv", type=Path,
                   default=REPO / "results/base_paper_comparison/base_paper_runs.csv")
    p.add_argument("--report", type=Path, default=REPO / "report",
                   help="also copy figures and macros here (pass an empty string to skip)")
    args = p.parse_args(argv)

    rows = load(args.csv)
    base_rows = load(args.base_csv, expected=240)
    base_table = index(base_rows)
    if {r["seed"] for r in base_rows} != {r["seed"] for r in rows}:
        raise ValueError("Follow-up and ablation must use the same seed labels")
    table = index(rows)
    seeds = sorted({r["seed"] for r in rows})
    rng = np.random.default_rng(20261103)
    (args.out / "figures").mkdir(parents=True, exist_ok=True)
    (args.out / "generated").mkdir(parents=True, exist_ok=True)

    style()
    fig_accuracy_vs_channel(table, seeds, rng, args.out / "figures/accuracy_vs_channel.pdf", base_table)
    est = contrast_estimates(table, seeds, rng)
    fig_ablation(est, args.out / "figures/ablation_contrasts.pdf")
    rates = gate_rates(table, seeds)
    fig_gate(rates, args.out / "figures/gate_rates.pdf")
    out_rows = outcomes(rows)
    write_table(out_rows, table, seeds, args.out / "generated/table_outcomes.tex")
    write_numbers(table, seeds, est, rates, out_rows, rows, rng, args.out / "generated/numbers.tex")
    write_attack_table(table, seeds, args.out / "generated/table_per_attack.tex")
    analysis = json.loads((args.base_csv.parent / "base_paper_analysis.json").read_text())
    write_base_assets(analysis, args.out)
    write_cross_study(table, base_table, seeds, args.out)
    curves = per_curves()
    fig_per_curve(curves, args.out / "figures/per_curve.pdf")
    write_channel_numbers(curves, args.out / "generated/channel_numbers.tex")

    for (label, pair), c in [(CONTRASTS[0], "hfl_trace_stress"), (CONTRASTS[1], "hfl_trace_stress")]:
        mean, lo, hi = est[(pair, c)]
        print(f"{label.splitlines()[0]:12s} @5dB: {mean:+.2f} pp [{lo:+.2f}, {hi:+.2f}]")
    print(f"wrote figures and macros to {args.out}")
    if args.report and str(args.report) not in ("", "."):
        sync_report(args.out, args.report)
        print(f"copied report assets to {args.report}")


# Earlier-phase plots shown in the report (produced by plot_results.py / plot_compare.py).
HISTORICAL_FIGURES = {
    "results/baseline_curves.png": "baseline_curves.png",
    "results/compare/final_accuracy_bars.png": "prelim_accuracy_bars.png",
    "results/compare/weight_share_attack_lossy.png": "prelim_weight_share.png",
}


def sync_report(paper: Path, report: Path):
    """Copy figures and macros so report/ stays self-contained for an Overleaf upload."""
    import shutil

    (report / "figures").mkdir(parents=True, exist_ok=True)
    (report / "generated").mkdir(parents=True, exist_ok=True)
    for src in (paper / "figures").glob("*.pdf"):
        shutil.copy2(src, report / "figures" / src.name)
    for src in (paper / "generated").glob("*.tex"):
        shutil.copy2(src, report / "generated" / src.name)
    for src, name in HISTORICAL_FIGURES.items():
        shutil.copy2(REPO / src, report / "figures" / name)


if __name__ == "__main__":
    main()
