# Operations and recovery

1. Keep the coordinator awake on power; run `swarm server start --host 0.0.0.0 --port 8787` and verify its `/health` endpoint from another device.
2. Prepare and checksum the datasets/traces; create a pilot study. Review the generated jobs before `swarm study start NAME`.
3. Generate owner-scoped enrollment codes; each owner installs, joins, runs doctor and starts the agent. Wait for compatible workers before starting the final study.
4. Monitor terminal progress, worker heartbeat/GPU telemetry and validated checkpoints. Unknown throughput/ETA stays blank until real completions exist.
5. `swarm pause --after-round` publishes a boundary checkpoint then releases the job. `swarm resume` allows claims again. Draining finishes the current experiment before stopping new claims.
6. After all jobs are terminal, run `swarm study validate NAME` then `swarm study export NAME --destination results/NEW-DIRECTORY`. Export cannot overwrite old output. Use the original analysis tools on the export.

## Failure behavior

Lease expiration ends the old attempt and schedules exponential infrastructure retry. Another compatible worker resumes from the newest valid centrally published checkpoint. Reconnecting workers have no implicit claim on prior work. All stale mutations are fenced. If a corrupt checkpoint is found, it is marked invalid with an event and an older checkpoint is tried. With none available, restart from round 1.

Numerical divergence is a terminal scientific outcome; its finite previous model/history and diagnostics are kept. It is never retried into a selectively successful experiment. CUDA OOM, deterministic application errors, source/data mismatches and exhausted infrastructure retries require attention. Changing a scientific batch size to fix OOM would change the experiment and must not happen automatically.

A temporary network partition triggers retries with backoff/jitter. Workers keep checkpoints locally and request a boundary stop when lease renewal fails. The training subprocess independently checks its lease deadline between rounds, including when its agent has crashed. A boundary cannot be created after power loss. If a round does not finish within 120 seconds of a worker stop request, the agent terminates it; recovery then uses a previously published boundary. This is a bounded shutdown fallback, not partial-round recovery.

Coordinator startup opens the same persistent DB and reconciles leases. Lease checks also happen during claims/heartbeats/publications, so restart cannot authorize stale output. SSE is advisory; persisted state and polling remain authoritative. A restarted worker requests fresh work and retains local orphan artifacts for inspection; it does not auto-publish superseded attempts.

## Storage

Default application state: `~/.swarmcompute`, override `SWARM_HOME`. Worker state: `~/.swarmcompute/worker`, override `SWARM_WORKER_HOME`. Artifacts are separate from historical repository results. Paths in the DB are server-generated relative content hashes.

`swarm server backup` uses SQLite online backup (includes WAL state), and prints a new timestamped DB file. Back up that DB together with `artifacts/`, `studies/` and configuration under access-controlled storage. To restore, stop the coordinator, restore a consistent snapshot under the same application directory, then restart and inspect recovery events. Do not copy only an actively changing `.db` file while ignoring WAL.

`swarm server maintain` retains latest two checkpoints per inactive job, protects active dependencies, and removes stale upload files after a day. No dashboard endpoint permits arbitrary checkpoint deletion. Critical low disk stops claims; warning thresholds are visible in Overview and configurable in Settings. Expired upload lock files can be removed after confirming no upload is active.

## Version changes

Distribute the exact versioned source to workers explicitly. Never auto-update a worker's scientific code during an active experiment. Source/data changes require a newly planned study, with new fingerprints. Record runtime/GPU differences; compare tolerances before claiming reproducibility across heterogeneous GPUs.
