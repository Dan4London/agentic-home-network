# Eval rubric

Grade each scenario on weighted checks:

1. **Detection** — correct `overall_health` / `security_status`
2. **Incident count** — expected number of incidents raised
3. **Category** — performance vs security incidents present
4. **Severity** — warning / critical as expected
5. **Action** — recommended `notify` (etc.) when applicable
6. **Explanation** — root cause contains expected phrases

**Pass threshold:** 80% per scenario; all scenarios must pass for a green run.

```bash
uv run netops-eval
uv run netops-eval --scenario unknown_laptop
uv run netops-eval --json
```
