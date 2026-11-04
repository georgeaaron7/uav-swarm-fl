# Laptop owner quick start

Target workers are Windows 11 and Ubuntu 22.04/24.04 with an NVIDIA GPU, a working NVIDIA driver and compatible CUDA-enabled PyTorch. These targets require the hardware checks in [acceptance](ACCEPTANCE.md); they have not been verified by the macOS development tests. A coordinator can use macOS, Linux or Windows without a GPU.

1. Clone the repository and check out the exact approved SwarmCompute revision used by the coordinator.
2. Run `powershell -ExecutionPolicy Bypass -File .\scripts\install-worker.ps1` on Windows, or `bash scripts/install-worker.sh` on Linux.
3. Activate `.venv` or use its `swarm` launcher directly. The installer checks Python/Git, reports NVIDIA driver information, installs dependencies and tests an actual CUDA tensor operation. It never changes drivers. When necessary select a validated wheel at [PyTorch's installer](https://pytorch.org/get-started/locally/) and supply its index as `SWARM_TORCH_INDEX_URL` before running the installer.
4. Prepare the data using the existing project scripts. Run `python prepare_data.py` for CIFAR. For DeepSense, obtain Scenario 23 under its terms, then `python scripts/prepare_deepsense23.py /path/to/scenario23`. Preparation needs the original dependencies, including pyarrow for parquet conversion: `python -m pip install -r requirements.txt`. Raw data is never committed or automatically redistributed.
5. Obtain the server address and a one-time enrollment code from the administrator.

```bash
swarm join --server http://COORDINATOR_IP:8787 --name my-laptop
swarm doctor
swarm start
```

The enrollment code is prompted privately. `--pairing-code` is supported but can expose it in shell history. `join` stores only a scoped, revocable worker credential in the owner configuration directory, with mode 0600 on Unix. On Windows it inherits the user's profile ACL; keep that directory private. New dashboard owner credentials are displayed once. Use a trusted LAN or Tailscale/HTTPS before transmitting credentials on shared networks.

`join --data-dir /prepared/data --trace-path /prepared/deepsense23.npz` selects local files. Pilot studies require the exact balanced subset created by the coordinator's existing `pilot_data()` helper: run the existing pilot planner with `--plan-only`, or prepare that subset identically. Example:

```bash
python run_context_study.py --profile pilot --aggs fedavg ccra --plan-only
swarm join --server http://COORDINATOR_IP:8787 --data-dir data/context_pilot
```

Do not use different data to bypass a fingerprint mismatch. Restart/re-enroll into a fresh owner config if changing enrollment; ordinary preferences can be updated with `swarm config set`.

## Owner controls

```bash
swarm status
swarm pause
swarm pause --after-round
swarm resume
swarm logs --follow
swarm config show
swarm config set mode light
swarm config set mode balanced
swarm config set cpu_threads 2
swarm config set allow_battery false
swarm config set min_battery 20
swarm config set max_temperature 85
swarm config set storage_limit_bytes 21474836480
swarm config set admin_permissions '["pause","resume","drain"]'
swarm benchmark
swarm autostart enable
swarm autostart disable
swarm leave
```

`pause` drains after the current experiment. `pause --after-round` asks for a completed-round checkpoint, uploads and validates it, then releases the job. Another worker may resume it. If disconnected, only locally retained files may exist; consult logs. Never assume an unpublished local checkpoint is central recovery state.

The owner dashboard also lets you request a participation mode; the agent acknowledges a versioned settings update and applies process limits to its next experiment. Changing mode resets the default CPU-thread budget; explicit CPU-thread configuration can then override it.

Light uses one CPU thread and waits for lower CPU activity. Balanced uses two threads. Dedicated uses more available CPU threads but still one GPU experiment until multi-process capacity has actually been measured. The current version does not enable unbenchmarked GPU concurrency. These are process/admission policies, not hard GPU memory partitions or guarantees of interactive performance. Battery/temperature gates are enforced when sensors are available; unsupported sensors remain unknown. VRAM budget is admission metadata, not a PyTorch memory cap. A nonzero budget declines jobs whose measured memory requirement is unknown; leave it at zero until a validated job memory profile is available. Restart the agent after changing server or dataset paths.

`benchmark` runs two actual baseline rounds in a separate benchmark directory and labels measurements as benchmark-only. It is not substituted for final results. Concurrency and GPU models alone are not used to claim performance. CPU-only pilots can be explicitly enabled with `join --allow-cpu` for test environments; do not count them as NVIDIA acceptance.

Connect power, keep cooling vents clear, choose suitable OS sleep settings, and keep the agent open. Closing the lid may suspend the computer. Display sleep is fine. Browsing/programming can coexist subject to available resources; GPU-heavy games may compete.

Autostart is opt-in. It installs only a user service/task/launch agent and can be disabled with the matching command. Before uninstalling, disable autostart, leave, wait for checkpoint/release, then delete the virtual environment and optional `~/.swarmcompute/worker` cache. Leave is independent of administrator approval.
