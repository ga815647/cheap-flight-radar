# Scoring

## Principle

The radar must not confuse a low sticker price with a good trip.

Every complete itinerary exposes raw facts first, then derived component scores. Absolute price and the explicit product views remain user-facing truth. A composite score may help the search pipeline order candidates internally, but it is **not a published winner** and there is no user-facing `Best Value` report view.

A low fare also has to be interpreted against **when the trip departs**. A fare that is excellent for travel next week may still be far above the lowest fare available somewhere in the full 120-day horizon. Those are different user questions and must remain separate.

## Core components

### 1. Effective total price

Use the normalized TWD cost defined in `flight-radar.yaml`, including material transport components that are required to make the proposed itinerary work. Short local taxi-equivalent first/last-mile access is excluded because comparable same-city itineraries also incur local airport/port access and the user does not value that small difference.

**Lodging is not part of effective transport price, including a hotel night caused by an overnight connection.** Nights are already represented by trip length and usable-time semantics; charging lodging again inside transport cost would double-count the same itinerary consequence. A bad overnight can still fare worse through unusable connection time or trip-length fit, but not through an invented mandatory hotel-cost surcharge.

The system should retain both original-currency values and normalized TWD values when possible.

### 2. Route value

Route value asks: **for the amount of travel obtained, is the price unusually good?**

v0.1 uses travel time as the initial route-size proxy because it is broadly available. Historical route pricing should increasingly become the stronger signal as evidence accumulates.

Do not use raw `hours / price` as the sole rule; that would systematically favor inefficient or excessively long itineraries. Route value should use efficient one-way travel time, while unusable connection time is penalized separately.

### 3. Trip-length fit

A cheap long-haul itinerary with too little destination time is not a good deal.

The configured return windows define search/fit guidance by typical one-way travel time. They are not hard maximum-trip-length gates. Scoring should:

- heavily penalize trips below minimum useful length;
- give full/near-full credit in the ideal range;
- avoid endlessly rewarding additional days beyond the ideal range;
- never reject a trip merely for exceeding a preferred `max_nights` search window.

Usable destination time is preferred over label-based "X days Y nights" when timestamps are available.

Verified excursion time during a long connection may be tracked separately as `usable_stopover_hours` and counted as usable trip time. Do not blindly count the whole scheduled layover: only the portion that remains genuinely usable after immigration/entry feasibility, airport or station access, baggage/recheck needs, and safe connection buffers may receive that treatment.

### 4. Transport efficiency

Transport efficiency measures itinerary friction, especially:

- unusable connection or waiting time;
- unnecessary backtracking;
- risky self-transfers;
- expensive positioning segments.

A **long connection is not inherently inefficient**. If a connection provides a verified practical stopover that can be used to visit the connection city, the usable excursion hours are removed from the waiting-time penalty. This credit is capped at the practical efficient-travel baseline: a deliberately longer routing cannot score better than an otherwise equivalent efficient itinerary merely because more stopover hours were inserted.

For example, an itinerary with an efficient baseline of 8 hours and 20 elapsed transport/connection hours normally has a time-efficiency ratio of `8 / 20 = 0.4`. If 10 of those hours are verified usable stopover time, the penalized transport time becomes 10 hours and the time ratio becomes `8 / 10 = 0.8`. If enough usable stopover time would reduce penalized transport below 8 hours, efficiency remains capped at `1.0` rather than receiving a bonus.

Self-transfer, re-entry, missed-connection, baggage, and similar risks remain separate penalties. A pleasant stopover does not erase those risks. Overnight lodging remains outside effective transport price; only the time itself is judged as usable stopover time or unusable waiting time.

Short local taxi-equivalent access is not counted as comparative transport time and does not reduce usable time. Connection feasibility still matters when that local movement feeds a fixed departure.

## Internal composite heuristic

The v0.1 SSOT retains provisional component weights:

- effective total price: 35%;
- route value: 25%;
- trip-length fit: 25%;
- transport efficiency: 15%.

These weights are **provisional** and the resulting composite is only an internal candidate-ordering heuristic. It may decide which superficially similar candidates deserve scarce deep-search/revalidation effort. It must not:

- create a `Best Value` user-facing winner;
- hide the Absolute Cheapest or Near-Term Cheapest result;
- replace the explicit Best Short Break or Unusual Long-Haul views;
- be presented as calibrated preference truth.

Raw component values remain useful for explainability and future calibration even though the composite winner is not published.

## Required user-facing views

The reporting layer preserves explicit views rather than collapsing all user value into one opaque rank.

### Near-Term Cheapest

Lowest effective total transport price among **usable complete trips departing within the next 30 days**.

This answers: "If I want to travel soon, what is actually cheap right now?"

A near-term fare is not promoted to a 120-day fare floor merely because it is the cheapest soon-departing option. Near-term supply can carry a real lead-time premium.

### Absolute Cheapest

Lowest effective total transport price among usable complete trips in the full current rolling **120-day** live horizon.

This answers: "How low can this radar find if I am flexible about when I travel?"

The broad-discovery search must continue looking for the horizon floor even after it has already found a merely acceptable coarse price band.

### Best Short Break

Surface strong cheap trips that become worthwhile with relatively few usable days. A strong 2–3 day Okinawa/Seoul/Hong Kong trip should not be buried by longer trips.

This view is selected from verified usable candidates using explicit trip duration, price, route fit, and friction evidence; it is not simply the highest composite score.

### Unusual Long-Haul Deal

Surface long routes whose price is unusually low for their route size and whose trip length is actually adequate. If no candidate converges, publish that absence rather than fabricating a winner.

## Historical anomaly is a separate price axis

"Absolute cheapest in this live horizon" and "historically unusual" are not synonyms.

Once enough observations exist, historical comparisons should match like with like where possible. The SSOT groups observations by departure lead time (`0–14`, `15–30`, `31–60`, `61–120` days) and also prefers comparable route, season/month, and trip-length evidence when sufficient history exists.

A fare can therefore be:

- a strong near-term deal but not the 120-day absolute floor;
- the current 120-day absolute floor but historically ordinary for that route/season;
- historically exceptional even when another unrelated route has a lower absolute sticker price.

Sparse history must be labelled low-confidence rather than converted into a fabricated percentile.

## Historical calibration

As sufficient history accumulates, candidate interpretation can increasingly use:

- route-specific percentile;
- percentage below recent baseline;
- new observed route low;
- departure-lead-time-matched history;
- seasonally comparable history when available.

Historical data should refine deal detection, not fabricate precision. Sparse routes must remain explicitly low-confidence. The publication layer follows the minimum sample thresholds in `flight-radar.yaml`; in particular it does not render a numeric percentile below the configured threshold.

## Explainability

Every published item should be able to answer:

- What was the effective total price?
- Is it a near-term low, the current 120-day absolute floor, a historical anomaly, or more than one of these?
- How many days until departure, and which lead-time bucket applies?
- How many comparable historical samples exist and what confidence does that imply?
- Which rolling low/recent baseline is actually supported, and what is the percentage below that baseline when available?
- Is a percentile supported by the SSOT sample threshold?
- How many usable destination hours/days are there when known?
- Did any connection contain verified `usable_stopover_hours`, and what portion remained pure waiting time?
- What is the efficient travel time and actual transit time when known?
- Which penalties or practical risks were applied?
- Was the fare discovery-only or revalidated?
- Why was it selected for the explicit view or market section?

The report must not answer the final question with "because it won Best Value." Composite ordering, if used, stays internal.
