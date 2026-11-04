# Windows 11 worker

For the current MacBook-coordinator / Windows-only deployment, start with the [complete step-by-step guide](MAC_WINDOWS_QUICKSTART.md). The installer now explicitly asks for a compatible official CUDA wheel index when CUDA-enabled PyTorch is not already working. Do not rely on pip defaults for NVIDIA support.

Follow [owner setup](WORKER_SETUP.md). Use an NVIDIA driver compatible with your GPU and chosen PyTorch CUDA wheel; installation is explicit. The PowerShell installer creates `.venv`, reports `nvidia-smi`, installs the worker extras and runs a CUDA tensor test. It fails clearly rather than replacing drivers.

Activate `.\.venv\Scripts\Activate.ps1`, or invoke `.\.venv\Scripts\swarm.exe`. If policy prevents activation, the direct launcher works without changing machine policy. The documented installer invocation uses a policy override only for that PowerShell process.

Choose the compatible official PyTorch wheel before installation when necessary:

```powershell
# Set $env:SWARM_TORCH_INDEX_URL to the URL selected for your hardware at pytorch.org.
powershell -ExecutionPolicy Bypass -File .\scripts\install-worker.ps1
.\.venv\Scripts\swarm.exe join --server http://COORDINATOR_IP:8787
.\.venv\Scripts\swarm.exe doctor
.\.venv\Scripts\swarm.exe start
```

Set suitable plugged-in timeouts under Settings → System → Power & battery → Screen, sleep & hibernate timeouts. Review lid-close behavior in Power Options and the laptop's cooling instructions. No sleep or driver setting changes automatically.

`swarm autostart enable` registers an interactive per-user Task Scheduler task named **SwarmCompute Worker**, with restart-on-failure. This is opt-in and does not create a privileged system service. `swarm autostart disable` removes the task. Stop/leave and disable startup before uninstalling. Keep credentials under the owner's private user-profile ACL.

Windows NVIDIA execution and Task Scheduler installation require manual target-machine acceptance; the macOS test suite cannot validate Windows drivers, CUDA or UI power settings.
