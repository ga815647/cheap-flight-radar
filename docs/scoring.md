# Scoring

## Principle

The radar must not confuse a low sticker price with a good trip.

Every complete itinerary exposes raw facts first, then derived component scores. The composite score is explainable and secondary to the absolute-price view.

## Core components

### 1. Effective total price

Use the normalized TWD cost defined in `flight-radar.yaml`, including transport components that are required to make the proposed itinerary work.

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

A direct or efficient one-stop itinerary should usually beat a similarly priced itinerary that burns a large fraction of the trip in transit.

## Provisional composite

The v0.1 SSOT uses:

- effective total price: 35%
- route value: 25%
- trip-length fit: 25%
- transport efficiency: 15%

These weights are **provisional**. They should be calibrated after enough real observations and user choices exist.

## Required parallel views

The UI/reporting layer must preserve separate rankings:

### Absolute Cheapest

Pure effective total transport price. This directly answers: "What is the cheapest complete trip I can take?"

### Best Value

Composite result balancing price, route value, trip fit, and efficiency.

### Best Short Break

Favor candidates that become worthwhile with relatively few usable days. A strong 2–3 day Okinawa/Seoul/Hong Kong trip should not be buried by long-haul trips.

### Unusual Long-Haul Deal

Surface routes whose price is unusually low for their route size and whose trip length is actually adequate.

## Historical calibration

Once sufficient history exists, route-value scoring should increasingly use:

- route-specific percentile,
- percentage below recent baseline,
- new observed route low,
- seasonally comparable history when available.

Historical data should refine deal detection, not fabricate precision. Sparse routes must remain explicitly low-confidence.

## Explainability

Every ranked item should be able to answer:

- What was the effective total price?
- How many usable destination hours/days are there?
- What is the efficient travel time and actual transit time?
- Which penalties were applied?
- Was the fare discovery-only or revalidated?
- Why did this item rank above/below another item?
