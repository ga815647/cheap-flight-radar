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

- Absolute Cheapest — minimum effective total transport cost.
- Best Value — composite price/time/trip-fit result.
- Best Short Break — strong cheap trip with low required usable days.
- Unusual Long-Haul Deal — long route that is abnormally cheap and has adequate trip length.

## Search horizon

Default: rolling 120 days.

The horizon should move forward each run. Historical observations are retained separately and do not extend the current live search horizon.

## Weekdays

v0.1 has no weekday hard gate.

Weekday, weekend, and potential leave-day information may be displayed later, but should not suppress an otherwise exceptional fare unless policy explicitly changes.

## Price verification

Search-result and metasearch prices are discovery signals, not promises.

Before calling a result a verified deal, re-check the fare through a source capable of showing the actual itinerary and current price. When final checkout cannot be verified, label the confidence/state accurately.
