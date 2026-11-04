# Source audit and implementation status

Audited starting revision: `8fb0bff` on `study/context-ablation`; implementation branch `feature/swarmcompute`.

The simulator has global and edge models, server Generator state, CCRA trust, delivery counters, topology positions/altitudes/BS layout/association/pending handovers/counts, and jammer placement. These are serialized explicitly. Clients retain poisoned labels, malicious metadata and telemetry. Images and immutable traces are rebuilt from fingerprinted data. Optimizers are newly constructed inside every local training call and are deliberately not persisted. Python, NumPy global, server Generator, Torch CPU and CUDA RNG states are restored. Best model, known-good model, authoritative completed-round history and training time are retained.

This checkout and the inspected local Git history contain neither `bp_fresh`, `bp_reuse` nor `ErasureReuse`. Available study methods are `fedavg`, `median`, `fltrust`, `ccra_noctx`, `ccra_maskonly`, `ccra`; the simulator additionally supports `cosavg`, `trimmed_mean`, `krum`, `multi_krum`. The user authorized proceeding with the inspected algorithms. No invented base-paper alias has been introduced. Any two supported methods across four attacks, three conditions and ten seeds produce 240 jobs using the existing `build_jobs()`. This does **not** establish that those methods are the requested absent base-paper algorithms.

Historical `results/`, figures, reports and scientific configurations are preserved. Distributed execution uses separate attempt directories. Existing completed results and existing export destinations are never overwritten.

## Evidence and limits

Tests include exact CPU trajectory restoration (100-round CCRA interrupted at 40), RNG/integrity/fallback checks, transaction concurrency, authenticated ownership, lease expiry, coordinator database reopen, stale-attempt fencing, bounded/path-safe uploads and real HTTP/worker/subprocess pilot execution. See the test suite and `ACCEPTANCE.md` for the current evidence and manual hardware checklist.

No claim of bitwise cross-GPU equivalence, Windows/Linux NVIDIA acceptance, or physical LAN acceptance can be established on this macOS coordinator alone. Record and compare target-machine results before production use. A CPU test is a pipeline test, not a study result or GPU benchmark.
