# Administrator quick start

Use Python 3.11+ on a coordinator with local writable storage. The tested development environment is macOS/Python 3.14. CPU-only scheduling does not need PyTorch or NVIDIA drivers. SQLite must remain on local disk, never NFS/SMB.

```bash
git clone https://github.com/sasank-555/uav-swarm-fl.git
cd uav-swarm-fl
# Check out the version/branch containing SwarmCompute on every machine.
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[server]"
swarm server init
swarm server start --host 0.0.0.0 --port 8787
```

The feature must be present in your clone; it is not assumed to exist on upstream main. Compiled dashboard files are included under `swarmcompute/static/`. If changing frontend source, install Node.js 22+ and run `npm ci --prefix web` then `npm run build --prefix web`. No Node server is needed at runtime.

`server init` creates `~/.swarmcompute` (or `$SWARM_HOME`), runs Alembic migrations, creates artifact storage, checks disk/write access, creates the first Argon2-hashed administrator password, and prints that password once, detected URLs and an ASCII QR code. Store the credential privately. It is not written into the repository. Change it through Settings after login. Running initialization again refuses to reset existing users.

Open the printed LAN URL from a reachable laptop; locally use `http://localhost:8787`. Review [LAN access](LAN_ACCESS.md) for private firewall rules. Keep the coordinator powered and awake. On macOS an explicitly chosen `caffeinate -i swarm server start --host 0.0.0.0 --port 8787` inhibits idle system sleep; lid closure can still interrupt ordinary service hosting.

## Prepare and start a study

Prepare CIFAR using existing `python prepare_data.py` and DeepSense using `python scripts/prepare_deepsense23.py /path/to/scenario23`. Dataset preparation may require the original research dependencies (`pip install -r requirements.txt`) in a separate preparation environment; scheduling itself does not require them. Do not redistribute raw datasets without permission.

```bash
swarm study create laptop-pilot --profile pilot --aggs bp_fresh bp_reuse
swarm study status laptop-pilot
swarm study start laptop-pilot
```

Equivalent creation/start controls are on Overview. Creating a study only plans/fingerprints it; starting explicitly authorizes scheduling. `swarm study create laptop-final --profile final --aggs bp_fresh bp_reuse` plans 240 jobs: 2 existing methods × 4 attacks × 3 conditions × 10 seeds, 100 rounds. This uses the actual upstream base-paper rules with serialized reuse state. Keep the pair separate from the original six-method context study. See [source audit](AUDIT.md).

Final-profile seeds/rounds retain existing planner defaults. Source and dataset fingerprints are frozen. A worker with different code or data cannot claim the job. Every machine must use the same scientific source files, including checkpoint code.

In Workers, Add worker generates an owner-scoped, single-use enrollment code valid for 10 minutes. Share the code and server address privately. CLI alternative: `swarm server enrollment --owner aaron`. New owner login credentials are shown once to the owner during `swarm join`.

```bash
swarm study pause laptop-pilot
swarm study resume laptop-pilot
swarm study validate laptop-pilot
swarm study export laptop-pilot --destination results/laptop-pilot-export
python analyze_context_study.py --help
swarm server backup
swarm server maintain
swarm server urls
```

Pause stops new claims for that study; running jobs can finish. Study validation checks every expected result before export. Export refuses any existing destination and reconstructs the original planner configuration and directory layout for `completed(job, root)` and the existing analysis scripts. Do not use a pilot as a final scientific result. Existing analysis comparisons are method-specific: absent comparison methods simply do not create new contrasts.

Initial defaults: 5s heartbeats, 20s suspect timeout, 60s leases, retry delay 30s exponential up to 300s, five infrastructure retries, checkpoints every 10 rounds/180s. Settings validates changes. New workers start paused unless automatic-start enrollment policy is enabled; the owner's first `swarm start` explicitly starts participation. Subsequent agent restarts preserve coordinator pause controls.
