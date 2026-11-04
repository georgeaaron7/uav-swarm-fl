param([string]$TorchIndexUrl = $env:SWARM_TORCH_INDEX_URL)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows, then reopen PowerShell.' }
# Use an existing environment, otherwise prefer the Python 3.11 launcher.
$SwarmPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $SwarmPython)) {
    $UseLauncher = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.11 -c 'import sys; assert sys.version_info >= (3,11)' 2>$null
            $UseLauncher = ($LASTEXITCODE -eq 0)
        } catch { $UseLauncher = $false }
    }
    if ($UseLauncher) { & py -3.11 -m venv .venv }
    else {
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11+ from python.org with the Python launcher and pip, then reopen PowerShell.' }
        & python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $SwarmPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed.' }
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { throw 'NVIDIA driver tools are missing. Install the appropriate NVIDIA driver explicitly; this installer never changes drivers.' }
& nvidia-smi
if ($LASTEXITCODE -ne 0) { throw 'The NVIDIA driver check failed.' }
& $SwarmPython -c "import importlib.util, sys; sys.exit(1) if importlib.util.find_spec('torch') is None else None; import torch; sys.exit(0 if torch.cuda.is_available() else 1)"
$CudaAlreadyWorks = ($LASTEXITCODE -eq 0)
if (-not $CudaAlreadyWorks) {
    if (-not $TorchIndexUrl) {
        Write-Host 'Open https://pytorch.org/get-started/locally/ and select Windows / Pip / Python / a CUDA build compatible with the GPU and driver above.'
        Write-Host 'Paste only the official --index-url value (https://download.pytorch.org/whl/cu...), or press Enter to stop and ask the coordinator owner for help.'
        $TorchIndexUrl = Read-Host 'Official PyTorch CUDA wheel index URL'
    }
    if ($TorchIndexUrl -notmatch '^https://download\.pytorch\.org/whl/cu[0-9]+/?$') { throw 'A compatible official CUDA wheel index is required. No driver or CPU-only fallback was installed.' }
    & $SwarmPython -m pip install --upgrade torch torchvision --index-url $TorchIndexUrl
    if ($LASTEXITCODE -ne 0) { throw 'CUDA-enabled PyTorch installation failed. Check GPU/driver/Python compatibility using the official selector.' }
}
& $SwarmPython -m pip install -e '.[worker]'
if ($LASTEXITCODE -ne 0) { throw 'Worker dependency installation failed.' }
& $SwarmPython -c "import torch; print('PyTorch:',torch.__version__,'CUDA build:',torch.version.cuda); assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_name(0)); x=torch.ones(32,device='cuda'); assert (x*2).sum().item()==64"
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed. No drivers were changed.' }
Write-Host 'Installed. No PowerShell activation policy change is required.'
Write-Host 'Unzip the private worker-data ZIP into this repository, then run:'
Write-Host '.\.venv\Scripts\swarm.exe data verify'
Write-Host '.\.venv\Scripts\swarm.exe join --server http://COORDINATOR_IP:8787 --name your-laptop-name'
Write-Host '.\.venv\Scripts\swarm.exe doctor'
Write-Host '.\.venv\Scripts\swarm.exe start'
