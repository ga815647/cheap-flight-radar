# Production operationalization — 2026-08-14

## Status

This checkpoint operationalizes the already-proven production Radar without reopening search-recall repair, provider substrate selection, the final production soak, or 429 hardening.

The production data path remains:

`Google Flight Deals → gflights exact/flexible/multi-city → immutable price history → schema-v2 publication manifest → Radar Pages`.

ChatGPT remains the scheduler/orchestrator. GitHub Actions remains short-lived deterministic compute, persistence plumbing, Gate, and Pages deployment. There is no GitHub cron, daemon, queue, or new durable state service.

## What was still missing after PR #27

The merged runtime/publication stack could already perform one correct production acquisition and emit a history snapshot plus publication manifest, but routine operation still had four operational gaps:

1. there was no stable ChatGPT-triggerable daily production entrypoint in the repository;
2. nothing durably prevented two canonical live acquisitions on the same Asia/Taipei day;
3. a publication push made with a workflow `GITHUB_TOKEN` cannot be relied on to recursively trigger another workflow/Pages build, so `presentation_manifest_push` alone was insufficient for an Actions-owned publication write;
4. if history persistence succeeded but active publication failed, the next run needed a way to rebuild publication without querying airfare providers again.

Those are orchestration/persistence gaps only. They do not justify another provider, a scheduler inside Actions, or another search architecture.

## Canonical daily trigger

The stable workflow is `.github/workflows/canonical-production-radar.yml`.

Its automated trigger is one ChatGPT-owned control write:

- control branch: `ops/radar-request`;
- request file: `requests/daily.json`;
- request schema: `{"schema_version": 1, "mode": "canonical_daily", "requested_date": "YYYY-MM-DD"}`;
- the requested date must equal the current Asia/Taipei date.

The control branch is disposable trigger transport, not Radar state. Before the daily request, ChatGPT may force-reset this dedicated branch to current `main`, then create the request file. The reset removes any prior request and therefore cannot request acquisition; the workflow explicitly treats a missing request file as a no-op. This keeps the trigger workflow current without putting daily report commits on `main`.

`workflow_dispatch` remains available as an explicit operator/recovery entrypoint, but there is no `schedule:` trigger in the workflow.

## One live acquisition attempt per local day

Before any provider call, the workflow inspects `history/price-observations` and then persists an immutable daily acquisition claim:

`data/production-attempts/YYYY/MM/DD/canonical.json`

The claim records the requested local date, claim time, workflow run id/URL, and trigger SHA. It is committed **before** `python -m cheap_flight_radar.production_runtime` starts live acquisition.

The rule is strict:

- no claim and no canonical snapshot → acquisition may run;
- claim exists but no canonical snapshot → the prior acquisition attempt did not finish persistence; fail closed and **do not query providers again that day**;
- one canonical snapshot exists → never reacquire; use publication recovery state instead;
- more than one canonical production snapshot exists for the local day → fail closed rather than guessing which run is canonical.

Actions concurrency additionally serializes canonical production workflow runs, but the durable claim is the actual cross-run guard.

## Durable success and publication recovery

A successful runtime already emits:

- one immutable price-history snapshot;
- one schema-v2 publication manifest;
- one complete `run-result.json` containing Deals, Signals, coverage, execution evidence, and provider failures.

The operational workflow validates these outputs and persists the snapshot plus an immutable recovery bundle on the existing history ref:

`data/run-evidence/YYYY/MM/DD/{radar_run_id}/run-result.json`

`data/run-evidence/YYYY/MM/DD/{radar_run_id}/publication-manifest.json`

The recovery bundle is not a second fare-history database and is not active presentation state. It exists only so a publication failure can be retried from already-acquired evidence without another live airfare search.

After durable history/recovery evidence exists, the workflow restores the identical manifest onto `publication/radar-reports`, smoke-builds the static site against current `main` plus history, and only then pushes the active manifest.

Recovery states are therefore:

- snapshot + recovery manifest, active manifest missing → republish only;
- active manifest present and identical to recovery evidence → no acquisition; Pages may be dispatched again;
- active manifest differs from recovery evidence → fail closed;
- snapshot exists without recovery evidence → fail closed; never synthesize the missing manifest and never reacquire merely to repair publication.

A runtime exception before successful snapshot persistence still leaves the pre-acquisition claim and workflow run URL as durable evidence that the day's one canonical acquisition attempt was consumed.

## Minimal Pages trigger

`radar-pages.yml` retains both its existing push trigger and `workflow_dispatch`.

For publication writes performed by the canonical production workflow, the active manifest push uses `GITHUB_TOKEN`. GitHub intentionally suppresses recursive workflow triggering from most events created by that token, so the canonical workflow does **not** assume that its own push will start Pages. After the manifest is present and the local smoke build passes, it explicitly dispatches `radar-pages.yml` with the same workflow token and `actions: write` permission.

This is the minimal reliable trigger:

1. persist history/recovery evidence;
2. stage and smoke-build the active manifest;
3. push the active manifest;
4. explicitly `workflow_dispatch` Radar Pages.

External/user/connector pushes to the publication ref may still use the existing push trigger. No second publication workflow or one-shot scaffold is required.

## Failure semantics

Acquisition and publication fail closed independently:

- acquisition failure after claim: no history snapshot is invented, no publication manifest is invented, and no same-day reacquisition occurs;
- success-evidence validation failure: active publication is not written;
- publication smoke-build failure: durable acquisition/recovery evidence remains, active publication is not advanced;
- publication push or Pages-dispatch failure: a later recovery trigger reuses the immutable recovery manifest and does not query providers;
- manifest divergence or ambiguous same-day snapshots: stop and require code/operator repair rather than guessing.

GitHub Actions artifacts remain transient convenience evidence only. The claim, price snapshot, and successful run recovery bundle are repository-durable evidence on `history/price-observations`.

## Legacy Issue #2–#5 disposition

The 2026-08-09 issue set predates the production substrate bake-off and now describes a provider architecture that is no longer authoritative.

### Issue #2 — credentialed Skyscanner/FlyAI provider validation

**Superseded / close as not planned.** The production bake-off selected the keyless Google substrate instead: Google Flight Deals for destination-free discovery/anomaly truth and `gflights==0.3.0` exact/flexible/multi-city for completion. Skyscanner partnership/quota access and FlyAI are not prerequisites for the current production architecture. Re-running the old credential basket would not satisfy a current product gap.

### Issue #3 — source router and provider-agnostic collector layer

**Completed under the current architecture.** The repository now has `source_router`, provider-independent airfare normalization, explicit provider/fallback/coverage state, deterministic adapter tests, and current Google routing in `flight-radar.yaml`. The old Skyscanner/FlyAI initial routing table is historical research, not the selected production plan.

### Issue #4 — normalized schema plus SQLite history

**Superseded / close as not planned in its SQLite form.** The normalized fare/verification schema exists, but durable history deliberately converged on append-only JSON snapshots on `history/price-observations`. SQLite would create a second durable state mechanism without solving a current production requirement. Comparable historical metrics are derived from immutable snapshots.

### Issue #5 — daily profile runner and unified report pipeline

**Completed by the current production runtime plus this operationalization.** TPE/TSA/RMQ/KHH use one shared production path; Japan/Korea/China/other Asia-Oceania are priority slices; exact/flexible/multi-city completion, immutable history, schema-v2 Deals/Signals publication, and deterministic Pages generation are implemented. This checkpoint supplies the missing once-daily ChatGPT trigger/idempotency/recovery protocol. The old Skyscanner/FlyAI provider assumptions are superseded.

## Routine operating contract

For normal unattended use:

1. ChatGPT runs once per Asia/Taipei day.
2. ChatGPT refreshes/creates the dedicated `ops/radar-request` control branch from current `main` and writes that day's `requests/daily.json`.
3. The canonical workflow validates that the request is for today.
4. It inspects history/publication state.
5. If and only if no daily claim/snapshot exists, it persists the claim and performs one canonical production acquisition.
6. Successful acquisition is durably committed as immutable price history plus recovery evidence.
7. Publication is restored from that evidence, smoke-built, and pushed.
8. Radar Pages is explicitly dispatched.
9. Any retry on the same date is recovery/no-op only; it may never start a second live acquisition.

Do not add GitHub cron, another provider, a daemon, a queue, or a database/state service to operate this protocol.

## Explicit same-day operator reacquisition

The once-per-day rule is a routine automation rule, not a prohibition on a user-requested same-day refresh. When the user or operator explicitly requests another live acquisition, use the separate operator control path rather than bypassing or mutating the canonical daily claim.

- control branch: `ops/radar-operator-request`;
- request file: `requests/operator.json`;
- request mode: `operator_reacquisition`;
- every intentional attempt requires a unique explicit `request_id`;
- the request id gets its own immutable pre-acquisition claim under `data/operator-attempts/YYYY/MM/DD/{request_id}.json`;
- operator run ids use `operator-radar-{request_id}-...`, so they append real observations to price history without entering or replacing the `production-radar-*` canonical daily namespace;
- duplicate execution of the same `request_id` is recovery/no-op only and may not reacquire;
- a new live attempt requires a new explicit request id, so there is no automatic retry loop;
- canonical and operator acquisitions share the same Actions concurrency group so they cannot hit the provider concurrently;
- successful operator runs persist the same immutable snapshot + recovery bundle, may publish as the newest Radar run, smoke-build, and explicitly dispatch Radar Pages.

This path is for explicit refreshed evidence, diagnosis, or provider-health comparison. It must never be scheduled automatically and does not relax the routine canonical one-attempt guard.

