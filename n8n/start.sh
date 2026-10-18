#!/usr/bin/env bash
# Start local n8n in Docker on http://localhost:5678, reachable from this machine only.
# Data (owner account, API key, credentials, workflows) persists in the brightpan_n8n_data volume.
set -euo pipefail
if docker ps -a --format '{{.Names}}' | grep -qx brightpan-n8n; then
  docker start brightpan-n8n >/dev/null
else
  docker run -d --name brightpan-n8n -p 127.0.0.1:5678:5678 \
    -e GENERIC_TIMEZONE=America/New_York -e TZ=America/New_York \
    -e N8N_DIAGNOSTICS_ENABLED=false -e N8N_PERSONALIZATION_ENABLED=false \
    -v brightpan_n8n_data:/home/node/.n8n \
    docker.n8n.io/n8nio/n8n:2.43.7 >/dev/null
fi
echo "n8n starting on http://localhost:5678"
