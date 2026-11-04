# MacBook coordinator + Windows GPU laptops

Your MacBook is the control desk and permanent results store. Each Windows laptop runs one complete experiment at a time on its NVIDIA GPU. The simulated UAVs are inside each experiment. You do not combine laptop GPUs into a single GPU.

## On the MacBook: once

Use the existing checkout containing SwarmCompute and activate its environment:

```bash
source .venv/bin/activate
swarm server init                       # only if not already initialized
swarm server start --host 0.0.0.0 --port 8787
```

Keep this terminal open, or use the locally installed Start Coordinator shortcut if the assistant set one up. No login/startup service is installed automatically. Open `http://localhost:8787`. Log in with the administrator password printed at initialization. If it was lost, the Mac's local recovery command prompts for a new one:

```bash
swarm server reset-password --username admin
```

This resets only the requested account and revokes its old sessions; do not run it unless you need recovery.

Run `swarm server urls` to see the current LAN address. A Windows laptop must open the **LAN address**, not localhost. Check both devices can communicate; campus Wi-Fi may block peers even on the same SSID. If this happens, use a trusted private router/wired network or authorized Tailscale. Use trusted LAN or encrypted transport for credentials. Do not expose port 8787 publicly.

Prepared input files are already separate from Git. Package them for the team:

```bash
swarm data export --destination /private/path/swarm-worker-data.zip
```

Copy the ZIP privately to each owner (USB is sufficient). It contains full CIFAR, the pilot subset, the prepared trace and a manifest; it is not uploaded to GitHub. Share only with authorized study participants under the dataset terms.

Create the studies once, then leave them pending while enrolling workers:

```bash
swarm study create windows-pilot --profile pilot --aggs bp_fresh bp_reuse
swarm study create base-paper-comparison --profile final --aggs bp_fresh bp_reuse
```

The pilot has 48 jobs × 2 rounds. The final study has 240 jobs × 100 rounds. Both use existing planner configurations. Start the pilot first; do not start the final study until at least one actual Windows NVIDIA worker has passed doctor and completed pilot jobs.

## On every Windows laptop: install once

1. Confirm it has a supported NVIDIA GPU and installed driver. Open **PowerShell** and run `nvidia-smi`. An Intel/AMD-only laptop is not supported as a GPU worker in this version. Send the output to the coordinator owner if driver/CUDA selection is uncertain.
2. Install **Git for Windows** and **Python 3.11+** with pip and the Python launcher. Close/reopen PowerShell after installation.
3. Until the PR is merged, clone the feature branch from the contributor fork:

```powershell
git -c core.autocrlf=false clone --branch feature/swarmcompute https://github.com/georgeaaron7/uav-swarm-fl.git
cd uav-swarm-fl
git config core.autocrlf false
# If the coordinator gave you a frozen commit, also run: git checkout THAT_COMMIT
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-worker.ps1
```

The installer creates a private virtual environment and checks an actual CUDA tensor operation. If no working CUDA PyTorch is present, it prints your NVIDIA driver info and asks for an official CUDA wheel index URL from [PyTorch's installer selector](https://pytorch.org/get-started/locally/). Select Windows / Pip / Python / the compatible CUDA build, and paste only the value after `--index-url`. Hardware differs: do not guess a driver/CUDA build. No drivers are installed or changed automatically.

4. Copy `swarm-worker-data.zip` to the repository directory. Extract it without overwriting existing inputs:

```powershell
# In a fresh checkout, there should be no data directory yet.
Expand-Archive -LiteralPath .\swarm-worker-data.zip -DestinationPath .
.\.venv\Scripts\swarm.exe data verify
```

Expected: `valid: true`. If false, stop and fix the source/data mismatch. No package activation or permanent execution-policy change is required when using the explicit `.venv` launcher.

## Each time you add another laptop

**You, on the MacBook:** open Dashboard → Workers → Add worker. Enter a unique owner username and generate the one-time enrollment code. Generate it after installation/data preparation, because it expires after ten minutes. Privately give the owner the code and your current LAN URL.

**Owner, on Windows:** first test connectivity, replacing HOST_IP with the Mac's current LAN IP:

```powershell
Invoke-RestMethod http://HOST_IP:8787/health
```

It must report status `ok`. Then, still inside the repository:

```powershell
.\.venv\Scripts\swarm.exe join --server http://HOST_IP:8787 --name owner-laptop
.\.venv\Scripts\swarm.exe doctor
.\.venv\Scripts\swarm.exe start
```

`join` asks privately for the code. Save the new owner dashboard password displayed once. `doctor` must show CUDA ready; `data verify` must be valid. `start` keeps running in that PowerShell window. Do not close that window while contributing. Joining alone does not start the worker agent.

**You, on the MacBook:** confirm the laptop appears as compatible/online. Once at least one is ready, start **windows-pilot** on Overview. New compatible workers can join while it runs. Confirm real rounds and centrally validated checkpoints/results appear. Final-study start remains a separate explicit action.

## Daily use

- MacBook: powered, awake, reachable; coordinator running. Keep the same network/IP when possible.
- Windows owner: plugged in, ventilated, suitable plugged-in sleep timeout, agent PowerShell window open. Balanced mode is default, with one GPU process and two CPU threads.
- Opening a dashboard in a browser only monitors/manages; it does not run training.
- Owners can keep using their laptops subject to available resources. Closing lids or launching GPU-heavy games can interrupt/compete with training.
- New workers need the same frozen code/data; do not pull unrelated source updates mid-study.

In a **second PowerShell** window inside the repository:

```powershell
.\.venv\Scripts\swarm.exe status
.\.venv\Scripts\swarm.exe pause --after-round   # checkpoint, upload, release, pause
.\.venv\Scripts\swarm.exe resume
.\.venv\Scripts\swarm.exe pause                 # finish experiment, then stop new work
.\.venv\Scripts\swarm.exe leave
```

The Mac administrator can operate pause/resume controls only if the owner grants permission. Optional owner consent:

```powershell
.\.venv\Scripts\swarm.exe config set admin_permissions pause,resume,drain
```

Optional auto-start at Windows login is a separate owner choice: `swarm.exe autostart enable`; remove it with `swarm.exe autostart disable` before uninstalling. It is not required for the first pilot.

If a laptop disconnects, its lease expires and another compatible worker resumes from the latest checkpoint already validated on the Mac. A sudden power loss cannot create a new checkpoint. A diverged experiment is a terminal scientific outcome, not a missing run to retry selectively.

## Finish and GitHub

After the pilot is complete and validated, start the 240-job final study. When all its jobs are terminal:

```bash
swarm study validate base-paper-comparison
swarm study export base-paper-comparison --destination results/base-paper-export
swarm server backup
```

GitHub distributes/reviews **code**; it is not the coordinator or checkpoint store. A PR to `sasank-555/uav-swarm-fl:main` lets maintainers review/merge the feature. You can use the shared feature branch before merge. After merge, use the same approved source on every worker. Do not upload credentials, worker configurations, raw datasets or the private data ZIP. Windows/macOS CI validates CPU/protocol/browser behavior; actual Windows NVIDIA pilot acceptance still requires a physical GPU laptop.
