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
- material airport / port transfer that is more than short local access,
- ferry check-in and waiting,
- sailing time,
- immigration/border processing,
- material port → city/rail/airport transfer when it is intercity or otherwise a real routing leg,
- onward mainland transport,
- the same components again if the return also uses ferry.

### Short local access normalization

Short local first/last-mile movement that can normally be handled by taxi or ordinary local transit is **not part of the comparative deal cost or comparative transport time**. A conventional same-city air trip also requires local airport access, so exact taxi fare/minutes add noise without improving the gateway decision.

For this class of movement:

- do not require an exact fare or duration;
- do not fail-close a candidate solely because that exact local fare/time is missing;
- do not deduct it from usable destination time or add it to extra transport time;
- still confirm that the connection is physically practical when it feeds a time-sensitive ferry or separately ticketed segment.

Examples that may be ignored for cost/time when practically short and local include `KNH ↔ Shuitou`, `Wutong ↔ Xiamen local anchor`, or an ordinary airport ↔ same-city taxi. This exception does **not** apply to a real intercity leg such as `Huangqi ↔ Fuzhou`, to ferry/rail/domestic-air travel, to check-in/waiting, or to a transport-caused overnight.

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

Actual ferry terminals, timetables, eligibility, ticket prices, and document requirements are live facts and must be verified at research time. For short local taxi-equivalent access, verify only that the connection is practically feasible; exact fare/minutes are not required or scored.

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

## Mixed-routing decision loop

The 2026-08-11 live PVG stress run showed that the generic gateway idea needs a small repeatable decision contract rather than a city whitelist or brute-force matrix.

### 1. Trigger gateway expansion

Expand a mainland arrival airport only after it becomes a **serious gateway seed** with current exact fare evidence and at least one verified practical onward or open-jaw edge.

A trip exceeding the default `return_windows.max_nights` is not rejected for that reason. Return windows remain search and trip-fit guidance; exact fare, complete transport cost, time, and verification state determine whether the candidate survives.

### 2. Select second cities from transport edges

Do not choose second cities from geographic proximity alone. Generate them from current verified transport edges and compare the complete itinerary.

Prefer high-speed rail when the verified rail path has lower required transport time and transfer friction than a domestic flight for the same expansion. Use domestic air when rail is absent or materially worse after station/airport access, check-in, transfer, and connection time are included.

Open-jaw exits should be considered when a current verified exit fare can reduce backtracking or improve complete transport cost/time. Do not infer a one-way open-jaw fare by dividing a round-trip fare or by reusing a route headline from unrelated dates.

### 3. Normalize before comparing

For every surviving expansion, normalize:

- complete required transport cost,
- required transport time,
- usable destination time,
- extra transport time versus the simplest same-gateway round trip,
- self-transfer / separately ticketed connection risk,
- baggage and fare-scope assumptions,
- current verification state for every essential component.

The conventional same-city round trip remains the benchmark even when the mixed itinerary is the desired travel pattern.

### 4. Stop expansion early

Stop expanding a branch when any of these becomes true:

- the next required segment cannot be currently revalidated;
- complete effective cost or required transport time cannot be normalized;
- the candidate no longer competes with the round-trip benchmark or already-evaluated expansions on price/time/route value;
- the configured deep-search candidate budget is reached.

This stop rule is intentionally evidence-based and contains no permanent numeric China fare threshold. A future low-fare gateway can therefore trigger the same procedure without changing policy.

### 5. Final revalidation fails closed

A serious mixed itinerary needs exact airports/dates for air segments, current prices for all priced required segments, and live schedules for time-sensitive rail/ferry segments. If an essential component remains unknown, retain the route as an exploratory seed rather than promoting it to a verified finalist.

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
- material port/airport transfers that are not short local taxi-equivalent access,
- mainland rail/domestic airfare,
- return transport to Taiwan,
- required baggage and unavoidable transport-caused overnight costs.

Short local taxi-equivalent access is deliberately excluded from both comparative cost and comparative transport time; only connection feasibility remains relevant.

Do not compare a ferry gateway's partial cost against a direct flight's complete round-trip cost.

## Verification and safety

Before recommending a ferry/multimodal itinerary as currently feasible, verify live:

- ferry operations and schedule,
- passenger eligibility,
- current document/entry requirements,
- minimum safe connection time,
- availability of the onward transport segment.

If any essential component is unknown, keep the candidate exploratory rather than verified.
