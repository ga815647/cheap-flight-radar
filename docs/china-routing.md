# China Routing

## Purpose

China is treated as a multimodal routing problem rather than only a set of direct international air routes.

The radar may compare:

1. Taiwan → mainland China by direct/connecting air.
2. Taiwan → Kinmen → ferry to the Xiamen/Quanzhou gateway area → mainland domestic transport.
3. Taiwan → Matsu → ferry to the Fuzhou gateway area → mainland domestic transport.
4. Open-jaw combinations where entry and exit cities differ.

## Core rule

Do not assume ferry gateways are cheaper. They are candidates that must compete on **effective total transport price + usable time + transport efficiency**.

A route that saves a small amount of money while consuming most of a travel day should normally lose to a simple flight.

## China coverage gate

A run may be described as a **full China radar** only after it has attempted all enabled entry modes configured in the SSOT:

- direct air,
- Kinmen gateway,
- Matsu gateway.

A mode does not need to produce a valid deal to count as attempted. If current fare, ferry, eligibility, schedule, or connection data cannot be obtained, mark that mode `missing`, `unavailable`, or `unverified` as appropriate. Do not silently omit it and do not claim complete China coverage.

The report should expose mode coverage explicitly so that a direct-air-only search cannot be mistaken for a China-wide multimodal radar.

## Kinmen gateway

Configured entry airport: `KNH`.

Potential routing shape:

```text
Taiwan airport → KNH → port transfer → ferry → Xiamen/Quanzhou area → rail/domestic flight → destination
```

Actual ferry terminals, timetables, eligibility, ticket prices, document requirements, and transfer times are live facts and must be verified at research time.

## Matsu gateway

Configured entry airports: `MFK`, `LZN`.

Potential routing shape:

```text
Taiwan airport → MFK/LZN → port transfer → ferry → Fuzhou area → rail/domestic flight → destination
```

As with Kinmen, live schedules and legal/document requirements must be revalidated; never copy an old timetable into a current recommendation without verification.

## Mainland expansion

Once a cheap gateway is found, the system may expand into practical onward transport:

- domestic air,
- high-speed rail,
- conventional rail,
- other verified ground transport where sensible.

The search should be gateway-first rather than province-by-province brute force. A cheap Fuzhou/Xiamen entry can then be expanded toward selected mainland hubs based on current onward fares and journey time.

## Open-jaw examples

Valid patterns include:

```text
Taiwan → Kinmen → Xiamen → Chengdu → Taiwan
Taiwan → Matsu → Fuzhou → Changsha → Wuhan → Taiwan
Taiwan → Shanghai → rail → Hangzhou → Taiwan
```

These are routing patterns only, not guaranteed fares or schedules.

## Cost normalization

China multimodal candidates must include required:

- Taiwan positioning flight,
- ferry fare,
- port/airport transfers,
- mainland rail/domestic airfare,
- return transport to Taiwan,
- required baggage and unavoidable transport-caused overnight costs.

Do not compare a ferry gateway's partial cost against a direct flight's complete round-trip cost.

## Verification and safety

Before recommending a ferry/multimodal itinerary as currently feasible, verify live:

- ferry operations and schedule,
- passenger eligibility,
- current document/entry requirements,
- minimum safe connection time,
- availability of the onward transport segment.

If any essential component is unknown, keep the candidate exploratory rather than verified.
