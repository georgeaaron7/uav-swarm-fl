$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows, then reopen PowerShell.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11+ from python.org and enable the launcher/PATH option.' }
python -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$SwarmPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $SwarmPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed.' }
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { nvidia-smi } else { Write-Warning 'Install an appropriate NVIDIA driver explicitly; driver installation is never automatic.' }
if ($env:SWARM_TORCH_INDEX_URL) {
    & $SwarmPython -m pip install torch torchvision --index-url $env:SWARM_TORCH_INDEX_URL
    if ($LASTEXITCODE -ne 0) { throw 'Requested PyTorch wheel installation failed.' }
} else { Write-Host 'Using pip default PyTorch wheels. Set SWARM_TORCH_INDEX_URL using https://pytorch.org/get-started/locally/ for a validated CUDA wheel.' }
& $SwarmPython -m pip install -e '.[worker]'
if ($LASTEXITCODE -ne 0) { throw 'Worker dependency installation failed.' }
& $SwarmPython -c 'import torch; print("PyTorch:",torch.__version__,"CUDA build:",torch.version.cuda); assert torch.cuda.is_available(), "CUDA unavailable; select a compatible official PyTorch build"; print(torch.cuda.get_device_name(0)); x=torch.ones(32,device="cuda"); assert (x*2).sum().item()==64'
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed. Use the official PyTorch installation selector; no drivers were changed.' }
Write-Host 'Activate with .\.venv\Scripts\Activate.ps1 (or invoke .\.venv\Scripts\swarm.exe directly).'
Write-Host 'Prepare data using docs/swarmcompute/WORKER_SETUP.md, then swarm join --server http://COORDINATOR_IP:8787'
Write-Host 'Run swarm doctor, then swarm start. Autostart and power changes remain opt-in.'
