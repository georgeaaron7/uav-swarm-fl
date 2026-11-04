#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -c 'import sys; assert sys.version_info >= (3,11)'
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[server]'
if [[ ! -f swarmcompute/static/index.html ]]; then
  command -v npm >/dev/null || { echo 'Dashboard bundle missing. Install Node.js 22+ for this build step, or use a source release containing the compiled dashboard.'; exit 1; }
  npm ci --prefix web
  npm run build --prefix web
fi
echo 'Activate: source .venv/bin/activate'
echo 'Initialize once: swarm server init'
echo 'Start: swarm server start --host 0.0.0.0 --port 8787'
