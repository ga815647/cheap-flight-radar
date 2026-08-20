# FTR scoped-search acquisition (RP-03)

Status: implemented pre-activation. `ftr_handoff.canonical_activation.enabled` remains `false`.

## Purpose

`scoped_search` is the on-demand CFR acquisition mode used by Family Trip Radar Search Mode when the user supplies one or more `availability_windows`. It is not a second airfare product, not a canonical daily run, not operator reacquisition, and not same-day recovery.

The runtime is `cheap_flight_radar.scoped_search`. It has no scheduler and this package adds no GitHub cron or production launch path.

## Request and identity

A request has an explicit `request_id`, one or more availability windows, and an explicit bounded execution policy. Duration is optional. When duration is absent, the planner injects **no FTR fixed trip duration**. In particular, adjacent-date / one-calendar-night pairs remain queryable. Calendar-date difference is only a planning dimension and is never treated as proof of CFR's minimum destination stay.

CFR eligibility remains authoritative after exact revalidation: `_minimum_away_satisfied(exact)` requires actual arrival-to-departure destination stay to be strictly greater than 24 hours when complete provider segment timing is available, and otherwise follows the existing fail-closed CFR fallback. Therefore a one-calendar-night exact itinerary may qualify when its observed destination stay is `>24h`, while an observed stay `<=24h` cannot qualify. An explicit request duration such as `min_nights=2` is still a hard query constraint and excludes adjacent-date pairs. `max_budget_twd`, when supplied, is a request-local hard filter only.

The request is normalized into a SHA-256 fingerprint. The deterministic run identity is:

`ftr-scoped-{request_id}-{request_fingerprint[:12]}`

The same request input therefore produces the same fingerprint, plan ID, task IDs, ordering, and truncation. An already-published identical fingerprint is replayed without provider acquisition. Reusing the same `request_id` for a different fingerprint fails closed rather than overwriting or masquerading as the earlier intent.

## Window-constrained acquisition

The producer reuses CFR source routing and the existing gflights adapter. Destination-free discovery uses the existing Google Flight Deals route, but every provider request carries an `anchor_departure` and `anchor_return` generated inside one supplied availability window. Each discovery task belongs to exactly one window.

The planner never treats `search.horizon_days` as the scoped window and never runs the canonical 120-day acquisition followed by a result-only filter.

The current `Explore`, `cheapest_dates`, and RP-06 open-jaw expansion surfaces cannot establish arbitrary supplied-window coverage under the current adapter contract, so RP-03 does not call them. Their scoped coverage is explicitly `not_attempted`. A future provider capability must first add a real full-window constraint before any such slice may become `succeeded`.

Provider-returned records are accepted only if outbound and return both fall inside the same task window. A record outside that window never reaches exact revalidation. Multiple supplied windows are planned deterministically and merged only after each candidate has retained its single-window provenance; no trip can be assembled by taking an outbound from one window and a return from another.

## Bounded planning

The machine SSOT in `flight-radar.yaml` defines hard maxima for window count, destination-free discovery calls, and exact revalidations. A request may use only limits at or below those maxima. Discovery ordering is deterministic and round-robins normalized windows at each date-pair depth before later date pairs; truncation takes a stable prefix.

Bounded truncation is execution policy, not coverage permission. If that stable prefix leaves any supplied availability window completely unattempted, the missing window is recorded as `not_attempted` with `reason=budget_unattempted`; another window's success cannot hide it and no consumable scoped manifest is written. If an explicit duration leaves a supplied window with zero queryable date pairs, the window is `not_attempted` with `reason=no_queryable_date_pair`, the provider is not called for that window, and the scoped run likewise fails closed before manifest publication.

## CFR semantics

Every known-route exact completion is authorized through the existing `source_router` `round_trip_benchmark` path and executed through the existing adapter `exact()` surface.

Formal Deal truth is evaluated with the same CFR anomaly authority and exact-complete-airfare logic used by `ProductionRadar`. A Deal remains `classification=Deal, state=deal` and is never copied into the non-Deal pool.

Current exact/revalidated non-Deals enter `RadarRunResult.exact_non_deal_candidates`; only the RP-02 `apply_absolute_low_selection()` path may produce `ftr_absolute_low_non_deal`. Generic weak Signals, failed exact searches, incomplete evidence, and non-revalidated exact evidence are never promoted.

RP-03 does not add destination-side open-jaw or new Taiwan-return-gateway acquisition. Existing normalized route/gateway identity is preserved by the shared FTR handoff serializer when such records already exist in an eligible CFR result.

## Coverage truth

The scoped run retains the RP-01 provider, surface, origin, and market dimensions and adds availability-window coverage as scoped terminal truth. Each supplied window persists deterministic counters for queryable date pairs, planned tasks, attempts, provider calls, non-empty successes, complete-empty results, failures, suppressions, unsupported routing, and records, plus one of `succeeded`, `failed`, or `not_attempted`.

A window is `succeeded` only when it has at least one real provider call and every call has a complete outcome. A complete-empty response is successful acquisition coverage and remains distinct from zero candidates. A provider failure is `failed`. A window with zero calls is never `succeeded`: budget truncation and zero-queryable duration constraints are both explicit `not_attempted` states with different reasons.

The same window truth is persisted in both `snapshot.coverage.windows` and `snapshot.scoped_search.execution.window_execution`; scoped validation requires them to match exactly and reconstruct against the deterministic plan. Any supplied window that is not `succeeded` makes the scoped snapshot non-consumable and prevents the scoped manifest from being written. This is stricter than treating the counters as informational metadata and prevents an overall green workflow from fabricating scoped coverage.

Because current RP-01 handoff treats both Flight Deals and Explore as required discovery surfaces for complete canonical coverage, a healthy RP-03 snapshot can legitimately be `coverage_state=degraded` while remaining a valid scoped snapshot: Flight Deals is real scoped coverage and Explore is truthfully `not_attempted` rather than fabricated.

## Durable handoff and isolation

A completed consumable run uses the existing RP-01 handoff primitives:

1. build a schema-compatible `mode=scoped_search` snapshot from real CFR execution evidence;
2. attach scoped request/fingerprint/plan/window-execution metadata and normalized `coverage.windows`;
3. validate every supplied window as terminal `succeeded`, then validate every published variant against one supplied window, optional duration, and optional request budget;
4. write the immutable snapshot first;
5. write `data/ftr-feed/scoped/{run_id}.json` last with the snapshot checksum;
6. reload through the checksum-validating consumer primitive and validate the scoped metadata/window truth again.

Before execution, the runtime hashes the presence/content of `data/ftr-feed/latest.json` and `data/ftr-feed/current-status.json`. The same deterministic guard is asserted in a `finally` path after success or failure. Scoped execution never calls canonical claim, repair creation, repair clearing, or operator-reacquisition operations.

Therefore RP-03 cannot create/replace/advance canonical latest, clear `repair_required`, replace a canonical incident, or masquerade as `same_day_recovery`.

## Acceptance boundary

All RP-03 acceptance uses deterministic fixtures/fake adapters and isolated temporary filesystems. No test invokes a live airfare provider. Production activation, production proof, FTR consumer orchestration, RP-04 canonical activation, RP-05 recovery orchestration, and RP-06 eligibility/route expansion remain out of scope.
