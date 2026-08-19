# Family Trip Radar downstream handoff

This document defines the CFR-owned machine contract consumed by Family Trip Radar (FTR). It does **not** change CFR Deal qualification or ranking. `PRODUCT_INTENT.md` remains durable human intent and `flight-radar.yaml` remains the operational SSOT; this document explains the handoff mechanics.

## Product boundary

CFR owns airfare discovery, exact airfare truth, Deal/Signal provenance, provider health and acquisition coverage. FTR owns home-to-home access, lodging, effective usable time, child fit and whole-trip recommendation reasoning.

The handoff therefore carries airfare facts and provenance only. It must never export CFR anomaly strength as an FTR whole-trip score.

## Schema and modes

Current schema: `1.0`.

Schema versions use `MAJOR.MINOR`:

- adding an optional compatible field may increment MINOR;
- removing a field, changing required structure, or changing field meaning requires MAJOR;
- consumers fail closed on an unsupported MAJOR.

Run modes:

- `canonical_daily` — routine canonical feed;
- `scoped_search` — user/Search-mode date-scoped acquisition; immutable but never advances canonical `latest.json`;
- `same_day_recovery` — explicit post-repair reacquisition; may advance canonical latest after it satisfies the same consumability contract.

## Durable paths

Immutable snapshot:

`data/ftr-feed/YYYY/MM/DD/<run_id>.json`

Canonical mutable manifest:

`data/ftr-feed/latest.json`

Scoped-search manifest:

`data/ftr-feed/scoped/<run_id>.json`

The history ref is the durable Git-backed evidence substrate. Actions artifacts are not part of this contract.

## Snapshot contract

Every snapshot contains at least:

- `schema_version`;
- `run_id`;
- `mode`;
- `observed_at`;
- `generated_at`;
- `producer_commit_sha`;
- `terminal_state`;
- `coverage_state`;
- `freshness_state`;
- normalized coverage/provenance;
- `candidate_counts`;
- `opportunities` with retained variants.

A snapshot is consumable only when `terminal_state=success`, its schema is supported, and producer coverage has not collapsed. A truthfully partial fresh run may be consumable with `coverage_state=degraded` / `freshness_state=degraded`.

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

Generic CFR Signals are not automatically eligible. `absolute_low_non_deal` must be explicitly selected upstream by the dedicated bounded price-floor producer path.

## Coverage truth

Deal count is never provider-health evidence. The handoff carries explicit execution/coverage state so downstream zero candidates cannot be mistaken for proof of a healthy zero-opportunity market.

At minimum, downstream consumers can see provider health, origin coverage, market coverage metrics and provider/operational failures. The producer must represent partial coverage as degraded rather than silently dropping failed slices.

## Atomic publication

Publication order is strict:

1. build normalized snapshot from terminal run evidence;
2. validate schema and consumability;
3. write immutable snapshot;
4. compute SHA-256 of the exact snapshot bytes;
5. construct manifest containing snapshot pointer + run metadata + checksum;
6. write/replace manifest last.

If any step before manifest publication fails, the previous canonical `latest.json` remains authoritative.

A snapshot path is immutable. Reusing an existing path is allowed only when the bytes are identical.

## Consumer fail-closed behavior

A consumer rejects the feed when any of these occur:

- missing manifest;
- unsupported schema major;
- manifest not terminal success;
- referenced snapshot missing;
- SHA-256 mismatch;
- snapshot schema invalid;
- manifest/snapshot run identity mismatch.

The consumer does not guess, patch or fabricate missing producer fields.

## Degraded and stale behavior

A broad provider/coverage collapse is not published as a new fresh consumable snapshot. The last-good canonical snapshot may remain available as historical/stale reference, but FTR must not present it as current bookable evidence.

A partially degraded but fresh run may publish a degraded snapshot when surviving evidence is still valid. FTR may use those fresh variants while clearly reporting incomplete coverage.

Persistent `repair_required` incident state and automatic same-day recovery orchestration are separate operational layers built on top of this producer contract; they must never mutate stale evidence into fresh evidence.

## GitHub Actions artifact policy

Production correctness depends on Git-backed evidence, not Actions artifact storage.

- success does not require uploading an artifact bundle;
- failure debug upload is best-effort only;
- debug artifacts should be narrow and short-retention;
- artifact quota exhaustion must not change acquisition truth or downstream handoff state;
- raw provider dumps, large HTML and entire runtime output directories do not belong in the FTR feed.

## Activation sequence

The contract primitive and tests may land before runtime activation. Normal production handoff activation should occur only after:

1. the operational SSOT contains the handoff policy;
2. the bounded absolute-low non-Deal producer path is explicit and tested;
3. canonical success staging writes snapshot + manifest to the durable history ref;
4. scoped Search-mode evidence cannot advance canonical latest;
5. recovery semantics are tested;
6. the full repository unit-test gate and exact-head PR checks pass.
