# ChatGPT instructions — Daily Flight Radar trigger

1. Read `AGENTS.md`, `PRODUCT_INTENT.md`, full `flight-radar.yaml` (SSOT wins), then `docs/daily-flight-radar-automation-prompt.md`. Resolve today (Asia/Taipei).
2. On control branch `ops/radar-request`, write `requests/daily.json` (`schema_version: 1`, `mode: canonical_daily`, `requested_date: YYYY-MM-DD`). One claimed acquisition per day: if today's claim/snapshot exists on `history/price-observations`, use the recovery/no-op path. Never create an `operator_reacquisition` request unasked.
3. Submission is not completion. Wait for the triggered workflow's terminal state, then read back final evidence from `history/price-observations` (claim, snapshot, `run-result.json`, `publication-manifest.json`, `data/run-evidence` manifest copies); check Pages dispatch state in the Actions UI.
4. Never judge health by Deal count; use `provider_health` or fail-safe coverage evidence. Keep exact-revalidated Deals in degraded runs.
5. Notify on meaningful new Deals vs prior publication, or any operational/provider/coverage failure. Healthy no-change runs stay silent. Never report success from submission alone.
6. The UI notification toggle is not policy. Do not rerun soak/repair/hardening work.
