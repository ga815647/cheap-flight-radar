# Production Radar runtime — 2026-08-13

## Status

This checkpoint connects the selected Google airfare substrate to an executable anomaly-first Radar path. It does not re-open the substrate bake-off.

The canonical one-shot production command is `python -m cheap_flight_radar.production_runtime`. ChatGPT remains the scheduler/orchestrator. The runtime is short-lived acquisition / normalization / decision / artifact generation only; it owns no schedule, queue, daemon, or durable state service.

The production path is:

1. ChatGPT orchestrates one Radar run.
2. The short-lived runtime creates an `OriginSweepRequest` for each configured origin: TPE, TSA, RMQ, KHH.
3. `source_router` must select `gflights_google_flight_deals` as the destination-free primary.
4. The adapter performs sparse Flight Deals trip-length anchors with the fixed CheapFlightRadar User-Agent, direct connection (`proxy=None`), TWD, and Taiwan locale.
5. Results are normalized into provider-independent `AirfareRecord` values. Raw `gflights` objects never cross the adapter boundary.
6. Global provider results are filtered to international Asia/Oceania and classified into Japan, Korea, China, and other Asia/Oceania priority slices.
7. Qualified Flight Deals and competitive weak seeds are first normalized by exact destination airport across TPE/TSA/RMQ/KHH. For each destination airport, the lowest current complete airfare is the preferred concrete candidate for bounded exact completion. There is no city × date × city brute-force matrix.
8. Every qualified Flight Deals row is retained as run evidence. A qualified row not selected for exact completion under the current compute budget is a `qualified_anomaly_candidate_pending_exact` Signal, never silently discarded and never promoted to a Deal.
9. `source_router` must select `gflights_google_exact` before the adapter can revalidate a candidate. Exact search preserves provider leg identity and booking-token/search provenance; booking offers are resolved when available.
10. Formal anomaly truth is selected by SSOT priority and never averaged: `google_flight_deals` → `google_flights_exact_price_insight` → `own_price_history`.
11. For Flight Deals, Radar uses the **lowest qualified typical price observed for the same destination airport across the configured Taiwan origins** as the external baseline, then compares that baseline with the newly revalidated exact current complete airfare. An expensive origin-specific typical cannot override a lower same-destination baseline.
12. Formal Deals are sorted only by relative anomaly strength descending, then current complete airfare ascending. Trip length, stops, brand, red-eye, self-transfer, lodging, and ground-transport friction do not alter formal Deal order.
13. Weak seeds, pending qualified anomalies, exact candidates without qualified anomaly truth, stale anomalies, and provider failures remain Signals/evidence rather than being promoted.
14. Every exact current complete airfare can become an immutable `FareObservation`. The run writes the existing history snapshot schema plus a schema-v2 publication manifest.
15. Schema-v2 publication renders Deals and Signals as the primary views. Existing schema-v1 run pages remain supported; legacy Absolute Cheapest / Near-Term and related views are transition/diagnostic only for new runs.

## Acquisition boundary

Production pins `gflights==0.3.0`. The adapter constructs the client with an explicit `CheapFlightRadar/...` User-Agent and `proxy=None`; it does not use browser-UA rotation, CAPTCHA bypass, stealth/fingerprint spoofing, residential proxying, or session bypass.

The adapter supports destination-free Flight Deals, Explore seeds, exact one-way/round-trip, cheapest-date expansion, multi-city/open-jaw exact search, and booking-offer resolution.

For a round-trip exact search, gflights 0.3.0 publicly exposes the chosen search-result segments but does not guarantee that the returned `FlightResult.legs` contains the return segments. `offer()` prices and locks the complete round-trip context. The domain therefore retains the requested exact return date as trip identity and separately exposes whether provider segments themselves cover the complete trip. It never invents an unreturned segment.

## Orchestration boundary

No scheduler is implemented in the repository. GitHub Actions remains disposable compute/Gate infrastructure only. The temporary one-shot live-validation workflow had no `schedule:` trigger and was removed from the feature branch after evidence capture.

Fixed-watch observations remain Signals and are not a Deal-coverage gate.

## Live production validation

The final live-validation execution ran on feature commit `b1c3dc95b79fe0f069cc4f61cc659e55e76d3082` in GitHub Actions run `31628823394` at `2026-08-13T02:40:56.098367+08:00`.

The complete unittest Gate passed before acquisition. The live acquisition, schema-v2 publication smoke build, and artifact upload all completed successfully. No provider failure was recorded.

### Origin coverage

| Origin | Flight Deals rows returned | Asia/Oceania discovery records | Qualified anomaly records | Explore seeds |
| --- | ---: | ---: | ---: | ---: |
| TPE | 90 | 23 | 23 | 0 |
| TSA | 90 | 8 | 3 | 0 |
| RMQ | 90 | 28 | 12 | 0 |
| KHH | 90 | 19 | 19 | 0 |

All four configured origins were attempted through the same shared pipeline. Explore was not needed in this run because every origin already produced at least one qualified Flight Deals candidate.

### Market-slice coverage

| Priority slice | Discovered | Qualified | Exact revalidated | Deals |
| --- | ---: | ---: | ---: | ---: |
| Japan | 24 | 18 | 5 | 5 |
| Korea | 8 | 7 | 1 | 1 |
| China | 13 | 5 | 1 | 1 |
| Other Asia/Oceania | 33 | 27 | 3 | 3 |

The runtime exact-completed 10 candidates under the bounded compute budget and emitted 10 Deals. It retained 68 Signals: 47 `qualified_anomaly_candidate_pending_exact` records plus 21 weak seeds. The 47 pending qualified anomalies keep their Flight Deals price / typical-price / discount evidence but are not Deals because current exact completion was not performed.

### Revalidated Deals

Formal order below is anomaly strength descending, then exact complete airfare ascending. The anomaly percentage is recalculated from the Flight Deals typical price and the newly revalidated current complete airfare.

| Rank | Route | Dates | Current complete airfare | Typical price | Relative anomaly |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | KHH → DRP (Daraga, Philippines) | 2026-08-30 → 2026-09-06 | TWD 7,912 | TWD 33,177 | 76.152% below typical |
| 2 | TSA → CJU (Jeju, South Korea) | 2026-08-31 → 2026-09-09 | TWD 17,639 | TWD 63,237 | 72.107% |
| 3 | TPE → FKS (Fukushima, Japan) | 2026-08-28 → 2026-09-04 | TWD 12,097 | TWD 39,759 | 69.574% |
| 4 | TPE → YGJ (Yonago, Japan) | 2026-08-31 → 2026-09-07 | TWD 8,697 | TWD 28,552 | 69.540% |
| 5 | TPE → ISG (Ishigaki, Japan) | 2026-12-04 → 2026-12-11 | TWD 5,897 | TWD 18,221 | 67.636% |
| 6 | KHH → ISG (Ishigaki, Japan) | 2026-09-06 → 2026-09-13 | TWD 7,297 | TWD 20,971 | 65.204% |
| 7 | TPE → HNA (Hanamaki, Japan) | 2026-09-05 → 2026-09-12 | TWD 7,897 | TWD 22,127 | 64.311% |
| 8 | TPE → BWN (Bandar Seri Begawan, Brunei) | 2026-09-06 → 2026-09-13 | TWD 6,004 | TWD 16,197 | 62.931% |
| 9 | RMQ → BOM (Mumbai, India) | 2026-09-06 → 2026-09-15 | TWD 10,173 | TWD 22,518 | 54.823% |
| 10 | RMQ → KMG (Kunming, China) | 2026-08-20 → 2026-08-26 | TWD 13,382 | TWD 26,748 | 49.970% |

Booking/evidence URLs were returned for eight of the ten exact candidates. KHH→DRP and RMQ→KMG retained exact search/booking-token provenance without an exposed booking URL; the runtime did not invent one.

The round-trip history identities were verified after the live normalization fix. For example, KHH→DRP is persisted as `2026-08-30 → 2026-09-06`, and RMQ→KMG as `2026-08-20 → 2026-08-26`; outbound connection dates are not mistaken for return dates.

### Durable history and publication ordering

The 10 exact fare observations from this run were appended to `history/price-observations` in commit `71cf006b23b1e639c85a059782e5a5358fbf8a54` at:

`data/price-history/2026/08/13/production-radar-20260813T024056-0800.json`

The live artifact also contains a schema-v2 publication manifest with 10 Deals and 68 Signals. The new generator successfully rebuilt the static site from that manifest plus history evidence.

The schema-v2 manifest is intentionally not pushed to `publication/radar-reports` before this code PR merges: the Pages workflow reads its generator from `main`, and current `main` does not yet contain the schema-v2 generator. Publishing the manifest first would violate the established history → compatible generator → presentation ordering and deliberately cause an old-generator failure. After merge, a normal ChatGPT-orchestrated production run can persist history first, then append its v2 manifest and let the push-triggered Pages build deploy it.

Open-jaw exact completion was not needed by this live shortlist because the selected qualified candidates were already complete round trips. The production open-jaw path is covered by adapter/router integration tests and remains selective rather than mandatory.
