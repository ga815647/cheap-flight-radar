# Current search policy — 2026-08-13 substrate convergence


## Current executable provider contract (SR-D, 2026-08-21)

`RoutePlan.entries` is an execution contract: every listed provider must be invokable by the canonical backend for the represented request shape.

- Destination-free canonical discovery/anomaly acquisition: qualified `gflights==0.3.1` / `gflights_google_flight_deals` remains the executable primary and automatic executable fallback is **none**. A primary failure fails closed and remains provider/coverage failure evidence.
- Known-route exact/flexible completion: `gflights_google_exact` is primary; the qualified official Kiwi.com remote MCP (`kiwi_mcp_exact`) is a one-attempt automatic fallback after primary technical failure. Primary degradation remains visible even when fallback succeeds.
- Open-jaw/multi-city remains `gflights_google_exact` only; Kiwi MCP is not claimed as open-jaw or anomaly coverage.
- Expedia airport-origin public Web remains external ChatGPT-Web/direct recall only and cannot silently repair canonical coverage.
- `fli` / `flights==0.9.0` safe-transport protocol/parser proof succeeded in SR-D, but it is not selected because stock transport uses browser impersonation/retries and it shares the Google upstream with gflights.
- FlyAI remains a different legacy adapter/provider contract and is not part of SR-D redundancy.

The historical routing and bake-off material below is retained as research history. Older uses of “fallback” describe candidate/external surfaces unless a section explicitly states current canonical-backend integration; they do not override this current execution contract.

This section supersedes any older mandatory outbound-one-way-first, global-scope, market-specific deep-pipeline, ferry-gateway, or fixed 120-day product semantics below. The older material remains in this file as design history. `PRODUCT_INTENT.md` and `flight-radar.yaml` are authoritative; see `docs/substrate-bakeoff-2026-08-13.md` for live evidence.

Current search architecture:

- production scope is Asia/Oceania; Japan, Korea and China are priority coverage slices, not separate mandatory algorithms;
- attempt destination-free discovery independently from TPE/TSA/RMQ/KHH;
- primary surface is qualified Google Flight Deals, with Google Explore and public Expedia/Kiwi/Skyscanner surfaces as recall/fallback seeds;
- direct complete round-trip Deal discovery is first-class and does not require reconstruction from a one-way fare;
- cheap one-way/Explore/Signal observations may seed investigation, but only competitive endpoints receive flexible return/open-jaw expansion;
- exact/flexible/multi-city Google Flights is the normal completion substrate; `fli` is a comparator/fallback;
- do not brute-force every city × date × city combination; add specialist pipelines only after measured recall evidence justifies them;
- 120 days is the normal compute budget, not a durable product boundary;
- ferry gateways are outside the airfare-Deal product.

---

# Search Strategy

## Goal

Cheap Flight Radar is a **deal discovery system**, not a fixed-destination booking form.

The central search pattern is:

1. discover unusually cheap outbound one-way fares from Taiwan;
2. expand only promising outbound candidates into complete trips;
3. search multiple return dates appropriate to route length;
4. consider same-city return, open-jaw return, different Taiwan return airports, and practical positioning segments;
5. treat verified usable stopovers as travel time rather than automatically treating every long connection as wasted time;
6. benchmark the constructed itinerary against a conventional round trip;
7. retain only complete itineraries whose important components can be verified for user-facing deal views;
8. persist the completed run before deriving historical publication metrics.

Price discovery answers two timing questions in parallel:

- **near-term floor** — what is cheap among usable trips departing within the next 30 days?
- **horizon absolute floor** — how low can a usable trip go anywhere in the full rolling 120-day horizon?

A good near-term fare is not automatically the horizon floor, and a far-future absolute low is not automatically useful to someone who wants to leave soon.

## Why outbound-first

Searching every origin × destination × departure date × return date × trip length × open-jaw pair is too expensive and noisy for a daily radar.

A cheap outbound fare is an efficient discovery signal. Most destinations do not need expensive deep search on every run.

Outbound-first does **not** mean two one-way tickets are assumed cheaper. The round-trip benchmark remains mandatory where available.

The term also has a strict executable meaning: the caller must not choose the destination before Stage A. A run that starts with `TPE -> PUS`, `KHH -> PVG`, or any other caller-preselected destination is a known-route probe, not outbound-first coverage, even if it searches the outbound leg before the return.

## Daily radar profiles

The default daily run uses one shared discovery engine with four specialist views rather than four unrelated full searches:

1. **World** — broad global discovery. Japan, Korea, and China remain eligible discovery destinations, but World does not spend specialist deep-expansion budget on them.
2. **Japan** — specialist deep search including alternate airports, open-jaw itineraries, and practical domestic flight/rail/bus positioning.
3. **Korea** — specialist deep search including alternate airports, open-jaw itineraries, and practical domestic flight/rail/bus positioning.
4. **China** — specialist deep search. This is the default profile that activates Kinmen/Matsu ferry gateway expansion and the China multimodal coverage gate.

The profiles share Taiwan-origin coverage and normalized candidate records. They should not repeat the same broad discovery four independent times when a shared result can be reused.

The final public report preserves dedicated Japan, Korea, China, and World sections. It does not publish a composite `Best Value` winner. Composite scoring may remain an internal ordering heuristic for allocating deep-search effort.

## Stage A — broad discovery

Search the rolling horizon for low one-way opportunities from the configured Taiwan origins **without a caller-supplied destination**.

### Executable coverage boundary

`OriginSweepRequest` is the only request shape that can establish outbound-first Stage-A coverage. It contains the exact Taiwan origin, rolling horizon and profile scope, but deliberately contains no destination or outbound date. A destination first appears in an `OutboundSeed` emitted by the sweep.

A legacy/known-route `SearchRequest(search_stage="broad_discovery", destination=...)` is rejected as `invalid_contract` by the source router and is ignored by the outbound-first coverage gate. This is the regression boundary that prevents a guessed PUS/OKA/PVG list from being relabeled as outbound-first.

The daily run performs one shared destination-free sweep for each configured origin:

- TPE;
- TSA;
- RMQ;
- KHH.

Only after a sweep produces a destination may the radar issue an exact known-route outbound probe.

### Broad-discovery routing

The primary Stage-A public surface is Expedia Taiwan's airport-origin `flights-from` page for the exact origin airport. These pages are useful because the request itself names an origin but does not require a destination. They are executed through ChatGPT Web, not through a new crawler or GitHub schedule.

Expedia is a **primary destination-seed surface, not a sole fare authority**. Its origin page can expose three distinct evidence classes:

1. `one_way_fare` — only when the page explicitly labels the amount as one-way;
2. `round_trip_deal` — a card explicitly labeled round trip;
3. `destination_only` — a destination/route signal without a usable fare.

A round-trip card is never divided by two or otherwise converted into an invented outbound fare. A headline one-way low without an exact departure date can seed a destination, but it cannot establish either the 0–30 or 0–120 outbound floor until an exact route/date one-way probe converges.

If the Expedia airport-origin surface is unavailable or insufficient, the existing `chatgpt_web_public_fare_index` route remains a best-effort destination-free fallback. This fallback does not convert known-route probes into Stage-A coverage and does not claim exhaustive market recall.

After a destination exists, the shared known-route Web layer uses:

- **exact route probe** — exact origin IATA + sweep-produced destination IATA + month/date window + explicit one-way intent;
- **return expansion probe** — sweep-produced destination + one of the generated return dates + Taiwan return airport;
- **round-trip benchmark probe** — exact conventional origin/destination/date pair;
- **LCC carrier probe** — exact route/date context plus a relevant low-cost carrier when generic fare indexes under-surface it.

Public fare-index observations remain **discovery evidence**. Indexed prices can be stale, prices can change, and metro-area pages can silently substitute airports. Exact airport/date/price therefore must be revalidated before a candidate is described as verified.

This best-effort Web route does not claim an exhaustive fare matrix. Fixed watches remain separate coverage/provenance signals and are not expanded merely to imitate a fare matrix. PTT is not a dependency of the outbound-first execution trunk. GitHub Actions is not part of this normal direct-Web stage unless ChatGPT delegates a deterministic execution surface.

### Two live fare floors, not one coarse target band

Only exact one-way probes can enter outbound floors. Broad discovery must retain both:

1. the cheapest serious **near-term** candidate departing within 30 days; and
2. the cheapest serious candidate in the complete **rolling 120-day horizon**.

A coarse heuristic such as "Korea around TWD 5k is cheap" is only an early candidate trigger. It is not a stopping condition. The floor scan continues because a TWD 5k near-term fare can coexist with a TWD 3–4k fare later in the horizon.

The same distinction matters for history: observations should be compared within departure lead-time buckets where possible so a fare seen a week before departure is not treated as equivalent to a 90-day-ahead observation.

Stage-A serious-candidate selection also reserves breadth across Japan, Korea, China and World before filling the remaining candidate budget globally. One market with many cheap observations must not consume the entire deep-search budget while other markets have eligible evidence.

### Korea specialist breadth

The Korea specialist must not equate "Korea" with only Seoul and Busan.

Initial non-exhaustive floor-scan seeds include ICN, GMP, PUS, CJU, TAE, and CJJ. This is a specialist deep-search breadth list, not a substitute for the destination-free Stage-A origin sweep and not a permanent route whitelist. Any other relevant Korean airport remains eligible when current route/fare evidence exists.

### Origin coverage gate

Every configured airport in `search.origin_airports` must receive a destination-free `OriginSweepRequest` attempt before a run may be described as **outbound-first full global radar**:

- TPE;
- TSA;
- RMQ;
- KHH.

A known-destination attempt for an origin does not satisfy this gate. A source that only exposes a metro-level "Taipei" result also does not count as Taiwan-wide airport coverage. Failed/missing origins remain visible as missing/unavailable rather than being silently replaced.

### Taiwan return closure is broader than outbound discovery

Configured outbound-discovery origins are not a whitelist of acceptable return airports.

A complete itinerary may end at **any public passenger airport on Taiwan's main island** when live evidence shows the proposed return flight operates. TPE/TSA/RMQ/KHH remain primary return-search airports, but a serious candidate can opportunistically return through another main-island airport.

Different Taiwan airports on outbound and return are first-class candidates. Once the itinerary reaches an eligible Taiwan main-island airport, the trip is considered returned to Taiwan. Do not add a mandatory domestic positioning segment merely to get back to the original outbound airport or a presumed home city.

This broader return closure does not expand the global origin-coverage gate: full-radar coverage still concerns the configured outbound origins.

### Taiwan airport display labels

User-visible Taiwan airport labels must remain airport-specific. Do not collapse TPE and TSA into `Taipei` / `台北`.

Default labels are:

- `TPE` → `桃園（TPE）`;
- `TSA` → `松山（TSA）`;
- `RMQ` → `台中（RMQ）`;
- `KHH` → `高雄（KHH）`.

If a source exposes only a metro label and the actual airport cannot be resolved, mark the airport unknown rather than publishing a candidate as though TPE or TSA had been identified.

Capture at minimum origin/destination, departure timestamp or date, displayed price/currency, carrier when available, stop count, source, observation time, and evidence/verification state.

## Stage B — candidate expansion

Only `SeriousOutbound` records selected from exact one-way Stage-A probes may enter return expansion. A raw seed or a caller-preselected route cannot bypass this gate.

For each serious outbound, search **multiple** return dates over route-time-dependent windows. Candidate return forms include:

1. same destination → Taiwan;
2. nearby/practical alternate city → Taiwan;
3. a different primary Taiwan return airport;
4. an opportunistic return to another live-served Taiwan main-island passenger airport;
5. one positioning segment by domestic flight, rail, bus, or ferry where allowed.

Do not force a return to the outbound Taiwan airport. Non-primary Taiwan return airports require current live route evidence before they are added to the expansion set.

### Return-window semantics

`return_windows` are search and scoring guidance, **not hard maximum-trip-length rejection rules**.

Trips below a minimum useful stay can be heavily penalized. Trips in the ideal range can receive full fit. Longer trips do not receive endless extra reward, but they remain eligible when otherwise usable. Duration alone must not reproduce the previously corrected hard-`max_nights` bug.

### Long connections and usable stopovers

Do not reject or heavily penalize a connection merely because its scheduled duration is long.

When a connection is long enough to permit a real excursion, determine how much is **verified usable stopover time** after preserving:

- entry/document feasibility;
- safe connection/recheck buffers;
- practical airport/station access;
- baggage/recheck constraints.

Only the verified excursion portion becomes `usable_stopover_hours`. The remainder remains ordinary connection/waiting time. If usable time cannot be verified, fail conservatively and treat it as waiting rather than assuming sightseeing.

Usable stopover hours can reduce connection-time penalty and count as usable trip time, but cannot make an intentionally inefficient routing outperform the practical efficient-travel baseline. Self-transfer, re-entry, baggage, and missed-connection risks remain separate.

Overnight lodging cost remains outside effective transport price. The itinerary consequence is represented by trip length and usable/unusable time instead of an invented required hotel price.

## Stage C — complete-trip normalization

Normalize each serious candidate into a comparable itinerary record including:

- all required transport segments;
- total required transport cost, excluding lodging and ordinary short local access under the SSOT;
- first departure from Taiwan;
- arrival at first real destination;
- departure from final real destination;
- final return to an eligible Taiwan main-island airport;
- total transit/connection time when available;
- verified usable stopover hours;
- remaining unusable waiting time;
- usable destination hours when available;
- baggage assumptions;
- transfer risks;
- verification state.

Unknown essential components remain unknown; do not fill plausible values.

A separate return one-way is not mandatory when the same return-expansion date has a usable conventional round-trip fare. In that case the RT benchmark itself is a complete itinerary and may close the candidate directly; the system must not require two one-way fares merely because discovery began with a one-way outbound.

## Stage D — round-trip benchmark

For each serious candidate, compare against a conventional round trip on the relevant route/dates when a comparable fare can be obtained.

If a normal round trip is cheaper and comparably usable, it should win even when discovery began with a one-way fare. If the separate return one-way fails to converge but the conventional RT is exact-date, usable and current enough for the candidate's evidence state, the RT may itself complete the candidate. The benchmark does not invalidate a mixed-Taiwan-airport itinerary merely because its endpoint differs; compare the simplest practical complete alternatives available for the same travel intent.

Only after a complete baseline candidate exists should the radar spend extra effort on open-jaw and mixed-Taiwan-return alternatives. Mainland HSR/domestic-air/Kinmen/Matsu expansion remains China-specialist-only.

## Stage E — explicit views and market sections

Do not collapse user value into one opaque rank.

The required user-facing live views are:

- **Near-Term Cheapest** — minimum effective total transport cost for usable trips departing within 30 days;
- **Absolute Cheapest** — minimum effective total transport cost anywhere in the rolling 120-day horizon;
- **Best Short Break** — strong cheap trip that becomes worthwhile with relatively few usable days;
- **Unusual Long-Haul Deal** — unusually cheap long route with adequate trip length.

There is deliberately **no user-facing Best Value view**. The provisional composite may still help internally order candidates before/deep-search work, but publication does not name its winner.

Japan/Korea/China/World notable candidates are published in dedicated sections. A section may explicitly contain no winner when nothing converged.

Historical anomaly evidence is reported alongside live-price views rather than replacing them. A current horizon floor can be historically ordinary, while a higher-priced route can still be a stronger historical anomaly.

## Stage F — persist before publication

After a Radar run has finished current discovery/deep-search/revalidation work:

1. persist one immutable validated run snapshot on `history/price-observations`;
2. derive current floors and historical metrics from persisted history;
3. append one presentation manifest on `publication/radar-reports`;
4. let the manifest push trigger the disposable static build/deploy backend.

The publication manifest never becomes fare history. Failed/non-converged cheap seeds, view selections, and coverage/freshness are presentation/provenance state; fare prices and historical calculations come from evidence snapshots.

See `docs/publication.md` for the complete Pages contract.

## Search horizon

Default: rolling 120 days. The horizon moves forward each run. Historical observations are retained separately and do not extend current live search state.

The near-term price view is the first 30 days of the same horizon, not a second scheduler or scan. Historical comparisons use configured departure lead-time buckets (`0–14`, `15–30`, `31–60`, `61–120`) when evidence exists.

## Weekdays

v0.1 has no weekday hard gate. Weekday/weekend/leave-day information may be displayed, but should not suppress an otherwise exceptional fare unless policy explicitly changes.

## Price verification

Search-result/metasearch prices are discovery signals, not promises.

Before calling a result a verified deal, re-check through a source capable of showing the actual itinerary and current price. When checkout cannot be verified, label confidence/state accurately.

Public/indexed Facebook or airfare-editor posts are `opportunistic` seed evidence only. They may provide route/date/promotion/price text when accessible without login bypass, but they never establish a verified fare and do not repair fixed-watch coverage.

## Current source-router slice

Production source routing remains intentionally **partial**:

1. **shared destination-free Stage A** across World/Japan/Korea/China — `expedia_tw_airport_origin_surface` is the primary origin-wide seed surface for TPE/TSA/RMQ/KHH; `chatgpt_web_public_fare_index` is the best-effort fallback. Both execute directly through ChatGPT Web and neither claims an exhaustive fare matrix;
2. **post-seed known-route Web probes** — `chatgpt_web_public_fare_index` handles exact outbound one-way, return expansion and conventional RT benchmark queries only after a sweep-produced destination exists;
3. **China deep search** — exact round trip through FlyAI with formal `FLYAI_API_KEY` when that route is used.

The router reads these selections from `flight-radar.yaml`; provider choice must not be duplicated as hidden code policy. A missing credential, unhealthy provider, unsupported open-jaw request, or unconfigured market/stage yields explicit unavailable/unsupported coverage and must not silently degrade while claiming provider coverage.

The shared Web route is best-effort discovery, not a deterministic full-market matrix and not checkout verification. Serious candidates require separate revalidation.

FlyAI results pass a strict returned-segment airport/date gate before normalization. Observed FlyAI `ticketPrice` remains a raw provider value where currency/tax/baggage/fare-family semantics are unknown. FlyAI is not selected for broad discovery, true revalidation, final cross-check, or combined open-jaw fare, and a FlyAI-only run must never claim complete China airfare coverage.

See `docs/outbound-first-contract-2026-08-12.md` for the implementation audit, deterministic Gate and live Expedia smoke evidence for this contract.
