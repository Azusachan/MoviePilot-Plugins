#!/usr/bin/env bash
set -euo pipefail
# Disposable image filesystem and synthetic config only; no host credentials.
docker run --rm --entrypoint sh \
  -v "$PWD/plugins.v2/cloudsubscribefork:/app/app/plugins/cloudsubscribefork:ro" \
  -v "$PWD/.github/scripts:/checks:ro" -e PYTHONPATH=/app -w /app \
  docker.io/jxxghp/moviepilot-v2:latest -c '
    pip install --no-cache-dir -r app/plugins/cloudsubscribefork/requirements.txt
    python /checks/runtime_smoke.py
  '
