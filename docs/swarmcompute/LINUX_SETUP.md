# Ubuntu 22.04 / 24.04 worker

Install Python 3.11+ with venv support, Git and a deliberately selected NVIDIA driver. Ubuntu's system Python version may need a separately installed compatible Python; do not replace distribution tooling blindly. Use [owner setup](WORKER_SETUP.md) and the official PyTorch wheel selector for the GPU/driver combination.

```bash
bash scripts/install-worker.sh
source .venv/bin/activate
swarm join --server http://COORDINATOR_IP:8787
swarm doctor
swarm start
```

The installer respects `SWARM_TORCH_INDEX_URL` for a validated PyTorch wheel source, reports `nvidia-smi` when present, and tests actual CUDA computation. No driver installation is automatic.

Desktop automatic suspend and lid behavior remain owner settings. Keep power and airflow available. Turning off the screen does not need to suspend the system.

`swarm autostart enable` writes `~/.config/systemd/user/swarmcompute.service`, reloads the user manager and enables the user service. `Restart=on-failure` reconnects after crashes. User services generally need a logged-in user; lingering is an independent administrator choice. Sleep and network managers can still interrupt connectivity. `swarm autostart disable` stops/disables the service and removes its file. No root-level service or power override is installed.

Linux NVIDIA execution, driver/PyTorch compatibility and systemd behavior require manual acceptance on target hardware. CPU macOS tests cover the HTTP/process protocol, not the Linux GPU runtime.
