# Outbound-one-way-first executable contract — 2026-08-12

Status: implementation checkpoint on top of clean `main`.

This package does not change the product policy in `flight-radar.yaml`. It makes the already-declared `search.discovery_strategy: outbound_one_way_first` and shared Web broad-discovery route executable and testable.

## Audit result

Before this package:

- `SearchRequest` required `destination` and `outbound_date`;
- `source_router.build_source_plan()` accepted that known-destination request for `broad_discovery`;
- the broad-discovery test itself preselected `PUS`;
- the controlled direct-Web benchmark used market/destination permutations and exact-route probes;
- therefore a run could say broad/outbound-first discovery happened without proving that any destination came from a destination-free origin sweep.

That is the contract gap closed here.

## Executable stages

### Stage A0 — destination-free origin sweep

`OriginSweepRequest` contains the exact Taiwan origin, horizon start/120-day horizon, 30-day near-term window, shared World/Japan/Korea/China profile set, currency and global destination scope. It deliberately has **no `destination` or `outbound_date` field**.

Only this request type can plan the shared broad-discovery route. A legacy `SearchRequest(search_stage="broad_discovery", destination=...)` returns `coverage_state=invalid_contract` and cannot establish outbound-first coverage.

A daily run issues one shared sweep for each configured origin (TPE/TSA/RMQ/KHH); it does not repeat the same broad sweep once per market profile.

### Stage A1 — normalized outbound seed

The sweep emits `OutboundSeed` with one of three evidence scopes:

1. `one_way_fare` — source explicitly labels the displayed amount one-way;
2. `round_trip_deal` — source explicitly labels the displayed amount round trip;
3. `destination_only` — route/destination signal without a usable fare.

The contract never converts `round_trip_deal` to a one-way fare and never divides a round-trip amount by two. A seed is the first point at which a destination may appear.

### Stage A2 — exact outbound one-way probe

`outbound_probe_request()` converts a sweep-produced seed into the first known-destination `SearchRequest`. Its `OutboundProbe` must resolve exact origin/destination airports, exact outbound date, explicit one-way fare scope, and a positive current displayed price. Only such probes are eligible for floors.

### Stage A3 — floors + serious-candidate gate

`select_stage_a_candidates()` preserves separate 0–30 day and 0–120 day floors by origin × market. Before filling the remaining budget globally, it reserves eligible evidence for Japan, Korea, China and World, so one market cannot consume every serious slot merely by producing many low observations.

Selected probes are wrapped as `SeriousOutbound`. Return expansion accepts that type rather than a raw probe, so unselected probes cannot bypass the Stage-A selection gate.

### Stage B — return expansion

`build_return_expansion_requests()` uses the SSOT travel-time return-window guidance, emits multiple reasonable return dates, searches TPE/TSA/RMQ/KHH, and admits another Taiwan main-island airport only with supplied live-route evidence. Return windows remain search guidance, not hard duration rejection.

### Stage C/D — completion + mandatory RT benchmark

`complete_candidate()` requires both a usable exact return fare and a conventional round-trip benchmark on the same dates. A usable conventional round trip wins when it is cheaper/equal with at least comparable practicality, or when current evidence marks it as more practical.

Only after this baseline candidate exists does `downstream_expansion_modes()` expose open-jaw / mixed-Taiwan-return expansion. Mainland HSR/domestic air/Kinmen/Matsu modes are China-profile-only.

## Expedia Taiwan origin-wide smoke research

Live public-Web research on 2026-08-12 found Expedia Taiwan airport-origin pages for TPE, TSA, RMQ and KHH under the `/lp/airports/<IATA>/flights-from-...` surface.

The TPE page is genuinely destination-free at entry: it is a flights-**from-TPE** page rather than a TPE→preselected-destination page. In the observed surface:

- the page separately stated one-way and round-trip starting prices;
- its FAQ identified the cheapest observed one-way destination as ICN;
- deal cards independently surfaced destinations including ICN, KIX, DMK, HKG, NRT and PVG;
- visible deal cards were predominantly explicitly labeled **round trip**, even though a one-way filter exists.

Operational decision: Expedia Taiwan is strong enough to be the **first origin-wide seed surface** attempted inside the existing `chatgpt_web_public_fare_index` Stage-A execution, but it is **not sufficient as the sole Stage-A fare authority**. The airport page may give a one-way low without the exact outbound date needed for a 0–30/0–120 floor, while many useful destination cards are round-trip evidence. Every serious destination therefore still requires an exact one-way route/date probe.

`tests/fixtures/outbound_first/expedia_tpe_origin_surface.json` preserves one-way, round-trip-card and destination-only evidence classes without claiming the fixture price remains current.

## Live end-to-end smoke — destination produced by the sweep

A small public-Web smoke on 2026-08-12 closed the full contract without preselecting the destination:

1. **Origin sweep:** Expedia Taiwan's TPE airport-origin surface independently emitted **ICN** among its deal destinations. The caller supplied TPE, not ICN.
2. **Exact outbound probe:** only after that seed existed, the TPE→ICN route surface exposed an explicit one-way fare of **NT$2,442 for 2026-09-14**.
3. **Return expansion:** the observed direct flight time was about 2h35, so the SSOT's up-to-4-hour bracket expands the outbound into multiple reasonable return dates, including 3/5/8 nights: **2026-09-17, 2026-09-19, 2026-09-22**. The 5-night ICN→TPE probe converged to an explicit one-way **NT$2,575 on 2026-09-19**.
4. **Conventional RT benchmark:** Trip.com's public Taiwan route surface independently exposed the exact same TPE→ICN **2026-09-14 → 2026-09-19** nonstop round trip at **TWD 5,057**.
5. **Complete candidate:** the constructed pair is **TWD 5,017 = 2,442 + 2,575**, so for this smoke the one-way pair beats the conventional round trip by **TWD 40**. The benchmark is still retained; had the RT been cheaper or materially more practical, the executable completion rule would select it instead.

Evidence URLs used by the smoke:

- Expedia TPE origin surface: `https://www.expedia.com.tw/en/lp/airports/tpe/flights-from-taoyuan-intl-airport`
- Expedia TPE→ICN: `https://www.expedia.com.tw/lp/flights/tpe/icn/taipei-to-seoul?flightType=oneway`
- Expedia ICN→TPE: `https://www.expedia.com.tw/en/lp/flights/icn/tpe/seoul-to-taipei?siteid=62`
- Trip.com Taiwan TPE→ICN benchmark surface: `https://tw.trip.com/flights/airport-tpe-icn/`

These are public fare-index observations, not checkout verification. They prove the Stage-A discovery provenance and end-to-end contract shape; any user-facing fare promotion still requires the normal final revalidation policy.

## Public Facebook/editor contract

Search-indexed public Facebook/editor material may create `OpportunisticSeedSignal` carrying route/date/promo/price text. It is permanently `role=opportunistic`, `verification_state=seed_only`, and `can_establish_verified_fare=false`. Login-gated/non-public social content is rejected.

This is independent of fixed-watch coverage. PTT is not required anywhere in the outbound-first execution path.

## Coverage-claim Gate

The regression Gate is explicit:

> A caller-preselected destination passed through `SearchRequest(search_stage="broad_discovery", ...)` must receive `invalid_contract`; only destination-free `OriginSweepRequest` can establish outbound-first coverage.

This prevents the previous pattern — guess PUS/OKA/PVG, then probe it — from being relabeled as outbound-first discovery.
