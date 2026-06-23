#!/usr/bin/env bash
# Save demo transcript to demo/netops-demo.txt
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p demo
OUT="demo/netops-demo.txt"
echo "Writing demo transcript to $OUT ..."
bash scripts/demo.sh 2>&1 | tee "$OUT"
echo "Done → $OUT"
