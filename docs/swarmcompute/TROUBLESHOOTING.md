# Troubleshooting

**The dashboard does not open on another laptop.** Verify the coordinator is awake and bound to `0.0.0.0`, then test `http://HOST_IP:8787/health`. Check the current IP (`swarm server urls`), private firewall rules, routing/VLANs and Wi-Fi client isolation. Same SSID is insufficient. Use a trusted router, wired network, authorized Tailscale or ask the network administrator.

**Dashboard build missing.** Run `npm ci --prefix web` and `npm run build --prefix web`, then restart the server. Only the compiled assets need to ship with the Python package. Do not keep a Vite development server running for deployment.

**Missing CUDA / incompatible GPU.** Run `nvidia-smi`, `swarm doctor`, and an actual Torch CUDA tensor test. Check the official PyTorch wheel selector against the installed driver and GPU generation. SwarmCompute does not install or update drivers. Unsupported NVML fields remain unknown.

**Worker is incompatible or never receives work.** Compare source hashes and dataset/trace hashes to the frozen study. Pilot data differs from the full CIFAR dataset. Ensure the worker is resumed, the study is started, resource limits permit work, it is not paused/on battery/over temperature, cluster concurrency is not full, and central disk is above critical. CPU workers require explicit pilot-only `--allow-cpu` and do not prove NVIDIA compatibility.

**Worker stops after a network loss.** This is expected after lease renewal becomes impossible. Local artifacts are retained, but a replacement can only resume centrally validated checkpoints. Expired attempts cannot overwrite replacements. Inspect Logs & events and owner logs, then `swarm resume` after recovery if paused.

**CUDA out of memory.** The attempt enters NEEDS_ATTENTION. Keep scientific batch size/configuration unchanged; choose a compatible worker with sufficient VRAM or create a separately approved scientific study. Increasing concurrency does not necessarily improve throughput.

**Numerical divergence.** Inspect its stage and round. DIVERGED is terminal scientific evidence and counts toward terminal study progress. It is not an automatic infrastructure retry.

**Checkpoint corrupt or storage unavailable.** Check disk space and permissions. An invalid central checkpoint is marked and older recovery points are tried. Failed uploads never become authoritative. Resolve storage before requesting new assignments. Never delete the only required checkpoint by hand.

**Already initialized / result exists.** Initialization, training and export deliberately refuse to overwrite existing records/results. Use a new study/attempt/export destination or resume an unfinished experiment from its checkpoint. Preserve original historical data.

**Pause or leave pending.** Keep the agent alive until it finishes the round, publishes its checkpoint and releases its lease. If publication is unavailable, the logs state that only local files are retained. Abrupt loss recovers only from previously central checkpoints. Disable opted-in autostart before uninstalling.

**Agent lock exists.** Do not start a second GPU process. Verify the recorded process is your existing agent. After an actual crash/reboot, stale PID lock files are reconciled by startup; investigate logs if startup still reports an active agent.

**HTTPS / LAN credentials.** Browser login uses explicit expiring bearer authorization, not cookies. Shared or untrusted institutional networks require Tailscale or HTTPS before transmitting credentials/artifacts. Do not put secrets in source, URLs, screenshots or shell history.
