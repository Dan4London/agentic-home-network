# Agentic Home-Network Operations

A miniature **autonomous-networks** agent that monitors home-network
**performance** (latency) and **security** (unexpected devices), reasons about
anomalies, and takes **guarded closed-loop action**. Built with **MCP tools**
and a **LangGraph** control loop — the same perceive → reason → act pattern
used in carrier OSS, at lab scale.

> **Status:** Phases 0–4 complete.

## What it does

| Capability | How |
|------------|-----|
| **Performance** | ICMP latency probes from a LAN host (e.g. Raspberry Pi) to gateway + WAN targets |
| **Security** | Active ARP sweep, device identification (MAC OUI, DNS, mDNS, HTTP banner), diff vs allow-list |
| **Reasoning** | Rule-based incident reports; optional Claude enrichment via `ANTHROPIC_API_KEY` |
| **Closed loop** | Propose → confirm → act (`notify`, `block_device`, `rate_limit`) with guardrails |
| **Evals** | 13 scripted scenarios with a weighted grader (`netops-eval`) |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     LangGraph agent (orchestrator)                 │
│   perceive ──► reason ──► decide ──► act ──► observe              │
│       │          │           │        │                            │
│       │          │           │        └── guarded actuator       │
│       │          │           └── pick actions from incidents     │
│       │          └── rule-based (+ optional LLM) analysis          │
│       └── MCP tools + SSH probes                                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ MCP (stdio) / SSH
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
 perf_probe            device_inventory           actuator
 (ping / iperf)        (ARP scan + identify)     (notify / block / limit)
     │                       │
     └───────────┬───────────┘
                 ▼
           LAN probe host
         (e.g. Raspberry Pi)
                 │
                 ▼
              Home LAN
```

| MCP server | Tools |
|------------|-------|
| **perf_probe** | `measure_latency`, `measure_throughput` (stub) |
| **device_inventory** | `list_devices`, `identify_devices`, `diff_against_known` |
| **actuator** | `propose_action_tool`, `apply_action`, `rollback_block_tool` |
| **flow_monitor** | Stub (Phase 2+ extension) |

Device identification combines MAC OUI lookup, reverse DNS, mDNS (macOS), HTTP
Server banners, and local-host detection for privacy/randomised MACs.

## Quickstart

```bash
# 1. Install
cp .env.example .env          # configure probe host — see below
cp baseline/known_devices.yaml.example baseline/known_devices.yaml
uv sync

# 2. Set up probe access (SSH key recommended)
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@<PROBE_HOST>

# 3. Build your device allow-list locally (never commit the result)
uv run netops-discover --write-baseline

# 4. Run the agent
uv run netops-agent --no-mcp

# 5. Closed loop — dry-run notify by default
uv run netops-agent --act --approve

# 6. Grade against scripted scenarios
uv run netops-eval

# 7. Record a demo transcript (~70s)
chmod +x scripts/demo.sh scripts/record-demo.sh
./scripts/record-demo.sh
```

## What to commit (and what not to)

This repo is designed to be **safe to publish** without exposing your home network.

| Commit | Do **not** commit |
|--------|-------------------|
| Source code, evals, `*.example` files | `.env` (credentials) |
| `baseline/known_devices.yaml.example` | `baseline/known_devices.yaml` (your MACs/IPs) |
| `.cursor/mcp.json.example` | `.cursor/mcp.json` (local Cursor wiring; uses `.env`) |
| README, `pyproject.toml` | `var/` (action logs, notifications) |
| | `demo/` (recorded transcripts may contain LAN details) |

`.gitignore` already excludes the sensitive paths. Before screenshots or screen
recordings, redact MAC addresses, private IPs, and hostnames.

## Environment

Copy `.env.example` → `.env` and set:

| Variable | Purpose |
|----------|---------|
| `PROBE_HOST` | IP of your LAN probe (e.g. Raspberry Pi) |
| `PROBE_USER` | SSH user on the probe |
| `PROBE_SSH_KEY` | Path to SSH private key (**recommended**) |
| `PROBE_PASSWORD` | Fallback only if key auth is unavailable |
| `LATENCY_TARGETS` | Comma-separated ping targets (gateway + WAN) |
| `ANTHROPIC_API_KEY` | Optional — enables LLM reasoning |
| `DRY_RUN` | `true` (default) — preview actions without applying |
| `USE_MOCK_PROBES` | `true` for offline dev without SSH |

## CLI reference

### Commands

| Command | Description |
|---------|-------------|
| `netops-agent` | Run the full agent loop |
| `netops-discover` | Identify LAN devices; `--write-baseline` updates allow-list |
| `netops-eval` | Grade rule-based agent against 13 scenarios |

### `netops-agent` flags

| Flag | Description |
|------|-------------|
| `--mock` | Static probe data, no SSH |
| `--no-mcp` | Call probe code directly (faster for local dev) |
| `--skip-security` | Performance checks only |
| `--targets a,b,c` | Override `LATENCY_TARGETS` |
| `--act` | Run decide → act after reporting |
| `--approve` | Auto-approve safe `notify` actions (with `--act`) |
| `--interactive` | Prompt before each action |
| `--allow-block` | Permit `block_device` / `rate_limit` with `--approve` |
| `--json` | Machine-readable report |

### Examples

```bash
# Healthy baseline check
uv run netops-agent --no-mcp

# Simulate WAN failure (use a non-routable target on your LAN)
uv run netops-agent --targets <gateway>,10.255.255.1

# Unknown-device detection is exercised via evals (no live LAN needed)
uv run netops-eval --scenario unknown_laptop

# Live notify (safe — writes to var/notifications.jsonl)
DRY_RUN=false uv run netops-agent --skip-security --targets <gateway>,10.255.255.1 --act --approve
```

## Safety defaults

- **`DRY_RUN=true`** — actions are previewed, not applied
- **Allow-list** — only `notify`, `rate_limit`, `block_device` are permitted
- **`notify`** is the only action auto-approved with `--approve`
- **`block_device`** requires `--allow-block` and `DRY_RUN=false`
- Security incidents **propose** blocks but skip them unless explicitly allowed
- **Rollback:** `rollback_block(<ip>)` or remove entry from `var/blocked_devices.json`

Destructive actions apply **probe-side iptables** rules only — they do not
configure your router. Review before disabling `DRY_RUN`.

## Eval suite

13 scenarios cover healthy baselines, degraded/down WAN, unknown devices
(laptop, IoT, multiple), and combined performance + security incidents.

```bash
uv run netops-eval                 # full suite (80% pass threshold)
uv run netops-eval --scenario wan_unreachable
uv run netops-eval --json
```

See `evals/rubric.md` for grading criteria.

## Demo recording

`scripts/demo.sh` walks through:

1. Full agent scan (performance + security)
2. Unknown-laptop eval scenario
3. Performance incident with closed-loop dry-run act
4. Full eval suite summary

```bash
./scripts/record-demo.sh    # → demo/netops-demo.txt (gitignored)
```

Use the transcript as a script for a screen recording — **redact any LAN-specific
output first**.

## Project layout

```
agent/              LangGraph loop, analyzer, actuator, policies, schemas
mcp_servers/        MCP tool servers (perf, inventory, actuator, flows)
probes/             SSH runner, latency, device identity, baseline diff
baseline/           known_devices.yaml.example (template; real file is local)
evals/              scenarios/ + run_evals.py grader
scripts/            demo.sh, record-demo.sh
var/                Action logs (gitignored, created at runtime)
```

Built with Cursor + Claude.

## Cursor chat (MCP)

Use your MCP servers directly in **Cursor Chat** or **Agent** mode.

### Setup

A local config is created at `.cursor/mcp.json` (gitignored). It registers all
four servers and sets `cwd` to the project root so probe credentials load from
your `.env` — **no secrets in the JSON file**.

First-time template:

```bash
cp .cursor/mcp.json.example .cursor/mcp.json   # only if mcp.json is missing
```

Ensure `.env` exists with `PROBE_HOST`, `PROBE_SSH_KEY`, etc.

### Activate

1. **Reload Cursor** — `Cmd+Shift+P` → **Developer: Reload Window**
2. Open **Settings → MCP** — all four `netops-*` servers should show connected
3. In chat, try:
   - *"Use netops-perf-probe to measure latency and summarise health."*
   - *"Call diff_against_known and list any unknown devices."*
   - *"Propose a notify action for an unreachable WAN target."*

### Servers registered

| Cursor name | MCP server | Tools |
|-------------|------------|-------|
| `netops-perf-probe` | `perf_probe.py` | `measure_latency`, `measure_throughput` |
| `netops-device-inventory` | `device_inventory.py` | `list_devices`, `identify_devices`, `diff_against_known` |
| `netops-actuator` | `actuator.py` | `propose_action_tool`, `apply_action`, `rollback_block_tool` |
| `netops-flow-monitor` | `flow_monitor.py` | `list_active_flows`, `recent_destinations` (stubs) |

### Troubleshooting

| Problem | Fix |
|---------|-----|
| Server red in MCP settings | Check `.venv` exists (`uv sync`); open server log in MCP tab |
| SSH / probe errors | Verify `.env` and `ssh -i <key> user@<PROBE_HOST>` works in terminal |
| Offline tool test | `uv run python scripts/mcp_smoke_test.py` |
| Mock probes only | Set `"USE_MOCK_PROBES": "true"` in the server's `env` block in `mcp.json` |

