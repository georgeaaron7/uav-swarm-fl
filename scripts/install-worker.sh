#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v git >/dev/null || { echo 'Install Git using your package manager.'; exit 1; }
command -v python3 >/dev/null || { echo 'Install Python 3.11+ and python3-venv.'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
if command -v nvidia-smi >/dev/null; then nvidia-smi; else echo 'NVIDIA driver tools unavailable. Install an appropriate driver explicitly before contributing GPU jobs.'; fi
# Respect an explicitly validated PyTorch installation/index; never replace drivers.
if [[ -n "${SWARM_TORCH_INDEX_URL:-}" ]]; then
  .venv/bin/python -m pip install torch torchvision --index-url "$SWARM_TORCH_INDEX_URL"
else
  echo 'Using pip default PyTorch wheels. For a validated CUDA wheel, set SWARM_TORCH_INDEX_URL from https://pytorch.org/get-started/locally/ before installation.'
fi
.venv/bin/python -m pip install -e '.[worker]'
echo 'Testing CUDA; a failed check needs a compatible driver/PyTorch combination.'
.venv/bin/python -c 'import torch; print("PyTorch:",torch.__version__,"CUDA build:",torch.version.cuda); assert torch.cuda.is_available(), "CUDA unavailable; use the official PyTorch installation selector"; print(torch.cuda.get_device_name(0)); x=torch.ones(32,device="cuda"); assert (x*2).sum().item()==64'
echo 'Worker installed. Activate: source .venv/bin/activate'
echo 'Prepare CIFAR-10 and DeepSense using docs/swarmcompute/WORKER_SETUP.md, then: swarm join --server http://COORDINATOR_IP:8787'
echo 'Run swarm doctor, then swarm start. Startup and sleep changes are opt-in.'
