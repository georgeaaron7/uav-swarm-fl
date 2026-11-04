# Acceptance evidence and remaining hardware validation

Implementation version: 0.1.0, branch `feature/swarmcompute`. Automated environment: macOS arm64, Python 3.14, CPU PyTorch 2.14; Chromium desktop/mobile emulation. Test data and injected failures live only in temporary directories and are not scientific campaign results.

## Automated evidence

Run the complete Python suite after installing `.[server,worker,dev]` with a compatible Torch build:

```bash
python -m pytest -q
```

The implementation run passes 69 tests, including the pre-existing scientific suite. New coverage includes:

| Requirement | Evidence |
|---|---|
| Complete scientific state/RNG recovery | 100-round CCRA interrupted at 40 and resumed; exact weights/scientific histories, trust, handovers, counters, best model and channel state; four other aggregators tested |
| Checkpoint integrity and compatibility | Checksum/size/identity failures, incomplete checkpoint rejection, safe loading, older-valid fallback |
| Round-37 failure | Injected failure inside round 37; latest published checkpoint 30; replacement reconstructs rounds 31–100; expired attempt rejected |
| Durable queue and fencing | Concurrent claims, only one owner, expiring leases, reopen coordinator DB, stale heartbeat/progress/failure/release rejection |
| Scientific identity/matrix | Machine paths/resources excluded from identity; source/data changes matter; existing planner generates exactly 240 final jobs for two supported methods |
| Auth/enrollment/owner autonomy | Single-use and expired codes, scoped worker credentials, role/owner controls, versioned participation preferences, revoke/leave, request-size limits and bad settings |
| Result publication | Checked config/provenance/history/CSV/summary/model archive, corrupt uploads rejected, idempotent terminal publication, stale final mutation blocked |
| Infrastructure failure classification | CUDA OOM requires attention; unavailable artifact storage cannot commit a result |
| Scientific divergence | Actual simulator nonfinite aggregation check exercised; finite preceding model retained; original completion schema accepts divergence; coordinator does not retry a terminal divergence |
| Real process execution | Real loopback HTTP coordinator, two independent agent processes, two actual FL training subprocesses on temporary pilot inputs, different worker assignments, progress/checkpoints/results and authoritative exports |
| Analysis compatibility | Exported manifest/results accepted by existing `completed(job, root)`; pre-existing analysis tests remain passing |
| CLI | Actual Typer command parsing for init, documented `join --server`, credential redaction and final `--aggs fedavg ccra` planning |

The round-37 test injects a simulator exception; it is **not** evidence of a physical power interruption at round 37. Lease/partition tests exercise durable protocol transitions, not a real campus Wi-Fi outage. CPU subprocess testing does not establish CUDA behavior or cross-GPU equality.

## Browser checks

```bash
npm ci --prefix web
npm run build --prefix web
python -m playwright install chromium
# The default config starts a disposable loopback-only test coordinator:
npm run test:e2e --prefix web
```

Four Playwright tests pass across desktop and mobile: authenticated routes, real enrollment generation, closed-drawer inertness, Escape/focus restoration, responsive overflow and recoverable invalid login. Python Playwright capture checks also visited all main routes and generated 1440px/390px screenshots. An independent UI review scored four material fixes resolved: frozen-manifest inspection, keyboard drawer handling, no-valid-checkpoint truth, and HTTP clipboard fallback. These checks cover actual API-backed empty states; every populated table/chart interaction is not independently visually certified.

To use your own disposable fixture instead, set `SWARM_TEST_URL`, `SWARM_TEST_USER`, and `SWARM_TEST_PASSWORD`. Do not point destructive enrollment tests at a production study. Fixed credentials in `tests/browser_server.py` are only for newly created disposable loopback test state; production initialization always generates a random credential.

## Packaging checks

The wheel builds with migrations and compiled dashboard assets. Coordinator initialization is tested with Torch imports explicitly prohibited. Source releases contain static files so deployment requires one Uvicorn port and no Node server. `bash -n` validates POSIX installer syntax; PowerShell/Task Scheduler/systemd installers still need target-OS execution.

## Required manual acceptance before production claims

- [ ] Install and run an actual Windows 11 NVIDIA worker; verify chosen driver/CUDA/PyTorch, NVML, enrollment, subprocesses and owner controls.
- [ ] Install and run an actual Ubuntu NVIDIA worker; verify the equivalent checks.
- [ ] Open the real coordinator dashboard and `/health` from another reachable physical laptop through the intended firewall/network.
- [ ] Run a reduced pilot on two heterogeneous physical GPUs. Confirm different assignments, metrics and central checkpoints.
- [ ] Disconnect one laptop during training, wait for lease expiry/reassignment, verify checkpoint resume and safely reconnect the original.
- [ ] Stop/restart the real coordinator while laptops are working and inspect recovery events.
- [ ] Test actual process kill/power-loss behavior and a prolonged partition, retaining the expected central recovery point.
- [ ] Verify owner pause/drain/resume/leave during real GPU work and storage/network outages.
- [ ] Execute opt-in Windows Task Scheduler and Linux systemd user autostart/disable/uninstall; verify no unintended service remains.
- [ ] Compare reproducibility under the actual GPU/software combinations with justified tolerances and recorded provenance.
- [ ] Locate/approve the absent `bp_fresh`/`bp_reuse` source before claiming to execute the originally named base-paper comparison.

The implementation is a working, locally deployable platform with automated CPU/protocol evidence. It is not yet a hardware-accepted SwarmCompute v1 production release under every criterion in the supplied specification.
