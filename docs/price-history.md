# Price History and Fare Baselines

## Purpose

Price history exists to answer a different question from the live floor scan.

The radar keeps three independent price views:

1. **near-term floor** — the lowest usable complete trip in the current radar run departing within 0–30 days;
2. **rolling-horizon absolute floor** — the lowest usable complete trip in the current radar run across the complete 0–120 day horizon;
3. **historical anomaly evidence** — how a current usable fare compares with prior comparable observations for the same route and departure lead-time conditions.

These views must not be collapsed. A fare can be excellent for travel next week while still being far above a cheaper departure 70 days away. Conversely, the current 120-day floor can be historically ordinary for that route, while another higher-priced route may be a new historical low.

## State model

The durable source of truth for history is an **append-only observation event log** supplied by the ChatGPT/orchestrator runtime. Baselines are derived from that log on each radar run; the derived median/percentile/low values are not a second authoritative state store.

GitHub Actions may emit normalized observation batches when ChatGPT delegates deterministic compute, crawling, or Gate work. Actions is not the durable history service, scheduler, daemon, queue, or database. The caller chooses the persistent storage location available to the orchestrator.

Validated data snapshots may be archived separately, but repository snapshots are not required runtime state.

Synthetic historical backfill is forbidden. If the radar has not actually observed enough comparable fares, the corresponding baseline, percentile, or anomaly label is unknown.

## Observation contract

A history event represents what the radar knew at a specific observation time. Baseline-eligible observations require:

- `radar_run_id`;
- exact Taiwan origin airport;
- exact destination airport;
- departure date;
- exact trip type;
- normalized effective total transport price in TWD;
- `fare_scope=usable_complete_trip`;
- observation timestamp;
- source identity and, when available, source URL;
- verification state;
- availability state.

Original currency/price is retained when available.

Availability states are:

- `available` — the observation exposed a usable fare at observation time;
- `stale` — the signal remains useful provenance but must not be treated as a current fare;
- `disappeared` — a previously observed fare can no longer be found in the follow-up observation.

`stale` and `disappeared` events remain in history. They are excluded from current live floors. A prior `available` event does not disappear from history merely because a later event says the fare disappeared; it remains evidence that the fare was once observed.

## Current live floors

Current live floors use observations belonging to the **current `radar_run_id` only**. Historical events from older runs cannot silently satisfy the current floor.

Only current-run events with:

- `availability_state=available`,
- `fare_scope=usable_complete_trip`, and
- a valid normalized TWD price

are eligible.

The near-term floor uses departures 0–30 days from the run time. The absolute floor uses departures 0–120 days from the run time. The two winners may be different observations.

## Comparable historical sample

For v0.1, the mandatory comparison key is:

- exact origin airport;
- exact destination airport;
- trip type;
- departure lead-time bucket.

The lead-time buckets are the SSOT values:

- `d0_14` — 0–14 days;
- `d15_30` — 15–30 days;
- `d31_60` — 31–60 days;
- `d61_120` — 61–120 days.

Each historical observation is bucketed using **its own observation time versus its own departure date**. This prevents a fare seen 7 days before departure from being naively compared with one seen 90 days before departure.

Season/month and comparable trip length are additional dimensions only when enough history exists. They must never be applied by shrinking a sample below the configured minimum and then pretending the smaller result is precise.

The current observation is excluded from its own historical baseline. Only earlier observation timestamps may contribute.

## Moving robust baseline

The robust baseline statistic is the median, not the mean.

The system independently computes moving medians from comparable observations seen in the prior:

- 7 days;
- 30 days;
- 90 days.

A window requires at least **3 comparable observations**. With fewer than 3, that window returns unknown rather than an imputed value.

The primary recent baseline is the 30-day median. If it is unavailable, the fallback order is 90-day then 7-day. The fallback does not manufacture a missing 30-day baseline; reporting should preserve which window was actually used.

## Rolling lows

The system independently computes comparable historical lows over:

- 30 days;
- 90 days;
- 365 days;
- all observed history.

A rolling low can be reported from one real prior observation because it is a factual minimum, but it must carry the associated sample count/confidence. A one-sample low is **not** enough to call a fare a historical anomaly or "神價".

## Historical percentile

The route-specific percentile is an empirical midrank percentile over the full comparable prior sample.

It requires at least **10 comparable historical observations**. Below 10, percentile is unknown.

Lower percentiles mean cheaper relative to history. The metric is evidence, not a market-level fixed TWD threshold.

## Percentage below baseline

For the selected recent median baseline:

`percent_below_baseline = (baseline_twd - current_twd) / baseline_twd * 100`

Positive values mean the current fare is cheaper than the baseline. If no recent median is available, the value is unknown.

The result must preserve the selected baseline window and sample count so a percentage cannot appear more precise than its evidence.

## Distance from historical low

When a prior comparable low exists:

- amount distance = `current_twd - historical_low_twd`;
- percentage distance = `(current_twd - historical_low_twd) / historical_low_twd * 100`.

A value of zero means the current fare ties the prior low; a negative value means it establishes a new observed low. The low and its sample count must be reported together.

## Confidence

Confidence is based on the number of comparable historical price observations:

- `none`: 0;
- `sparse`: 1–2;
- `low`: 3–9;
- `medium`: 10–29;
- `high`: 30+.

This is evidence-density confidence, not a promise that a discovery fare is bookable. Verification state remains a separate axis and should be reported alongside the sample count.

## Historical anomaly labels

The system may call a current fare a `historical_floor` only when:

- it is at or below the prior all-time comparable low; and
- there are at least 10 prior comparable price observations.

`unusually_low` is intentionally **uncalibrated** in the current SSOT. Until accumulated evidence supports a threshold, the system exposes percentile, median delta, rolling lows, and confidence without inventing an `unusually_low` cutoff.

Sparse history returns `insufficient_history` rather than a percentile or historical-low claim.

## Staleness and disappearance provenance

A later stale/disappeared event should reference the prior observation when possible. This permits the report to answer:

- where the fare was first seen;
- when it was last seen available;
- when it became stale or disappeared;
- which source produced each state transition.

A stale/disappeared event never makes the old fare currently purchasable again. It is retained only as historical provenance.

## Radar-run update sequence

For each scheduled ChatGPT radar run:

1. perform current fixed-watch/opportunistic/deep-search/revalidation work according to the existing orchestrator policy;
2. normalize usable fare observations and stale/disappeared follow-up events;
3. append new events to the durable history log without rewriting prior events;
4. compute the current-run 0–30 day and 0–120 day live floors;
5. compare serious current fares with prior route + lead-time-matched history;
6. expose median windows, rolling lows, percentile where supported, baseline delta, low distance, sample count/confidence, and provenance;
7. leave the formal SSOT unchanged unless accumulated evidence justifies a methodology change.

A single market swing therefore changes observations and derived metrics, not the system's methodology.
