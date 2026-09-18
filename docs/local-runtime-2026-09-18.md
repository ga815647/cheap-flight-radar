# Local runtime decoupling — 2026-09-18

## Decision

Retire the GitHub Actions production path. The Daily Radar now runs on the
owner's own machine: an OpenChamber scheduled task (`daily-radar`,
`.agents/loops/daily-radar.md`) invokes `scripts/local_daily_radar.py` about
once per day. History, publication, run evidence and the lock live under
`{CFR_LOCAL_ROOT}` (default `~/.local/share/cheap-flight-radar/`), not in git
refs. Only `.github/workflows/ci.yml` remains; all production workflows are
deleted.

## What changed

- `PRODUCT_INTENT.md` §11: scheduler is the local scheduled run, evidence is
  local and immutable, notification semantics unchanged.
- `flight-radar.yaml`: `publication.orchestration` gained `local_runtime`
  (runner, roots, flock concurrency) and `primary_scheduler:
  openchamber_scheduled_local_run`; `price_history.persistence.durable_store`
  is `local_machine`; `publication.platform` is `local_session_report` with a
  local static-site build; GitHub token/Pages/dispatch keys removed.
- `scripts/local_daily_radar.py`: faithful port of the retired canonical and
  operator workflows — inspect → claim → `production_runtime` acquisition →
  stage-success → restore-publication → local site build → JSON summary.
  Non-blocking flock prevents overlap; the immutable claim still enforces one
  canonical live attempt per Taipei day; repeats are recovery/no-op.
  Acquisition timeout (default 5400s) consumes the claim fail-closed.
- `ftr_handoff` snapshot primitives, RP-02 absolute-low, RP-03 scoped search,
  Deal/anomaly truth, sticky-429 circuit and TWD-0 posture are unchanged.

## What did not change (deliberately)

- No provider, search, scoring, or Deal-truth changes in this package.
- The `chat_web_execution_contract` consumer-surface lane is untouched.
- Historical docs describing the GitHub era remain as evidence; superseded
  live contracts (`daily-flight-radar-automation-prompt.md`,
  `docs/ftr-handoff.md`) carry retirement notices.

## Validation boundary

- Fixture-based unit tests only (`tests/test_local_daily_radar.py` covers
  date refusal, lock contention, and fail-closed blocked-claim paths).
- The first scheduled live run is the production proof; it uses the canonical
  daily identity and consumes that day's one attempt.
- Live validation must never invent a second canonical daily attempt.
