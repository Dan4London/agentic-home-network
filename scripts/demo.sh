#!/usr/bin/env bash
# Demo walkthrough (~70s). Record with: ./scripts/record-demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

pause() { sleep "${1:-2}"; }

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Agentic Home-Network Operations — Live Demo              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
pause 3

echo ""
echo "▶ Step 1/4: Full agent scan (performance + security)"
echo "  Probe host: Pi at 192.168.1.70 via SSH key auth"
pause 2
uv run netops-agent --no-mcp 2>&1 | head -35
pause 3

echo ""
echo "▶ Step 2/4: Unknown laptop scenario (eval)"
echo "  Simulates Mac at 192.168.1.12 joining the LAN"
pause 2
uv run netops-eval --scenario unknown_laptop 2>&1
pause 3

echo ""
echo "▶ Step 3/4: Performance incident + closed-loop act (dry-run)"
echo "  Unreachable target triggers notify action"
pause 2
uv run netops-agent --no-mcp --skip-security --targets 192.168.1.1,10.255.255.1 --act --approve 2>&1 | tail -22
pause 3

echo ""
echo "▶ Step 4/4: Full eval suite"
pause 2
uv run netops-eval 2>&1 | tail -8

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Demo complete — perceive → reason → decide → act → observe  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
