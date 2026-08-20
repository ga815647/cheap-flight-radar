# Family Trip Radar downstream handoff

This document defines the CFR-owned machine contract consumed by Family Trip Radar (FTR). It does **not** change CFR Deal qualification or ranking. `PRODUCT_INTENT.md` remains durable human intent and `flight-radar.yaml` remains the operational SSOT; this document explains the handoff mechanics.

## Product boundary

CFR owns airfare discovery, exact airfare truth, Deal/Signal provenance, provider health and acquisition coverage. FTR owns home-to-home access, lodging, effective usable time, child fit and whole-trip recommendation reasoning.

The handoff therefore carries airfare facts and provenance only. It must never export CFR anomaly strength as an FTR whole-trip score.

## Schema and modes

Current snapshot/manifest schema: `2.0`.

RP-01 advances the pre-activation contract from `1.0` to `2.0` because coverage slice state and freshness meaning are now stricter: provider/surface/origin/market states must come from execution evidence, and `stale_reference` is a mutable current-usability interpretation rather than an immutable snapshot state. This is a semantic change, not an optional-field-only addition.

Schema versions use `MAJOR.MINOR`:

- adding an optional compatible field may increment MINOR;
- removing a field, changing required structure, or changing field meaning requires MAJOR;
- consumers fail closed on an unsupported MAJOR.

Run modes:

- `canonical_daily` — routine canonical feed;
- `scoped_search` — user/Search-mode date-scoped acquisition; immutable but never advances canonical `latest.json`;
- `same_day_recovery` — explicit post-repair reacquisition identity; a future producer transition may advance canonical latest only after the recovery satisfies the consumability/recovery contract.

`operator_reacquisition` is a separate CFR acquisition identity. It is **not** an FTR snapshot mode and cannot impersonate `same_day_recovery` for repair clearing.

## Durable paths

Immutable snapshot:

`data/ftr-feed/YYYY/MM/DD/<run_id>.json`

Canonical mutable manifest:

`data/ftr-feed/latest.json`

Scoped-search manifest:

`data/ftr-feed/scoped/<run_id>.json`

Mutable current-status / repair incident envelope:

`data/ftr-feed/current-status.json`

These paths live on the Git-backed CFR evidence ref defined by `flight-radar.yaml`. Actions artifacts are not part of correctness or persistence.

## Immutable snapshot contract

Every snapshot contains at least:

- `schema_version`;
- `run_id`;
- `mode`;
- `observed_at`;
- `generated_at`;
- `producer_commit_sha`;
- `terminal_state`;
- `coverage_state`;
- snapshot-generation `freshness_state`;
- normalized execution/coverage/provenance;
- `candidate_counts`;
- `opportunities` with retained variants.

Snapshot freshness is historical truth at generation time and is limited to:

- `fresh` — complete current producer coverage;
- `degraded` — current, usable surviving evidence with truthfully incomplete coverage.

`stale_reference` is deliberately **not** a valid immutable snapshot freshness value. If a later producer attempt fails, an old snapshot remains byte-for-byte unchanged; the mutable current-status envelope is what says that the preserved last-good feed is now only a stale reference.

A snapshot is consumable only when `terminal_state=success`, its schema is supported, and producer coverage has not collapsed. A truthfully partial fresh run may be consumable as `coverage_state=degraded` / `freshness_state=degraded`. Broad producer collapse is not a new consumable snapshot.

## Slice-faithful coverage truth

The FTR handoff carries explicit provider, surface, origin and market states. The only exported slice states are:

- `succeeded`;
- `failed`;
- `not_attempted`.

The producer normalizes these states from real CFR execution/coverage evidence. It must not infer success from Deal count, candidate count, the mere absence of `provider_failed`, or an unknown source status.

Key rules:

- `Deal` count is never provider-health or coverage truth.
- Surface state comes from execution attempts/provider calls/outcomes/suppression/unsupported evidence. A complete-but-empty provider response may still be an execution success; zero records by itself is not a technical failure.
- Origin state preserves the producer's attempted/degraded/failed/not-attempted evidence. A degraded or failed origin cannot become `succeeded` because some other origin worked.
- Market state may use the shared destination-free origin sweep as its execution basis; market candidate counters remain metrics only and never decide success.
- Provider identity must be traceable to normalized record, failure or explicit provider-execution evidence. The handoff does not hard-code `gflights` as a universal truth.
- Multiple providers require explicit per-provider execution evidence; aggregate health is insufficient to invent individual provider state.
- Unknown or contradictory execution evidence fails closed.
- Optional surfaces may truthfully be `not_attempted`. Required discovery-surface gaps degrade/fail the run rather than becoming silent success.

## Opportunity and variant identity

FTR grouping is destination-side route-shape based.

Examples:

- `KIX -> KIX` is one opportunity;
- `KIX -> UKB` is another;
- `KIX -> FUK` is another.

Taiwan gateway, airline, flight schedule, date pair and fare are **variant dimensions**, not opportunity keys. A mixed Taiwan gateway therefore remains under the same destination-side route shape.

Each retained variant carries:

- `candidate_kind`: `deal` or `absolute_low_non_deal`;
- exact complete airfare TWD;
- observed time;
- outbound and return dates;
- actual Taiwan outbound and return gateway;
- destination-side arrival/departure airport shape;
- airline/leg data when observed;
- verification state;
- evidence/provenance reference.

Generic CFR Signals are not automatically eligible. `absolute_low_non_deal` is selected only by the dedicated RP-02 price-floor producer from the current run's explicit exact non-Deal outcome pool. The selector does not scan or rewrite the generic Signal journal and performs no additional acquisition.

The machine policy lives at `ftr_handoff.absolute_low_non_deal_producer` in `flight-radar.yaml`. Eligibility requires a non-Deal `exact_revalidated_candidate` with a positive complete outbound+return fare, exact dates, the same strict >24-hour minimum-away rule already used by CFR production, concrete/reproducible itinerary identity, a current timezone-aware observation that is not later than the run timestamp, and existing CFR revalidation/provenance evidence. The minimum-away threshold is deterministically tied to `return_windows_policy.formal_deal_minimum_away_hours`; weak seeds, cached/promotional hints, incomplete/non-converged/non-exact/stale or future-dated evidence, <=24-hour destination stays, and anything matching a formal Deal identity fail closed.

The producer is deliberately bounded independently of CFR display/publication limits: it selects at most five variants, ordered by complete airfare ascending and then exact dates, Taiwan origin, destination-side route shape and record ID. This is a downstream handoff candidate set, not a CFR leaderboard and not an anomaly ranking. Existing qualifying route identity, including an already-produced open-jaw shape or different Taiwan return gateway, is retained without adding RP-06 search/eligibility expansion.

## Canonical RP-04 runtime activation

RP-04 activates the downstream FTR producer **inside the existing canonical transaction**; it does not create another scheduler or acquisition pipeline. The existing canonical daily claim, `production_runtime`, CFR `stage-success`, immutable `data/price-history`, run-evidence and publication recovery remain authoritative CFR behavior.

The production workflow checks out the application from current `main` into `_app` and resolves `git -C _app rev-parse HEAD`. That exact 40-hex checkout SHA is the FTR `producer_commit_sha`. The ops request/control-branch trigger SHA remains claim/control provenance only and must never be substituted for the producer application SHA.

FTR staging runs only after legitimate CFR success evidence has already been persisted on the evidence ref. Therefore a later FTR serialization/checksum/current-status failure cannot roll back or delete CFR price-history/run-evidence and does not silently replace CFR publication semantics.

Canonical FTR publication order is strict:

1. canonical acquisition process has completed and durable CFR `run-result.json` exists;
2. build mode `canonical_daily` snapshot from that durable run truth;
3. validate schema, terminal semantics, coverage/freshness and candidate contract;
4. write immutable FTR snapshot first;
5. calculate SHA-256 from the **exact persisted snapshot bytes** and match it to the manifest checksum;
6. write/replace canonical `data/ftr-feed/latest.json` only after the snapshot write;
7. reload through `load_manifest_snapshot`, rechecking checksum and run identity (plus producer SHA at the RP-04 runtime boundary);
8. only then write `data/ftr-feed/current-status.json` from that exact reloaded latest snapshot;
9. commit FTR state to the same configured Git evidence ref as CFR evidence.

The RP-01 low-level `stage_snapshot` writes snapshot before manifest. RP-04 wraps the complete snapshot→manifest→reload→current-status sequence with a previous-latest byte guard: if anything after a tentative manifest write fails, the previous latest bytes are restored exactly (or the newly-created latest is removed when there was no last-good) before `repair_required` is recorded. An already-written immutable snapshot is never rewritten or deleted.

Healthy complete coverage yields `fresh`. Truthfully partial but consumable coverage yields `degraded`. A healthy zero-opportunity run is valid; candidate/Deal count never decides health.

## Durable current status and `repair_required`

`current-status.json` is mutable current usability state; it is **not** historical fare evidence. It records at least:

- current producer status/health interpretation;
- boolean `repair_required`;
- `current_freshness_state` (`fresh`, `degraded`, `stale_reference`, or `unavailable` when no last-good exists);
- preserved `last_good` run, snapshot path, manifest path and SHA-256;
- active repair incident set time;
- trigger/latest failed attempt identity, terminal/validation state and evidence reference;
- deterministic clearing contract.

On a failed or invalid new canonical producer attempt:

1. do **not** rewrite/delete the last-good immutable snapshot;
2. do **not** advance/rewrite/delete canonical `latest.json`;
3. persist a compact immutable `ftr-failed-attempt.json` beneath the existing `data/run-evidence/YYYY/MM/DD/<attempt>/` namespace;
4. use that Git-backed path as `latest_failed_attempt.evidence_ref`;
5. persist/update `current-status.json` with `repair_required=true`;
6. preserve the last-good pointer/checksum;
7. expose that preserved feed only as `current_freshness_state=stale_reference` (or `unavailable` if no last-good exists).

This covers acquisition-process failure and downstream FTR invalid/staging failure. Actions artifacts/logs are debug-only and never supply the durable failure truth.

The preserved snapshot's own `freshness_state` remains exactly what it was when produced. A later failure never rewrites historical bytes from `fresh` to `stale_reference`.

Scoped-search and operator-reacquisition failures cannot create/replace the canonical FTR repair incident. They remain distinct identities and cannot alter canonical current-state semantics merely by existing.

## Repair clearing contract / RP-05 boundary

RP-01 defines and tests the transition contract, but RP-04 deliberately does **not** implement live recovery acquisition/control orchestration.

For the current contract, an active `repair_required` incident clears only when durable canonical evidence proves all of the following:

- transition identity is `same_day_recovery`;
- canonical latest points to that exact recovery run;
- terminal state is success;
- schema major is supported;
- snapshot validates;
- coverage is complete;
- snapshot freshness is `fresh`;
- producer health is healthy;
- manifest/snapshot run identity matches;
- SHA-256 of immutable snapshot bytes matches the manifest.

The incident does **not** clear merely because:

- an ordinary later `canonical_daily` run succeeds;
- a workflow is green;
- an `operator_reacquisition` exists;
- a `scoped_search` exists;
- publication recovery succeeded;
- a stale/last-good snapshot still exists.

While repair is active, ordinary `canonical_daily` staging cannot advance canonical FTR latest and cannot masquerade as `same_day_recovery`. Live same-day recovery orchestration remains RP-05.

## Consumer fail-closed behavior

A consumer rejects the feed when any of these occur:

- missing manifest;
- unsupported schema major;
- manifest not terminal success;
- referenced snapshot missing;
- SHA-256 mismatch;
- snapshot schema invalid;
- manifest/snapshot run identity mismatch;
- unknown or inconsistent coverage state.

When `repair_required=true`, a consumer must consult `current-status.json`: preserved last-good bytes may be inspected only as a stale reference/current fallback, never as current bookable evidence.

The consumer does not guess, patch or fabricate missing producer fields.

## GitHub Actions artifact policy

Production correctness depends on Git-backed evidence, not Actions artifact storage.

- success does not require uploading an artifact bundle;
- failure debug upload is best-effort only;
- debug artifacts should be narrow and short-retention;
- artifact quota exhaustion must not change acquisition truth or downstream handoff state;
- raw provider dumps, large HTML and entire runtime output directories do not belong in the FTR feed.

## Activation sequence

RP-01 established the contract/repair primitives, RP-02 added the bounded absolute-low non-Deal producer, RP-03 added isolated scoped-search acquisition, and **RP-04 activates canonical FTR producer staging** on the existing canonical workflow/evidence transaction.

This is not final FTR launch readiness. RP-05 same-day recovery orchestration and later readiness packages (including RP-06/RP-07/RP-08 as tracked under parent #37) remain pending. RP-04 performs no live acquisition or live proof by itself.
