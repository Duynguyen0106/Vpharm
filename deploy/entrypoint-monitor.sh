#!/usr/bin/env bash
# Run the Facebook monitor under Xvfb (headed Chromium on a headless VPS).
set -euo pipefail
mkdir -p "${FB_SESSION_DIR:-/data/session}"
exec xvfb-run -a --server-args="-screen 0 1280x900x24" python main.py
