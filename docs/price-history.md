# Current price-history role — 2026-08-13 substrate convergence

Price history remains durable evidence, but it is no longer the mandatory or preferred anomaly engine. This section supersedes older text below where repository history appears to be required to decide whether a fare is unusually cheap. Existing immutable observations and comparison code are retained rather than deleted.

Current authority order:

1. qualified Google Flight Deals typical-price / discount evidence;
2. qualified Google Flights exact price insight when available;
3. repository `history/price-observations` comparable history as fallback and supplemental context.

An external source qualifies only when the relevant surface is stable enough for production use, the current price can be reproduced closely enough to identify the same airfare, and it exposes a typical price or explicit route-relative anomaly magnitude. Conflicting qualified sources are resolved by the explicit priority above; values are never averaged. A formal Deal does not require repository history when a higher-priority qualified authority already supplies anomaly truth.

Repository history still supports provenance, route observations that lack external typical-price context, fallback percentile/baseline metrics, disappearance/staleness analysis, and future source audits. Synthetic backfill remains forbidden.

---

# Price History and Fare Baselines

## Purpose

Price history answers a different question from the live floor scan.

The radar keeps three independent price views:

1. **near-term floor** — the lowest usable complete trip in the current run departing within 0–30 days;
2. **rolling-horizon absolute floor** — the lowest usable complete trip in the current run across the complete 0–120 day horizon;
3. **historical anomaly evidence** — how a current usable fare compares with prior comparable observations for the same route and departure lead-time conditions.

These views must not be collapsed. A fare can be excellent for travel next week while still being above a cheaper departure 70 days away. Conversely, the current 120-day floor can be historically ordinary while another higher-priced route is a new observed route low.

## Evidence state versus presentation state

The durable source of truth for fare history is **GitHub repository data on `history/price-observations`**, not ChatGPT memory, a GitHub Actions artifact, a rendered Pages file, or a publication manifest.

Publication is deliberately separate:

- `history/price-observations` contains immutable fare-evidence snapshots;
- `publication/radar-reports` contains append-only presentation manifests selecting report sections and recording coverage/failed seeds;
- GitHub Pages contains deterministic HTML derived from those two inputs plus policy/code on `main`.

A presentation manifest never becomes a historical price sample. A failed/non-converged seed can be shown publicly without fabricating a fare-history observation.

## State model

The SSOT uses a dedicated durable evidence ref, `history/price-observations`, containing immutable per-radar-run snapshots. The default path shape is:

`data/price-history/YYYY/MM/DD/{radar_run_id}.json`

Each run creates one new snapshot file and never rewrites an older run snapshot. Baselines, percentiles, and lows are derived from snapshots when needed; derived values are not a second authoritative state store.

ChatGPT remains scheduler/orchestrator/decision layer. It may create a validated snapshot directly through the GitHub connector. When data volume or aggregation justifies it, ChatGPT may delegate short-lived GitHub Actions compute. The Action remains disposable compute; the evidence ref is the durable store.

GitHub Actions artifacts are short-term handoff/deployment material only and must not become the 365-day/all-time history source.

If the history ref does not exist, initialize empty history without fabricated backfill. Synthetic historical backfill is forbidden. Missing evidence remains unknown.

Validated history-snapshot writes are data-only updates. They do not authorize policy/code changes or imply a merge to `main`.

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
- `stale` — the signal remains provenance but must not be treated as current;
- `disappeared` — a previously observed fare can no longer be found on follow-up.

Stale/disappeared events remain in history. They are excluded from current live floors. A prior `available` observation remains evidence that the fare was once observed even after it later disappears.

## Current live floors

Current live floors use observations belonging to the **current `radar_run_id` only**. Older history cannot silently satisfy a current floor.

Only current-run events with:

- `availability_state=available`;
- `fare_scope=usable_complete_trip`; and
- a valid normalized TWD price

are eligible.

Near-term floor uses departures 0–30 days from run time. Absolute floor uses 0–120 days. Winners may differ.

## Comparable historical sample

For v0.1, the mandatory comparison key is:

- exact origin airport;
- exact destination airport;
- trip type;
- departure lead-time bucket.

The SSOT lead-time buckets are:

- `d0_14` — 0–14 days;
- `d15_30` — 15–30 days;
- `d31_60` — 31–60 days;
- `d61_120` — 61–120 days.

Each observation is bucketed using **its own observation time versus its own departure date**. This prevents a fare seen 7 days before departure from being naively compared with one seen 90 days before departure.

A radar run contributes at most **one comparable price sample** for the same exact route + trip type + lead-time bucket. Multiple Web query permutations, editors, OTAs, or duplicate sightings in the same run are provenance, not independent market samples. If a run contains multiple usable complete-trip observations for one comparison key, the run-level historical sample is the lowest observed usable complete-trip price.

Season/month and comparable trip length are additional dimensions only when enough history exists. They must not shrink a sample below thresholds and then pretend the smaller result is precise.

The current observation is excluded from its own baseline. Only observations with timestamps earlier than the current observation can contribute. This time ordering is also what guarantees that a future low cannot alter the historical metrics on an older permanent run page.

## Moving robust baseline

The robust baseline statistic is the median.

The system independently computes moving medians from comparable observations seen in the prior:

- 7 days;
- 30 days;
- 90 days.

A window requires at least **3 comparable observations**. Fewer than 3 returns unknown rather than an imputed value.

Primary recent baseline is the 30-day median. If unavailable, fallback order is 90-day then 7-day. Reporting preserves which actual window was selected.

## Rolling lows

The system independently computes comparable historical lows over:

- 30 days;
- 90 days;
- 365 days;
- all observed history.

A rolling low can be reported from one real prior observation because it is a factual minimum, but it must carry sample count/confidence. A one-sample low is not enough to call a fare a historical anomaly.

## Historical percentile

Route-specific percentile is an empirical midrank percentile over the full comparable prior sample.

It requires at least **10 comparable prior observations** under the current SSOT. Below 10, percentile is unknown and the public page must **omit the numeric percentile**, not print a fabricated placeholder.

Lower percentiles mean cheaper relative to comparable history. The metric is evidence, not a fixed TWD threshold.

## Percentage below baseline

For the selected recent median baseline:

`percent_below_baseline = (baseline_twd - current_twd) / baseline_twd * 100`

Positive values mean current is cheaper than baseline. If no qualifying median exists, the percentage is unknown. The report preserves baseline window and evidence density.

## Distance from historical low

When a prior comparable low exists:

- amount distance = `current_twd - historical_low_twd`;
- percentage distance = `(current_twd - historical_low_twd) / historical_low_twd * 100`.

Zero ties the prior low; negative establishes a new observed low. The prior low and sample count must be interpreted together.

## Confidence

Confidence is evidence density, not a promise of bookability:

- `none`: 0 comparable prior samples;
- `sparse`: 1–2;
- `low`: 3–9;
- `medium`: 10–29;
- `high`: 30+.

Verification state remains a separate axis and is shown alongside historical confidence.

## Historical anomaly labels

A current fare may be called `historical_floor` only when:

- it is at or below the prior all-time comparable low; and
- at least 10 prior comparable price observations exist.

`unusually_low` remains intentionally **uncalibrated** in the current SSOT. Until evidence supports a threshold, publish the underlying percentile/median delta/lows/confidence rather than inventing an `unusually_low` cutoff.

Sparse history returns insufficient-history semantics rather than false precision.

## Staleness and disappearance provenance

A later stale/disappeared event should reference the prior observation when possible so the system can answer where a fare was first seen, last available, and later stale/disappeared.

A stale/disappeared event never makes an old fare currently purchasable. It remains historical provenance only.

## Radar-run persistence and publication sequence

For each scheduled ChatGPT Radar run:

1. load fixed-watch state and perform current fixed-watch/opportunistic/deep-search/revalidation work according to orchestration policy;
2. normalize usable fare observations and stale/disappeared follow-up events;
3. validate and **persist one immutable current-run snapshot first** on `history/price-observations`;
4. reload/read persisted history needed for comparison;
5. compute current-run 0–30 day and 0–120 day live floors;
6. compare serious current fares with prior route + trip-type + lead-time-matched history;
7. derive median windows, rolling lows, percentile only when supported, baseline delta, low distance, sample count/confidence, and provenance;
8. append the run's presentation manifest on `publication/radar-reports`;
9. let the manifest push invoke the disposable static build/deploy workflow.

This ordering intentionally differs from treating a rendered report as state. If deployment fails, the validated fare evidence has already been persisted and can be republished without searching fares again.

Adding later history must not rewrite an older run's historical meaning. The static generator enforces this by comparing each run only to observations whose timestamps are earlier than that run; deterministic tests rebuild an old page after adding a later much-lower fare and require byte-identical output.

See `docs/publication.md` for Pages paths, manifest semantics, and deployment architecture.
