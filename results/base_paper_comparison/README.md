# Completed base-paper erasure-rule comparison

The separate SwarmCompute follow-up completed on 8 November 2026 (IST). All **240**
planned runs have validated terminal artifacts: **157 succeeded and 83 diverged
numerically**. There are no missing jobs. This study does not change the design or
primary hypothesis of the original [720-run ablation](../CONTEXT_STUDY_FINAL.md).

The design is two rules (`bp_fresh`, `bp_reuse`) × four attack settings × three
channels × ten seeds (41–50), with 100 requested rounds per run. Both use the same
49,500-image client pool and reserve the same disjoint 500 root images; the erasure
rules do not use the root reference. The methods are packet-level, hierarchical
adaptations of Shirvanimoghaddam et al., *IEEE Communications Letters*, 26(6),
1293–1297, 2022, [doi:10.1109/LCOMM.2022.3167094](https://doi.org/10.1109/LCOMM.2022.3167094).
They are not exact reproductions of the paper's whole-upload erasure setting.

## Findings

| Rule | Successful | Numerically diverged | All-run final accuracy |
|---|---:|---:|---:|
| Fresh-only | 79/120 | 41/120 | 37.74% |
| Reuse-old | 78/120 | 42/120 | 36.42% |

Divergence contributes **10% chance accuracy**, not the last finite accuracy and
not an excluded observation. All 60 sign-flip runs diverged; the other 23
divergences were under IPM. There were no clean or ALIE divergences.

| Exploratory paired contrast: fresh-only minus reuse-old | Gain | 95% seed-bootstrap interval |
|---|---:|---:|
| Clean, ideal | 0.00 pp | [0.00, 0.00] pp |
| Clean, trace at 15 dB | +0.04 pp | [−0.17, +0.25] pp |
| Clean, trace at 5 dB | **+5.39 pp** | **[+4.11, +6.74] pp** |
| Attacked suite, trace at 5 dB | +3.40 pp | [+0.94, +6.60] pp |

Clean stressed-channel accuracy is 56.86% for fresh-only versus 51.47% for reuse-old.
The attacked stressed-channel means are 30.28% versus 26.87%, including divergence.
For the attacked suite, the three attacks are averaged **within each seed** before
resampling the ten independent seed pairs (10,000 percentile bootstrap replicates,
RNG seed 501927). These follow-up contrasts are exploratory, without multiplicity
adjustment. Full-precision estimates for all 12 cells and two pooled scopes are in
[`base_paper_analysis.json`](base_paper_analysis.json).

Fresh-only performed better under the tested stressed packet loss; neither rule
was Byzantine-robust under the tested sign-flip attack. These results concern this
non-IID CNN simulation and do not refute the original paper's honest-client
convergence theorem. The new rules appear as dashed, starred curves in the updated
paper/report accuracy figure. Cross-study comparisons against the A100 ablation are
descriptive, not hardware-controlled paired effects or speedup measurements.

## Evidence and execution provenance

| File | Purpose |
|---|---|
| `base_paper_runs.csv` | All 240 terminal run metrics, divergence flags and final-attempt software/GPU profiles |
| `accuracy_history.csv.gz` | Finite recorded per-round accuracy/loss; after divergence, analysis pads accuracy to chance through round 100 |
| `base_paper_analysis.json` | Reproducible all-run outcomes and paired fresh-only/reuse-old intervals |
| `study_protocol.json` | Frozen scientific configurations with machine-specific paths/execution fields removed |
| `ARTIFACT_VALIDATION.json` | Completeness, pairing, source/data fingerprints and final-attempt runtime profiles |
| `evidence_checksums.csv` | SHA-256 of the original exported config, history, summary, runtime, assumptions, partition and final model for each run |

The frozen training revision is `ad06055b8f3ee496c95852d54a3ac7ba695a7ae1`;
its scientific fingerprint is
`75c376ea0bb754a2063e3d4d9700a3552067216f1b9f7a4ad16fc214d63a7432`.
The CIFAR and trace hashes match those recorded for the earlier ablation. Its
training-source fingerprint differs, and this difference is retained explicitly.

Final attempts ran on an RTX 2060 (238) and GTX 1650 (2), with different PyTorch,
Python and NumPy versions recorded in the validation report. Fifty-seven final
attempts resumed from verified central checkpoints; their histories include earlier
completed rounds. A final-attempt hardware label does not describe every preceding
attempt of a resumed run. Checkpoints preserve state and RNGs, but cross-device
bitwise equivalence was not established.

Operational failures were recovered with unchanged scientific inputs: verified
checkpointed pauses were requeued, and the known Windows progress-file replacement
error received bounded retries. Failed attempts remain in the private coordinator
audit trail. Numerically divergent runs were never retried into successful outcomes.
The coordinator validated every terminal result archive before export; publication
additionally checks terminal histories, exact frozen configs, fingerprints and
all 120 paired partition summaries.

The full export, model weights and coordinator backup remain local. Raw datasets,
private worker-data ZIPs, credentials, worker identifiers, GPU UUIDs and user paths
are not part of this publication. Checksums identify the original artifacts without
publishing their contents. Repeating training requires authorized access to the
same prepared inputs and the frozen source revision.

## Reproduce the analysis and document assets

From the repository root, with the project's Python dependencies installed:

```bash
python scripts/analyze_base_paper.py --csv results/base_paper_comparison/base_paper_runs.csv
python scripts/make_paper_figures.py
```

The first command recomputes estimates from the committed compact data; the second
regenerates paper/report plots, tables and macros. To regenerate the compact
evidence directly from an authorized, completed SwarmCompute export:

```bash
python scripts/analyze_base_paper.py /path/to/completed-export
```

Build each document with `tectonic -X compile main.tex` inside `paper/` and
`report/`. No training or access to private coordinator state is needed to rebuild
the published figures and documents.
