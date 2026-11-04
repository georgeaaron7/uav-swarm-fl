# Checkpointing and scientific recovery

Checkpoint directories contain `state.pt`, `metadata.json`, and `COMPLETE`. A temporary directory is written first; the state is flushed/fsynced, hashed and safely reloaded, then the directory is atomically renamed. An incomplete directory is never selected as a recovery point. Tensors are saved on CPU; the format contains tensors/primitives and explicitly encoded NumPy arrays, never arbitrary live Python objects. Loading uses `weights_only=True`, `map_location="cpu"`.

Every checkpoint contains models for the global server and all BSs; best accuracy and model; last valid global model; complete round history; round number; CCRA trust; topology positions/altitudes/BS layout/serving/pending/handover counters; jammer and jammed clients; delivery counters; poisoned client labels and persistent metadata; server Generator state; and Python/NumPy/Torch/CUDA RNG state. Immutable input images/traces are reconstructed from hash-checked source data. Client optimizers are deliberately not persisted because each local training invocation constructs a new optimizer.

The upstream base-paper algorithms are integrated: `ErasureFresh` exposes empty state; `ErasureReuse` preserves its per-client absolute parameter cache and known-coordinate masks. A 100-round reuse run interrupted at round 40 resumes with identical scientific state in the tested CPU environment. Future stateful aggregators must implement explicit serialization.

```bash
python run_baseline.py --resume-from /path/round_0040 \
  --checkpoint-every-rounds 10 --name my-experiment --out-dir /fresh/attempt \
  [the identical scientific options used by the original run]
```

Do not change total rounds or scientific options on resume: they are part of identity. Device, thread count and machine-specific paths are execution-only. Dataset, trace, scientific configuration and source hashes are validated before restoration. CPU reconstruction of models/clients occurs before RNG restoration. Resume starts after the last completed round, reconstructing CSV from authoritative checkpoint history and restoring the best model. Existing completed results refuse overwrite, including when a resume flag is supplied.

Checkpoints are due after ten rounds, about 180 seconds checked at boundaries, a graceful stop, or final completion. Optional `--stop-file` requests a cross-platform boundary stop. `--lease-file` allows training itself to stop at a boundary if its agent dies or its local lease deadline expires. No incomplete round is labelled complete. Forced termination before a boundary can only recover from an earlier checkpoint.

The worker transfers bounded, chunked ZIP envelopes containing exactly the checkpoint files. Coordinator validation covers sizes, checksums, schema, job/attempt/config/source/data identity and completed-round bounds before durable database publication. The coordinator does not import PyTorch; full safe tensor-state loading and history consistency validation run on the executing/recovery worker. Never accept checkpoint code or pickle classes from dashboard input. In this trusted-revision architecture, workers are authorized research machines, not untrusted compute tenants.

Periodic retention keeps the newest two validated checkpoints for inactive jobs. Active jobs protect their recovery artifacts. `swarm server maintain` applies retention and cleans abandoned uploads; `swarm server backup` uses SQLite's online backup API. Final results remain immutable. Corrupt recovery envelopes are marked invalid and an older validated checkpoint is selected, otherwise the experiment restarts from round 1.

The 100-round CCRA CPU test interrupted at 40 compares final weights, every scientific history field, aggregation state, channel/topology state, counters and best model exactly. Wall-clock timing differs and is excluded from equivalence. This is evidence for the tested equivalent CPU environment, not a promise of bitwise cross-GPU reproducibility. Runtime/GPU/software provenance travels with every result.
