# Agentic Home-Network Operations — Project Plan

A small, demoable agent that monitors a home network for **performance**
(bandwidth & latency) and **security** (unexpected / unwanted traffic), reasons
about what it sees with an LLM, and takes closed-loop action — autonomous-network
principles at lab scale.

Scoped to be **buildable in a few focused sessions**, demonstrating MCP,
LangGraph, agent design, evals, and a real closed loop.

---

## 1. Goal & success criteria

**Primary use cases:**
1. **Performance** — continuously check bandwidth and latency; spot and explain
   degradation; recommend or apply a remediation.
2. **Security** — establish a baseline of "normal" devices/flows and surface
   traffic that shouldn't be on the network (new/unknown device, unexpected
   destination, odd port, traffic at an odd hour).

**Definition of done (MVP):**
- One agent loop that, on a schedule or on demand, pulls live metrics + flow
  data, reasons over them, and produces a structured **incident report**
  (what, why, severity, recommended action) plus an optional **safe action**.
- A README with an architecture diagram and a short demo walkthrough.
- A small **eval set** (10–20 scripted scenarios) the agent is graded against.

**Explicit non-goals (keep scope tight):** no fancy UI, no cloud deployment, no
multi-home/multi-tenant, no ML training. Read-only by default; actions are
opt-in and guarded.

---

## 2. Architecture

```
              ┌─────────────────────────────────────────────┐
              │                LangGraph agent              │
              │  perceive → reason (LLM) → decide → act →    │
              │            ↑                         │       │
              │            └──────── observe ◄───────┘       │
              └───────────────┬─────────────────────────────┘
                              │ MCP (tools)
        ┌─────────────────────┼─────────────────────┬───────────────┐
        ▼                     ▼                     ▼               ▼
   perf_probe            flow_monitor          device_inventory   actuator
  (bandwidth/latency)   (who's talking to     (known vs new      (apply guarded
                         whom, ports)          devices)           change)
```

- **MCP server(s)** expose the network as a set of typed **tools** — the same
  pattern used to expose operational systems to agents.
- **LangGraph** runs the control loop: perceive → reason → decide → act →
  observe, with state and a clear stopping condition. Closed-loop, not a
  one-shot prompt.
- **LLM** (Claude via API for the primary path; optional local model as
  fallback/offline) classifies anomalies, explains them in plain English, and
  proposes actions.
- **Guardrails**: actions are allow-listed and require a "dry-run → confirm"
  step. The agent *recommends* freely but only *acts* within a safe envelope.

---

## 3. Data sources / how to actually get the signals

Pick whichever matches your kit; you don't need all of them for the MVP.

**Performance (bandwidth & latency):**
- Latency/jitter/loss: scheduled `ping` / `mtr` to a few targets (gateway, 1.1.1.1,
  a CDN); optional `iperf3` against a LAN target for throughput.
- Throughput / per-device usage: OpenWrt (`luci-app-statistics`, `nlbwmon`,
  `collectd`), or SNMP counters off the router, or a `speedtest-cli` cron.
- If on OpenWrt: its `ubus`/`rpcd` JSON API is a clean thing to wrap as MCP tools.

**Security (unexpected traffic):**
- Device inventory: ARP/neighbour table, DHCP leases, `nmap -sn` sweep → "who is
  on the network". Diff against a known-devices allow-list.
- Flow visibility: router conntrack table, or pi-hole/AdGuard query logs (great
  for "talking to a domain it never has before"), or lightweight NetFlow/IPFIX
  (`softflowd` → `nfdump`) if you want flow records.
- "Shouldn't-be-here" heuristics the LLM reasons over: new MAC/device, new
  external destination ASN/domain, unusual port (e.g., outbound SMTP/IRC/uncommon
  high ports), traffic spikes from a normally-quiet device, activity at 3am.

**Hardware fit:** a Raspberry Pi as the always-on probe/collector on the LAN works
well; the agent can run on the Pi or on a separate orchestrator host.

---

## 4. Repository structure

```
agentic-home-netops/
  README.md                 # what it is, diagram, quickstart
  pyproject.toml
  .env.example              # ANTHROPIC_API_KEY, targets, allow-lists
  mcp_servers/
    perf_probe.py           # tools: measure_latency(), measure_throughput()
    flow_monitor.py         # tools: list_active_flows(), recent_destinations()
    device_inventory.py     # tools: list_devices(), diff_against_known()
    actuator.py             # tools: propose_action(), apply_action()  (guarded)
  agent/
    graph.py                # LangGraph: nodes, edges, state, stop condition
    prompts.py              # system + reasoning prompts
    schemas.py              # pydantic: Incident, Action, Metric (typed outputs)
    policies.py             # allow-lists, safe-action envelope, thresholds
  evals/
    scenarios/              # scripted/recorded inputs (normal + anomalies)
    run_evals.py            # grades agent output vs expected incident/action
    rubric.md
  baseline/
    known_devices.yaml      # MAC/host allow-list
    normal_profile.json     # learned/declared "normal" ranges
```

---

## 5. Build phases (each is a stopping point you can demo)

**Phase 0 — Skeleton (½ day).**
Repo, env, one MCP server (`perf_probe`) exposing `measure_latency()` returning
fake/static data, a LangGraph loop that calls it and prints a result. Proves the
plumbing end-to-end. *Demoable: "agent calls a tool and reasons over the result."*

**Phase 1 — Performance loop (1 day).**
Real latency/throughput probes. LLM classifies "healthy / degraded / down",
explains why, emits a typed `Incident`. Add 3–4 thresholds in `policies.py`.
*Demoable: unplug/throttle something, watch it detect and explain.*

**Phase 2 — Security / unexpected traffic (1–2 days).**
`device_inventory` + `flow_monitor` tools. Baseline of known devices and normal
destinations. Agent flags a new device or an odd destination and explains the
"why this is suspicious" in plain English. *Demoable: join a new device → it gets
flagged with reasoning.*

**Phase 3 — Closed loop + guardrails (1 day).**
`actuator` with a dry-run/confirm pattern (e.g., propose blocking a device,
rate-limiting, or raising a notification) inside a safe envelope. Agent now
*acts*, not just reports. *Demoable: end-to-end perceive→act with a human-in-loop
confirm.*

**Phase 4 — Evals + polish (1 day).**
10–20 scenarios (normal + anomalies) and a grader. README with the diagram and
a demo script. *Measurable agent behaviour, not ad-hoc testing.*

---

## 6. Tech choices

- **Language:** Python
- **Agent framework:** LangGraph (explicit state/edges)
- **Tooling protocol:** MCP
- **LLM:** Claude via API for the primary reasoning path; local open-source model
  as offline fallback (privacy-friendly option for a security tool)
- **Typed outputs:** pydantic schemas for `Incident`/`Action`
- **AI-assisted dev:** built with Cursor + Claude

---

## 7. Watch-outs

- **Keep actions safe.** Default read-only. Anything that can disrupt your own
  network goes behind dry-run + confirm. Don't demo a live "block" without a
  rollback.
- **Privacy in the write-up.** Redact real MACs / IPs / domains in screenshots.
- **Scope creep is the enemy.** The eval set and README matter more than adding a
  fifth data source. Ship Phases 0–2, then stop and polish.
- **Time-box it.** Finish a working demo, then polish — don't keep adding features.
