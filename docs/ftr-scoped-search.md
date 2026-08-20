# FTR scoped-search acquisition (RP-03)

Status: implemented pre-activation. `ftr_handoff.canonical_activation.enabled` remains `false`.

## Purpose

`scoped_search` is the on-demand CFR acquisition mode used by Family Trip Radar Search Mode when the user supplies one or more `availability_windows`. It is not a second airfare product, not a canonical daily run, not operator reacquisition, and not same-day recovery.

The runtime is `cheap_flight_radar.scoped_search`. It has no scheduler and this package adds no GitHub cron or production launch path.

## Request and identity

A request has an explicit `request_id`, one or more availability windows, and an explicit bounded execution policy. Duration is optional. When duration is absent, the planner does not inject an FTR fixed trip duration; only existing CFR complete-trip / minimum-away semantics remain. `max_budget_twd`, when supplied, is a request-local hard filter only.

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

Without a user duration constraint, date-pair planning considers multiple durations where the budget permits. The existing CFR strict `>24h` complete-trip rule is a Deal/eligible-airfare invariant, not an FTR fixed-duration preference.

## CFR semantics

Every known-route exact completion is authorized through the existing `source_router` `round_trip_benchmark` path and executed through the existing adapter `exact()` surface.

Formal Deal truth is evaluated with the same CFR anomaly authority and exact-complete-airfare logic used by `ProductionRadar`. A Deal remains `classification=Deal, state=deal` and is never copied into the non-Deal pool.

Current exact/revalidated non-Deals enter `RadarRunResult.exact_non_deal_candidates`; only the RP-02 `apply_absolute_low_selection()` path may produce `ftr_absolute_low_non_deal`. Generic weak Signals, failed exact searches, incomplete evidence, and non-revalidated exact evidence are never promoted.

RP-03 does not add destination-side open-jaw or new Taiwan-return-gateway acquisition. Existing normalized route/gateway identity is preserved by the shared FTR handoff serializer when such records already exist in an eligible CFR result.

## Coverage truth

The scoped run emits the RP-01 dimensions: provider, surface, origin, and market, each with `succeeded`, `failed`, or `not_attempted` semantics. It also records per-window execution counts in scoped snapshot metadata.

Zero candidates is not a provider failure. A successful/empty provider request is still attempted coverage. Conversely, an unqueried or unsupported surface is never marked succeeded merely because the overall Python process exits successfully.

Because current RP-01 handoff treats both Flight Deals and Explore as required discovery surfaces for complete canonical coverage, a healthy RP-03 snapshot can legitimately be `coverage_state=degraded` while remaining a valid scoped snapshot: Flight Deals is real scoped coverage and Explore is truthfully `not_attempted` rather than fabricated.

## Durable handoff and isolation

A completed run uses the existing RP-01 handoff primitives:

1. build and validate a schema-compatible snapshot with `mode=scoped_search`;
2. attach scoped request/fingerprint/plan/window-execution metadata;
3. validate every published variant against the supplied windows, optional duration, and optional request budget;
4. write the immutable snapshot first;
5. write `data/ftr-feed/scoped/{run_id}.json` last with the snapshot checksum;
6. reload through the checksum-validating consumer primitive and validate the scoped metadata again.

Before execution, the runtime hashes the presence/content of `data/ftr-feed/latest.json` and `data/ftr-feed/current-status.json`. The same deterministic guard is asserted in a `finally` path after success or failure. Scoped execution never calls canonical claim, repair creation, repair clearing, or operator-reacquisition operations.

Therefore RP-03 cannot create/replace/advance canonical latest, clear `repair_required`, replace a canonical incident, or masquerade as `same_day_recovery`.

## Acceptance boundary

All RP-03 acceptance uses deterministic fixtures/fake adapters and isolated temporary filesystems. No test invokes a live airfare provider. Production activation, production proof, FTR consumer orchestration, RP-04 canonical activation, RP-05 recovery orchestration, and RP-06 eligibility/route expansion remain out of scope.
