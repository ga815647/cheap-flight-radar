# Fixed-watch persisted artifact interface — 2026-08-11

Status: implementation contract for Issue #10 / PR #11. `flight-radar.yaml` remains the policy SSOT; this document explains how the existing ChatGPT-orchestrated fixed-watch policy is carried across radar runs.

## 1. Architecture boundary

ChatGPT remains the primary radar scheduler/orchestrator. GitHub Actions remains an on-demand deterministic execution / crawler / Gate backend.

There is deliberately:

- no independent GitHub cron;
- no Actions-side cadence planner;
- no mutable branch or repository file used as a hidden scheduler clock;
- no opportunistic source allowed to repair failed fixed-watch coverage.

The caller decides when a radar run occurs, reads prior successful state, computes due fixed watches, dispatches GitHub execution only when needed, then consumes the returned manifest before continuing to open-Web discovery and downstream fare work.

## 2. Persistence backend

The existing `.github/workflows/fixed-watch-run.yml` persists every requested execution as a GitHub Actions artifact:

- artifact name: `fixed-watch-run-${radar_run_id}`;
- contained file: `artifacts/fixed-watch-run.json`;
- retention: 14 days.

Current fixed-watch freshness thresholds are 3 hours and 6 hours, so the artifact retention window is intentionally much longer than the state required for cadence reuse. If artifacts are unavailable or have expired, the orchestrator has no trustworthy prior-success evidence and the existing due planner conservatively returns `due_now`.

Artifact persistence therefore cannot create false freshness: absence of evidence makes a source due rather than silently reusing stale state.

## 3. Reader / state resolver

`cheap_flight_radar.fixed_watch_state` reads one or more extracted `fixed-watch-run.json` files and produces one current orchestration state object.

Example:

```bash
python -m cheap_flight_radar.fixed_watch_state \
  --manifest artifacts/run-a/fixed-watch-run.json \
  --manifest artifacts/run-b/fixed-watch-run.json \
  --now 2026-08-11T17:12:00+08:00 \
  --output artifacts/fixed-watch-state.json
```

The output contains:

- `plan`: the existing cadence plan for every source in the current SSOT registry;
- `due_watch_ids`: only sources that require a new deterministic execution;
- `reused_successes`: exact prior `attempt_id`, source, completion time, source run id, and observation count used for fresh reuse;
- `normalized_observations`: observations belonging only to the selected latest successful attempts that are still fresh.

The current registry drives planning. Attempts for sources that existed in older artifacts but are no longer fixed watches are ignored by the cadence planner.

## 4. Manifest compatibility and integrity

The durable checkpoint runner already emitted the v1 JSON field contract before this reader existed. Therefore a manifest without an explicit `schema_version` is interpreted as schema v1 for backward compatibility; an explicit unsupported version is rejected.

The reader validates before a manifest is allowed to affect freshness:

- timestamps must be timezone-aware ISO-8601 values;
- requested watch ids must exactly match the source ids represented by attempts;
- one source has at most one terminal attempt inside one manifest;
- every observation must have a source attempt in the same manifest;
- each attempt's `observation_count` must equal the source observations actually present;
- a failed attempt cannot contain normalized observations.

Cadence still uses the latest **successful** attempt only. A newer `blocked`, `unavailable`, `fetch_failed`, or `parse_failed` attempt does not refresh the due clock.

When several persisted manifests contain successful attempts for one source, only the exact latest successful attempt selected by the cadence planner contributes normalized observations to the current ChatGPT radar run. Older observations remain historical evidence but are not silently mixed into a fresh-source snapshot.

## 5. ChatGPT radar-run protocol

For each scheduled ChatGPT radar run:

1. Read the current fixed-watch registry from the repo SSOT.
2. List/download recent non-expired fixed-watch run artifacts from the intended production execution ref and extract their manifests.
3. Resolve current state with `fixed_watch_state` (or the same strict contract in the caller).
4. If `due_watch_ids` is empty, reuse the exact `attempt_id` values and their normalized observations; do not start an unnecessary GitHub execution.
5. If one or more watches are due, dispatch `.github/workflows/fixed-watch-run.yml` with only those ids and the caller's radar-run id.
6. Download the resulting artifact, add its manifest to the state set, and resolve again. Any source that remains due / failed is reported as incomplete fixed-watch coverage rather than repaired by another source.
7. Merge fresh fixed-watch sightings into ChatGPT's opportunistic public-Web discovery while retaining separate provenance.
8. Promote serious candidates into the existing deep-search/source-router path. Unconfigured provider stages remain explicitly unconfigured rather than silently degrading.
9. Revalidate serious exact itineraries where a suitable source exists, preserve unknown fare components as unknown, then produce the final report with fixed-watch coverage status.

GitHub Actions never decides when step 1 occurs and never loops on a cadence by itself.

## 6. Live backward-compatibility evidence

The earlier one-shot live integration run `31473909367` persisted an artifact containing:

- a successful China Airlines attempt with 8 normalized observations;
- a successful PTT Japan_Travel attempt with zero matching current posts (valid success under the board parser contract);
- a Tigerair attempt that ended `parse_failed` before Tigerair was demoted from the fixed registry.

At approximately 17:12 Asia/Taipei on 2026-08-11, both current-registry successes from that artifact were less than one hour old. Under the current 6h / 3h thresholds, a ChatGPT radar run should therefore reuse both exact successes and dispatch **no** new fixed-watch execution. The obsolete Tigerair attempt does not participate in current fixed-watch planning.

This is the intended compatibility behavior for artifacts created before the state reader was added.
