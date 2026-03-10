#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build "$SCRIPT_DIR/../docker/sandbox" -t lacuna-sandbox "$@"
echo "[lacuna] Sandbox image built: lacuna-sandbox"
