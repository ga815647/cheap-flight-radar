# Search Strategy

## Goal

Cheap Flight Radar is a **deal discovery system**, not a fixed-destination booking form.

The central search pattern is:

1. Discover unusually cheap outbound one-way fares from Taiwan.
2. Expand only promising outbound candidates into complete trips.
3. Search multiple return dates appropriate to route length.
4. Consider same-city return, open-jaw return, and practical positioning segments.
5. Benchmark the constructed itinerary against a conventional round trip.
6. Rank only complete itineraries whose important components can be verified.

Price discovery must answer two different timing questions in parallel:

- **near-term floor** — what is cheap among usable trips departing within the next 30 days?
- **horizon absolute floor** — how low can a usable trip go anywhere in the full rolling 120-day horizon?

A good near-term fare is not automatically the horizon floor, and a far-future absolute low is not automatically useful to someone who wants to leave soon.

## Why outbound-first

Searching every origin × destination × departure date × return date × trip length × open-jaw pair is too expensive and too noisy for a daily radar.

A cheap outbound fare is an efficient discovery signal. Most destinations do not need expensive deep search on every run.

Outbound-first does **not** mean two one-way tickets are assumed cheaper. The round-trip benchmark remains mandatory where available.

## Daily radar profiles

The default daily run uses one shared discovery engine with four views rather than four unrelated full searches:

1. **World** — broad global discovery. Japan, Korea, and China remain eligible discovery destinations, but this profile does not spend deep-expansion budget on them because specialist profiles handle that work.
2. **Japan** — specialist deep search for Japan, including alternate airports, open-jaw itineraries, and practical domestic flight/rail/bus positioning.
3. **Korea** — specialist deep search for Korea, including alternate airports, open-jaw itineraries, and practical domestic flight/rail/bus positioning.
4. **China** — specialist deep search for China. This is the only default profile that activates Kinmen/Matsu ferry gateway expansion and the full China multimodal coverage gate.

The profiles share Taiwan-origin coverage and normalized candidate records. They should not perform the same broad discovery work four independent times when a shared result can be reused.

The final daily report merges the profiles into a unified ranking while preserving dedicated Japan, Korea, China, and World-other sections. World discovery may still surface Japan/Korea/China seeds, but those countries should be represented by their specialist expansion results in the dedicated sections.

## Stage A — broad discovery

Search the rolling horizon for low one-way fares from the configured Taiwan origins.

### Broad-discovery routing

The shared production broad-discovery route is intentionally different from fixed-watch monitoring and from provider-backed deep search.

ChatGPT performs this stage directly with public Web fare-index evidence. The preferred source order is:

1. public OTA/metasearch **route fare indexes** that expose actual origin/destination/date/price observations;
2. indexed exact-fare results;
3. official LCC promotion/event pages;
4. public deal editors/forums as additional seeds.

This ordering exists because a promotion announcement is not the same thing as a cheap fare observation. A carrier event page may prove that a sale, route, date range, or coupon exists while exposing no absolute price at all. It is useful intelligence, but it cannot by itself tell the radar which route/date is currently cheapest.

For each configured Taiwan origin, broad discovery should use several query shapes rather than one generic sale search:

- **origin floor scan** — exact origin IATA + rolling-horizon month/date context + cheap-flight/fare-index intent, preferably in TWD, to discover low destination floors;
- **exact route probe** — exact origin IATA + candidate destination IATA + month/date window + one-way and round-trip intent;
- **LCC carrier probe** — exact route/date context plus relevant low-cost carrier when route coverage is known and the generic fare index may under-surface it.

The route is shared across World/Japan/Korea/China profiles so the radar does not repeat the same broad scan four times. Candidate records are then handed to the appropriate specialist profile for deeper expansion.

### Two live fare floors, not one coarse target band

Broad discovery must retain both:

1. the cheapest serious **near-term** candidate departing within 30 days; and
2. the cheapest serious candidate in the complete **rolling 120-day horizon**.

A coarse heuristic such as "Korea around TWD 5k is cheap" is useful only as an early candidate trigger. It is **not a stopping condition**. The floor scan continues after such a hit because a TWD 5k near-term fare may coexist with a TWD 3–4k fare later in the horizon.

The same distinction applies during historical calibration: price observations should be compared within departure lead-time buckets when possible so a last-minute fare is not judged against a long-lead fare as though supply conditions were identical.

Public fare-index observations remain **discovery evidence**. Indexed prices can be stale, prices can change between observations, and metro-area pages can silently substitute airports. Exact airport/date/price must therefore be revalidated before a candidate is described as verified; checkout/bookability remains a separate confidence level.

This best-effort Web route does **not** claim an exhaustive fare matrix. Its purpose is high cheapness recall at low cost. Fixed watches remain coverage/provenance signals and are not expanded merely to imitate a fare matrix. GitHub Actions is not part of this normal direct-Web path unless a later deterministic collector is empirically justified.

### Korea specialist breadth

The Korea specialist must not equate "Korea" with only Seoul and Busan.

For floor discovery it should actively probe current/relevant Korean airports exposed by public fare indexes and route evidence. Initial non-exhaustive seeds are:

- `ICN` — Incheon,
- `GMP` — Gimpo,
- `PUS` — Busan/Gimhae,
- `CJU` — Jeju,
- `TAE` — Daegu,
- `CJJ` — Cheongju.

This list is deliberately a **seed list, not a permanent route whitelist**. If another Korean airport develops a relevant Taiwan fare signal inside the horizon, it remains eligible. The goal is to prevent hotspot bias while avoiding an artificial fixed fare matrix.

### Origin coverage gate

Every configured airport in `search.origin_airports` must receive a discovery attempt before a run may be described as a **full global radar**.

For v0.1 that means independent coverage attempts for:

- `TPE`,
- `TSA`,
- `RMQ`,
- `KHH`.

A source that only exposes Taipei results does not count as Taiwan-wide coverage. Results from all successfully searched origins are merged before candidate ranking, and mixed Taiwan airports may still be used for outbound and return when allowed by policy.

If an origin cannot be searched or returns unavailable data, record it as `missing` or `unavailable`. Do not silently substitute another airport and do not present the run as complete. The report should expose origin coverage so incomplete discovery is visible.

### Taiwan airport display labels

User-visible Taiwan airport labels must remain airport-specific. Do not collapse `TPE` and `TSA` into the ambiguous city label `Taipei` / `台北`.

Default labels are:

- `TPE` → `桃園（TPE）`,
- `TSA` → `松山（TSA）`,
- `RMQ` → `台中（RMQ）`,
- `KHH` → `高雄（KHH）`.

This rule applies to both outbound and return segments. If a source exposes only a metro-area label such as `Taipei` but the actual airport cannot be resolved, mark the airport as unknown rather than publishing the candidate as though `TPE` or `TSA` had been identified.

Capture at minimum:

- origin and destination,
- departure timestamp,
- displayed price and currency,
- carrier when available,
- stop count,
- source,
- observation timestamp,
- whether the result is cached/discovery-only or revalidated.

Do not discard a route merely because it is long-haul. Long-haul candidates are evaluated with longer return windows and minimum useful trip lengths.

## Stage B — candidate expansion

For the cheapest/highest-potential outbound candidates, search returns over the configured route-time-dependent window.

Candidate return forms:

1. same destination → Taiwan,
2. nearby/practical alternate city → Taiwan,
3. different Taiwan return airport,
4. one positioning segment by domestic flight, rail, bus, or ferry where allowed.

Specialist profiles may spend more expansion budget inside their target country than the World profile. The World profile prioritizes geographic breadth and unusual long-haul opportunities; Japan/Korea/China profiles prioritize depth within their country.

The system should avoid combinatorial explosion. Nearby/alternate exits should be generated from a curated transport graph or verified live transport options, not arbitrary geographic proximity.

## Stage C — complete-trip normalization

Normalize each candidate into a comparable itinerary record:

- all required transport segments,
- total required transport cost,
- first departure from Taiwan,
- arrival at first real destination,
- departure from final real destination,
- final return to Taiwan,
- total transit/connection time,
- usable destination hours,
- baggage assumptions,
- transfer risks,
- verification state.

## Stage D — round-trip benchmark

For each serious candidate, compare against a conventional round trip on the relevant route/dates when a comparable fare can be obtained.

If a normal round trip is cheaper and comparably usable, it should win even when the discovery path began with a one-way fare.

## Stage E — ranking and views

Do not collapse all user value into one opaque rank.

Always preserve at least:

- Near-Term Cheapest — minimum effective total transport cost for usable trips departing within 30 days.
- Absolute Cheapest — minimum effective total transport cost anywhere in the current rolling 120-day horizon.
- Best Value — composite price/time/trip-fit result.
- Best Short Break — strong cheap trip with low required usable days.
- Unusual Long-Haul Deal — long route that is abnormally cheap and has adequate trip length.

Historical anomaly evidence is reported alongside these live-price views rather than replacing them. A current horizon floor can be historically ordinary, and a historically exceptional fare can still lose the pure absolute-price view to a cheaper unrelated route.

## Search horizon

Default: rolling 120 days.

The horizon should move forward each run. Historical observations are retained separately and do not extend the current live search horizon.

The near-term price view is the first 30 days of that same horizon; it is not a second independent scheduler or scan. Historical comparisons should use the configured departure lead-time buckets (`0–14`, `15–30`, `31–60`, `61–120`) when enough evidence exists.

## Weekdays

v0.1 has no weekday hard gate.

Weekday, weekend, and potential leave-day information may be displayed later, but should not suppress an otherwise exceptional fare unless policy explicitly changes.

## Price verification

Search-result and metasearch prices are discovery signals, not promises.

Before calling a result a verified deal, re-check the fare through a source capable of showing the actual itinerary and current price. When final checkout cannot be verified, label the confidence/state accurately.

## Current source-router slice

Production source routing remains intentionally **partial**, but broad discovery is no longer left undefined.

The SSOT now selects two different execution slices:

1. **shared broad discovery** across World/Japan/Korea/China — `chatgpt_web_public_fare_index`, executed directly by ChatGPT Web using the ordered public fare-index/query-shape policy above; no credential and no GitHub runner are required for the normal path;
2. **China deep search** — exact round trip through FlyAI with formal `FLYAI_API_KEY`.

The router reads these selections from `flight-radar.yaml`; provider choice must not be duplicated as hidden code policy. A missing credential, unhealthy provider, unsupported open-jaw request, or otherwise unconfigured market/stage yields an explicit unavailable/unsupported coverage state. It must not silently substitute a lower-fidelity source while still claiming provider coverage.

The shared Web route is also explicit about its limits: it is a best-effort discovery backend, not a deterministic full-market matrix and not checkout verification. A cheap indexed fare may be promoted to deep search, but only a separate revalidation observation can upgrade its confidence.

FlyAI results pass a strict returned-segment airport/date gate before normalization. A `TSA-SHA` request whose returned itinerary uses `PVG`, for example, is rejected rather than relabeled. Observed FlyAI `ticketPrice` remains a raw provider value because the formal response did not expose verified currency, tax, baggage, or fare-family semantics; those normalized fields remain unknown.

FlyAI is **not** currently selected for broad discovery, true revalidation, final cross-check, or one combined open-jaw fare. Independent SearchAPI/Google Flights reference evidence found multiple low-price exact itineraries whose flight-number components were absent from the FlyAI formal exact result set, so a FlyAI-only run must never claim complete China airfare coverage. Deeper World/Japan/Korea provider-backed routing remains unconfigured until sufficient evidence justifies a production provider.
