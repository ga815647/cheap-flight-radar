# China Routing

## Purpose

China multimodal routing is a **China specialist profile**, not a requirement for every global radar run.

Normal Taiwan → mainland China air fares remain eligible in World broad discovery. The China specialist profile goes deeper by comparing:

1. Taiwan → mainland China by direct/connecting air.
2. Taiwan → Kinmen → ferry to the Xiamen/Quanzhou gateway area → mainland domestic transport.
3. Taiwan → Matsu → ferry to the Fuzhou gateway area → mainland domestic transport.
4. Open-jaw combinations where entry and exit cities differ.

## Activation rule

The Kinmen/Matsu gateway expansion and full China coverage gate apply only when the active daily profile is `china` (or an explicitly requested China deep search).

A normal World radar does **not** need to query ferry timetables or prove Kinmen/Matsu coverage. It may still discover ordinary air fares to China as part of global discovery.

## Core rule

Do not assume ferry gateways are cheaper. They are candidates that must compete on **effective total transport price + usable time + transport efficiency + disruption risk**.

A route that saves a small amount of money while consuming most of a travel day should normally lose to a simple flight.

## China coverage gate

A run may be described as a **full China deep radar** only after it has attempted all enabled entry modes configured in the SSOT:

- direct air,
- Kinmen gateway,
- Matsu gateway.

A mode does not need to produce a valid deal to count as attempted. If current fare, ferry, eligibility, schedule, or connection data cannot be obtained, mark that mode `missing`, `unavailable`, or `unverified` as appropriate. Do not silently omit it and do not claim complete China-deep coverage.

The report should expose mode coverage explicitly so that a direct-air-only search cannot be mistaken for a China-wide multimodal radar.

## Ferry data: topology vs operational facts

The **route topology** may be kept as a stable configuration: Kinmen is a possible gateway toward the Xiamen/Quanzhou area and Matsu is a possible gateway toward the Fuzhou area.

Operational facts must not be hard-coded as constants. At research time, verify live:

- operating status,
- timetable,
- fare and fees,
- terminal/port details,
- passenger eligibility,
- document requirements,
- check-in/reporting requirements.

An old or normally scheduled sailing must never be assumed to operate on the target date.

## Ferry time-cost evaluation

Do not compare only the minutes spent on the boat. Compare the ferry itinerary's **total required transport time** against the simplest comparable air itinerary.

Count, when required:

- Taiwan positioning flight and airport process,
- airport → port transfer,
- ferry check-in and waiting,
- sailing time,
- immigration/border processing,
- port → city/rail/airport transfer,
- onward mainland transport,
- the same components again if the return also uses ferry.

Expose at least two diagnostics for a serious ferry candidate:

1. **money saved per extra transport hour** versus the simpler comparable itinerary;
2. **extra transport time as a share of usable trip time**.

This prevents a short trip from looking attractive merely because a complicated gateway saves a modest amount of money.

## Ferry disruption risk

Until sufficient observed history exists, do not invent a numerical cancellation probability.

Use a qualitative `low` / `medium` / `high` disruption-risk label based on factors such as:

- number of ferry-dependent legs,
- schedule frequency and practical fallback options,
- buffer before separately ticketed onward transport,
- whether disruption could cascade into a missed flight/rail segment,
- availability of a same-day or next-day recovery path.

A ferry followed closely by a separately ticketed onward flight should receive a materially higher penalty than a ferry itinerary with generous buffer and easy alternatives.

If historical operations data is later collected, the risk model may be calibrated quantitatively; until then, uncertainty must remain explicit.

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
