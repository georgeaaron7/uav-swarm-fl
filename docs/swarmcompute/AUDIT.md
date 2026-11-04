# Source audit and implementation status

Audited starting revision: `8fb0bff` on `study/context-ablation`; implementation branch `feature/swarmcompute`.

The simulator has global and edge models, server Generator state, CCRA trust, delivery counters, topology positions/altitudes/BS layout/association/pending handovers/counts, and jammer placement. These are serialized explicitly. Clients retain poisoned labels, malicious metadata and telemetry. Images and immutable traces are rebuilt from fingerprinted data. Optimizers are newly constructed inside every local training call and are deliberately not persisted. Python, NumPy global, server Generator, Torch CPU and CUDA RNG states are restored. Best model, known-good model, authoritative completed-round history and training time are retained.

The initial audit at `8fb0bff` lacked `bp_fresh`, `bp_reuse` and `ErasureReuse`. A subsequent fetch found upstream PR #6 merged at `dab038e`; that main revision is now merged into this branch. Both actual base-paper implementations are reused without aliases. `ErasureReuse.params` and `known` have explicit checkpoint serialization. Its 100-round interrupted/resumed trajectory is tested. The base-paper pair remains a separate 240-job study, preserving upstream's guard against mixing it into the six-method context study.

Historical `results/`, figures, reports and scientific configurations are preserved. Distributed execution uses separate attempt directories. Existing completed results and existing export destinations are never overwritten.

## Evidence and limits

Tests include exact CPU trajectory restoration (100-round CCRA interrupted at 40), RNG/integrity/fallback checks, transaction concurrency, authenticated ownership, lease expiry, coordinator database reopen, stale-attempt fencing, bounded/path-safe uploads and real HTTP/worker/subprocess pilot execution. See the test suite and `ACCEPTANCE.md` for the current evidence and manual hardware checklist.

No claim of bitwise cross-GPU equivalence, Windows/Linux NVIDIA acceptance, or physical LAN acceptance can be established on this macOS coordinator alone. Record and compare target-machine results before production use. A CPU test is a pipeline test, not a study result or GPU benchmark.
