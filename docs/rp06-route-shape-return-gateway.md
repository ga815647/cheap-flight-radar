# RP-06 — Route-shape eligibility and return-gateway semantics

Status: implemented capability; final FTR readiness remains false.

This package closes the route-variant admission/coverage gap identified by readiness audit Issue #37 without changing CFR Deal truth, Deal ranking, or provider-call shape.

## Canonical exact route-variant admission

The canonical runtime already spends bounded multi-city work on two route variants after baseline completion:

- mixed Taiwan return: `TW-origin -> A`, `A -> different-TW-return`;
- destination-side open jaw: `TW-origin -> A`, `B -> TW-return`.

RP-06 does **not** add another search. `ProductionExecutionAdapter` still owns the same fixed multi-city lane and `ProductionRadar` still makes at most one mixed-return logical attempt per selected expansion seed plus its existing bounded destination-side open-jaw attempt. `RecordingFlightDealsAdapter` now retains those already-acquired request/result pairs.

An already-acquired route variant may be copied into `RadarRunResult.exact_non_deal_candidates` only through that captured exact provider result. The generic Signal journal is not scanned and Signal naming/classification is not selector authority. Before pool admission, the runtime probes the existing RP-02 selector with the exact candidate so the same current/revalidated/reproducible/complete-fare/>24h/provenance/main-island/Deal-duplicate gates remain authoritative. The final RP-02 pass still owns bounded max-count and deterministic price-first ordering across the merged dedicated pool.

No anomaly baseline is synthesized for a route variant. A route variant that lacks formal CFR Deal truth remains a Signal/non-Deal candidate and can reach FTR only as `ftr_absolute_low_non_deal` after RP-02 selection.

## Route identity

Exact normalized itinerary legs are authoritative. FTR serialization already derives:

- mixed return `TW -> A ; A -> TW2` as destination route shape `(A, A)`, with actual Taiwan origin `TW` and actual Taiwan return `TW2`;
- destination open jaw `TW -> A ; B -> TW2` as destination route shape `(A, B)`.

Therefore `(A,A)` and `(A,B)` remain distinct FTR opportunities, while different Taiwan gateways remain variants under the same destination-side opportunity. City labels, discovery shortcuts, and metro guesses do not define this identity.

## Return-gateway coverage truth

`search.return_to_taiwan.completion_scope = any_public_passenger_airport_on_taiwan_main_island` defines which proven final arrivals can complete an itinerary. It does **not** claim every main-island airport was searched.

The canonical run result now carries optional `coverage.return_gateway_expansion` evidence with:

- configured primary return gateway pool;
- `search_exhaustive = false`;
- `primary_pool_semantics = bounded_search_pool_not_exhaustive_claim`;
- maximum one mixed-return provider attempt per expansion seed;
- one row per observed mixed-return request, including selected gateway, actually attempted gateway(s), configured primary gateways not attempted, `provider_request_sent`, result coverage state, and whether a revalidated complete exact record supplied live route evidence;
- explicit opportunistic non-primary semantics: allowed only when policy permits, live route evidence is required, no proactive exhaustive expansion is performed, and absence of live route evidence means not searched/not eligible as an opportunistic extra.

A circuit-suppressed request may still record which gateway was selected, but `provider_request_sent=false`, `attempted_mixed_return_gateways=[]`, and every configured primary gateway remains not attempted. An exact revalidated non-primary main-island return record is itself live route evidence; an offshore return cannot pass RP-02 main-island admission.

This optional gateway-expansion evidence does not redefine mandatory provider/surface/origin/market coverage and does not imply exhaustive gateway coverage.

## Scoped-search boundary

RP-06 is a canonical already-acquired route-variant convergence, not a new scoped open-jaw engine. Current scoped search continues to make zero mixed-Taiwan-return/open-jaw calls. Those surfaces remain `not_attempted` when no provider call occurred. Canonical route-variant capability does not imply scoped route-variant coverage.

The historical RP-03 `rp06_open_jaw_expansion` / `rp06_eligibility_expansion` labels are resolved as an intentional bounded scoped-search exclusion after RP-06, not as hidden unfinished work. Consumers must not infer coverage for a route-variant surface that scoped search did not acquire.

Scoped canonical isolation remains unchanged: scoped search cannot consume the canonical claim, advance canonical latest, mutate current-status, clear `repair_required`, or masquerade as same-day recovery.

## Readiness boundary

RP-05 same-day recovery capability remains implemented/active and its live proof remains pending. RP-06 adds zero provider calls beyond the existing canonical call shape and performs no live validation. Final FTR readiness therefore remains false after this package; RP-07 and RP-08 remain pending.
