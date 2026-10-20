# A100 multi-seed benchmark artifacts

This directory contains the reviewed output of the full guide-requested
benchmark. Training completed on 20 October 2026 using an NVIDIA A100-SXM4-40GB
with PyTorch 2.11.0 and CUDA 12.8. The recorded training source is commit
`4a2e772`.

## Coverage and validation

- 18 scenarios: three channel/topology settings for clean training and each of
  five Byzantine attacks.
- 8 aggregators: FedAvg, CosAvg, Coordinate Median, Trimmed Mean, Multi-Krum,
  FLTrust, CCRA, and CCRA without channel context.
- 3 deterministic seeds: 41, 42, and 43.
- 30 requested rounds per run and 432 terminal runs in total.
- 432 valid `history.json` files, 432 valid `summary.json` files, and 432 finite
  last-known-good final models.
- 47 runs explicitly recorded numerical divergence. Diverged runs are excluded
  from metric averages and reported separately; their accuracy is never
  silently replaced with chance performance.
- No unexpected tracebacks, CUDA out-of-memory failures, or unrecorded
  non-finite results were found in the final audit.

## Included files

| File | Contents |
|---|---|
| `benchmark_runs.csv` | One row per seed/scenario/aggregator run (432 rows) |
| `benchmark_summary.csv` | Mean and sample SD across non-diverged seeds (144 scenario/aggregator rows) |
| `BENCHMARK_SUMMARY.md` | Human-readable version of the aggregate table |
| `accuracy_heatmap.png` | Final accuracy by scenario and aggregator |
| `defense_tradeoff.png` | Mean honest-rejection/attacker-acceptance trade-off with scenario SD bars |
| `benchmark_raw_results.tar.gz` | All configs, assumptions, partitions, logs, per-round metrics, histories, and summaries for the 432 runs |
| `MODEL_SHA256SUMS.txt` | SHA-256 hashes for all 864 local best/final checkpoints |
| `manifest.json` | Exact scenario, seed, round, aggregator, and trace-path matrix |
| `SOURCE_COMMIT` | Training implementation commit |
| `COMPLETE` | UTC completion marker |

The raw archive SHA-256 is
`1c88330b215fce8403659e990c8552eb906d3c2b0e10ca2acfb19acdf2ee643d`.
It deliberately excludes the 864 PyTorch checkpoint binaries (532 MB) because
they would make the Git repository unnecessarily large. Their hashes are
included for integrity checks, and the deterministic commands in the project
README reproduce them.

Extract the raw run artifacts without modifying this checkout:

```bash
mkdir -p /tmp/uav-benchmark-results
tar -xzf results/benchmark_gpu/benchmark_raw_results.tar.gz \
  -C /tmp/uav-benchmark-results
```

The CIFAR-10 cache and raw/prepared DeepSense Scenario 23 data are not
redistributed. Follow the main README to prepare those inputs.
