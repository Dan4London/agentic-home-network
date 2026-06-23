# Agentic Home-Network Operations — Project Plan

A small, demoable agent that monitors a home network for **performance**
(bandwidth & latency) and **security** (unexpected / unwanted traffic), reasons
about what it sees with an LLM, and takes closed-loop action. In effect:
autonomous-networks principles — your patent territory — shrunk to lab scale.

It is deliberately scoped to be **buildable in a few garden-leave sessions** and
to read well as a portfolio artifact for Applied AI / FDE / solutions-architect
roles: it shows hands-on MCP, LangGraph, agent design, evals, and a real
closed loop, anchored in your telco domain.

---

## 1. Goal & success criteria

**Primary use cases (your stated priorities):**
1. **Performance** — continuously check bandwidth and latency; spot and explain
   degradation; recommend or apply a remediation.
2. **Security** — establish a baseline of "normal" devices/flows and surface
   traffic that shouldn't be on the network (new/unknown device, unexpected
   destination, odd port, traffic at an odd hour).

**Definition of done (MVP):**
- One agent loop that, on a schedule or on demand, pulls live metrics + flow
  data, reasons over them, and produces a structured **incident report**
  (what, why, severity, recommended action) plus an optional **safe action**.
- A short README with an architecture diagram and a 60–90s screen capture.
- A small **eval set** (10–20 scripted scenarios) the agent is graded against.

**Explicit non-goals (keep scope tight):** no fancy UI, no cloud deployment, no
multi-home/multi-tenant, no ML training (the YOLO/CV work is a *separate*
artifact). Read-only by default; actions are opt-in and guarded.

---

## 2. Architecture (the shape that matters for the CV)

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

- **MCP server(s)** expose the network as a set of typed **tools**. This is the
  centrepiece — it mirrors how you'd expose an OSS to an agent, and it's the
  exact pattern Anthropic/Cohere/Mistral interview for.
- **LangGraph** runs the control loop: perceive → reason → decide → act →
  observe, with state and a clear stopping condition. Closed-loop, not a
  one-shot prompt.
- **LLM** (Claude via API for the "smart" path; a local open-source model as a
  fallback/offline path — reuses what you're already doing in the CV app) does
  the reasoning: classifying anomalies, explaining them in plain English,
  proposing actions.
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

**Hardware fit:** a Raspberry Pi as the always-on probe/collector sitting on the
LAN is ideal and on-brand for you; the agent can run there or on your lab box.

---

## 4. Repository structure

```
agentic-home-netops/
  README.md                 # what it is, diagram, screen-capture, quickstart
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
10–20 scenarios (normal + anomalies) and a grader. README with the diagram and a
short screen capture. *This is the bit that impresses interviewers — you measured
your agent, you didn't just vibe it.*

> Apply at end of **Phase 1** with the README marked "in progress (Phases 0–1
> live; 2–4 in build)". Finishing 2–4 strengthens it but shouldn't gate the
> application.

---

## 6. Tech choices (matched to your stack & the target roles)

- **Language:** Python (the form asks; this proves it).
- **Agent framework:** LangGraph (you already use it; explicit state/edges read
  well).
- **Tooling protocol:** MCP (the differentiator; same pattern as exposing an OSS).
- **LLM:** Claude via API for the primary reasoning path; local open-source model
  as offline fallback (reuses your CV-app setup, and "runs without sending home
  traffic to a cloud LLM" is a nice privacy story for a *security* tool).
- **Typed outputs:** pydantic schemas for `Incident`/`Action` — shows you care
  about reliability, not just prompting.
- **AI-assisted dev:** build it with Claude Code / Cursor — and *say so* in the
  README; for these employers that's a plus.

---

## 7. How to talk about it (CV + interview)

- **CV one-liner (already on the tailored CV):** "A miniature autonomous-networks
  agent that monitors performance and self-heals home routers via MCP tools and a
  LangGraph control loop."
- **Interview framing:** connect it explicitly to your CAROT patent and Nokia
  Orchestration Center work — "this is closed-loop assurance and intent-based
  remediation, the same pattern I drove into Nokia's OSS, rebuilt from scratch on
  MCP + LangGraph so I could touch every layer myself."
- **Have ready:** one anomaly you caught that surprised you; one design trade-off
  (e.g., why local model vs Claude for which path); how you'd scale the same
  pattern to a real CSP network. These are exactly the FDE-interview questions.

---

## 8. Watch-outs

- **Keep actions safe.** Default read-only. Anything that can disrupt your own
  network goes behind dry-run + confirm. Don't demo a live "block" without a
  rollback.
- **Privacy in the write-up.** Redact real MACs / IPs / domains in screenshots.
- **Scope creep is the enemy.** The eval set and README matter more than adding a
  fifth data source. Ship Phases 0–2, then stop and polish.
- **Don't let it eat the job hunt.** Time-box it. The artifact is a means to the
  applications, not a replacement for them.
