# Scoring

## Principle

The radar must not confuse a low sticker price with a good trip.

Every complete itinerary exposes raw facts first, then derived component scores. The composite score is explainable and secondary to the absolute-price view.

A low fare also has to be interpreted against **when the trip departs**. A fare that is excellent for travel next week may still be far above the lowest fare available somewhere in the full 120-day horizon. Those are different user questions and must remain separate.

## Core components

### 1. Effective total price

Use the normalized TWD cost defined in `flight-radar.yaml`, including material transport components that are required to make the proposed itinerary work. Short local taxi-equivalent first/last-mile access is excluded because comparable same-city itineraries also incur local airport/port access and the user does not value that small difference.

The system should retain both original-currency values and normalized TWD values when possible.

### 2. Route value

Route value asks: **for the amount of travel obtained, is the price unusually good?**

v0.1 uses travel time as the initial route-size proxy because it is broadly available. Historical route pricing should eventually become the stronger signal.

Do not use raw `hours / price` as the sole ranking rule; that would systematically favor inefficient or excessively long itineraries. Route value should use efficient one-way travel time, while excessive connection time is penalized separately.

### 3. Trip-length fit

A cheap long-haul itinerary with too little destination time is not a good deal.

The configured return windows define minimum and ideal trip lengths by typical one-way travel time. Scoring should:

- heavily penalize trips below minimum useful length,
- give full/near-full credit in the ideal range,
- avoid endlessly rewarding additional days beyond the ideal range.

Usable destination time is preferred over label-based "X days Y nights" when timestamps are available.

### 4. Transport efficiency

Transport efficiency penalizes itinerary friction, especially:

- excessive connection time,
- unnecessary backtracking,
- risky self-transfers,
- expensive positioning segments,
- avoidable overnight costs caused by transport.

Short local taxi-equivalent access is not counted as comparative transport time and does not reduce usable time. Connection feasibility still matters when that local movement feeds a fixed departure.

A direct or efficient one-stop itinerary should usually beat a similarly priced itinerary that burns a large fraction of the trip in material transit.

## Provisional composite

The v0.1 SSOT uses:

- effective total price: 35%
- route value: 25%
- trip-length fit: 25%
- transport efficiency: 15%

These weights are **provisional**. They should be calibrated after enough real observations and user choices exist.

## Required parallel views

The UI/reporting layer must preserve separate rankings rather than presenting one fare as "the cheap price" for every planning horizon.

### Near-Term Cheapest

Lowest effective total transport price among **usable complete trips departing within the next 30 days**.

This view answers: "If I want to travel soon, what is actually cheap right now?"

A near-term fare is not promoted to a 120-day fare floor merely because it is the cheapest soon-departing option. Near-term supply can carry a real lead-time premium.

### Absolute Cheapest

Lowest effective total transport price among usable complete trips in the full current rolling **120-day** live horizon.

This answers: "How low can this radar find if I am flexible about when I travel?"

The broad-discovery search must continue looking for the horizon floor even after it has already found a merely acceptable coarse price band.

### Best Value

Composite result balancing price, route value, trip fit, and efficiency.

### Best Short Break

Favor candidates that become worthwhile with relatively few usable days. A strong 2–3 day Okinawa/Seoul/Hong Kong trip should not be buried by long-haul trips.

### Unusual Long-Haul Deal

Surface routes whose price is unusually low for their route size and whose trip length is actually adequate.

## Historical anomaly is a separate price axis

"Absolute cheapest in this live horizon" and "historically unusual" are not synonyms.

Once enough observations exist, historical comparisons should match like with like where possible. The SSOT therefore groups observations by departure lead time (`0–14`, `15–30`, `31–60`, `61–120` days) and also prefers comparable route, season/month, and trip-length evidence.

A fare can therefore be:

- a strong near-term deal but not the 120-day absolute floor;
- the current 120-day absolute floor but historically ordinary for that route/season;
- historically exceptional even when another unrelated route has a lower absolute sticker price.

Sparse history must be labelled low-confidence rather than converted into a fabricated percentile.

## Historical calibration

Once sufficient history exists, route-value scoring should increasingly use:

- route-specific percentile,
- percentage below recent baseline,
- new observed route low,
- departure-lead-time-matched history,
- seasonally comparable history when available.

Historical data should refine deal detection, not fabricate precision. Sparse routes must remain explicitly low-confidence.

## Explainability

Every ranked item should be able to answer:

- What was the effective total price?
- Is it a near-term low, the current 120-day absolute floor, a historical anomaly, or more than one of these?
- How many days until departure, and which lead-time bucket applies?
- How many usable destination hours/days are there?
- What is the efficient travel time and actual transit time?
- Which penalties were applied?
- Was the fare discovery-only or revalidated?
- Why did this item rank above/below another item?
