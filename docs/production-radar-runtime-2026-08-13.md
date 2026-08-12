# Production Radar runtime — 2026-08-13

## Status

This checkpoint connects the selected Google airfare substrate to an executable anomaly-first Radar path. It does not re-open the substrate bake-off.

The production path is:

1. ChatGPT orchestrates one Radar run.
2. The short-lived runtime creates an `OriginSweepRequest` for each configured origin: TPE, TSA, RMQ, KHH.
3. `source_router` must select `gflights_google_flight_deals` as the destination-free primary.
4. The adapter performs sparse Flight Deals trip-length anchors with the fixed CheapFlightRadar User-Agent, direct connection (`proxy=None`), TWD, and Taiwan locale.
5. Results are normalized into provider-independent `AirfareRecord` values. Raw `gflights` objects never cross the adapter boundary.
6. Global provider results are filtered to international Asia/Oceania and classified into Japan, Korea, China, and other Asia/Oceania priority slices.
7. Qualified Flight Deals and a small number of competitive weak seeds enter selective known-route completion. There is no city × date × city brute-force matrix.
8. `source_router` must select `gflights_google_exact` before the adapter can revalidate a candidate. Exact search preserves provider leg identity and booking-token/search provenance; booking offers are resolved when available.
9. Formal anomaly truth is selected by SSOT priority and never averaged: `google_flight_deals` → `google_flights_exact_price_insight` → `own_price_history`.
10. For Flight Deals, the authority's typical price is compared with the newly revalidated exact current complete airfare. This prevents stale discovery price from driving formal ranking.
11. Formal Deals are sorted only by relative anomaly strength descending, then current complete airfare ascending. Trip length, stops, brand, red-eye, self-transfer, lodging, and ground-transport friction do not alter formal Deal order.
12. Weak seeds, exact candidates without qualified anomaly truth, stale anomalies, and provider failures remain Signals/evidence rather than being promoted.
13. Every exact current complete airfare can become an immutable `FareObservation`. The run writes the existing history snapshot schema plus a schema-v2 publication manifest.
14. Schema-v2 publication renders Deals and Signals as the primary views. Existing schema-v1 run pages remain supported; legacy Absolute Cheapest / Near-Term and related views are transition/diagnostic only for new runs.

## Acquisition boundary

Production pins `gflights==0.3.0`. The adapter constructs the client with an explicit `CheapFlightRadar/...` User-Agent and `proxy=None`; it does not use browser-UA rotation, CAPTCHA bypass, stealth/fingerprint spoofing, residential proxying, or session bypass.

The adapter supports destination-free Flight Deals, Explore seeds, exact one-way/round-trip, cheapest-date expansion, multi-city/open-jaw exact search, and booking-offer resolution.

## Orchestration boundary

No scheduler is implemented in the repository. GitHub Actions remains disposable compute/Gate infrastructure only. The one-shot live-validation workflow used during this checkpoint has no `schedule:` trigger and is removed from the final branch after evidence is captured.

Fixed-watch observations remain Signals and are not a Deal-coverage gate.

## Live validation

To be filled from the one-shot exact-head runner before PR closeout. The durable evidence will record the exact commit/run, origin coverage, market-slice coverage, qualified Deals, exact revalidation outcomes, and any provider failures without inventing missing fares.
