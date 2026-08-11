# Price-history controlled live validation — 2026-08-11

## Scope

This is a controlled Japan/Korea validation of the new price-history contract, not a complete four-market benchmark and not an exhaustive fare matrix.

Observed run time: `2026-08-11T21:01:36+08:00`.

The run intentionally checks three separate questions:

1. can a usable 0–30 day fare differ from the usable 0–120 day floor?
2. do indexed/query-permutation results remain discovery evidence until exact airport/date/usability checks succeed?
3. does sparse real history remain sparse instead of fabricating medians, percentiles, or a historical-low label?

Current observations from this validation were archived to the durable GitHub history ref `history/price-observations`; the prior Issue #10 Korea checkpoint was migrated separately as real observed evidence. No synthetic historical backfill was created.

## Controlled source/query shapes

The primary current surface was the exact-IATA Expedia Taiwan route page, opened on 2026-08-11:

- `TPE-OKA`: https://www.expedia.com.tw/en/lp/flights/tpe/oka/taipei-to-naha
- `TPE-KIX`: https://www.expedia.com.tw/en/lp/flights/tpe/kix/taipei-to-osaka
- `TPE-PUS`: https://www.expedia.com.tw/en/lp/flights/tpe/pus/taipei-to-busan
- `RMQ-ICN`: https://www.expedia.com.tw/en/lp/flights/rmq/icn/taichung-to-seoul

Permutations also included indexed search results, cross-locale Expedia pages, Skyscanner route pages, and metro-area forms such as `TPE-OSA` / `RMQ-SEL`. The wider forms are useful for recall but are not allowed to establish exact-airport history unless the individual result resolves the exact airport.

All prices below remain discovery/public-fare-surface evidence, not checkout guarantees. Tax/baggage/fare-family fields not exposed by the surface remain unknown.

## Japan — near-term and horizon floor separate after usability

### TPE → KIX

The exact route page reported an overall round-trip floor around `TWD 5,556`, but the surfaced fare producing that value was `2026-08-26 → 2026-09-11`, a 16-night trip.

The same page reports an average route time around 3h41. Under the SSOT `<=4h` return window, a normal candidate must be 3–8 nights. Therefore the 16-night sticker floor is not a usable complete-trip floor for the radar.

Usable current examples on the same exact route page were:

- **near-term**: `2026-09-02 → 2026-09-09`, 7 nights, 22 days to departure, `TWD 8,363`, lead bucket `d15_30`;
- **horizon**: `2026-10-31 → 2026-11-05`, 5 nights, 81 days to departure, `TWD 7,570`, lead bucket `d61_120`.

Result: the controlled Japan sample correctly keeps the near-term usable fare separate from the cheaper later-horizon usable fare. It also proves that a route-page sticker minimum cannot bypass the trip-usability gate.

### TPE → OKA stale/indexed signal

An indexed exact-route result exposed `2026-10-12 → 2026-10-14` around `TWD 4,702`. When the exact TPE-OKA page was opened during this validation, that exact pair was no longer among the surfaced current fares; a current usable near-term example was `2026-09-06 → 2026-09-11`, 5 nights, `TWD 5,143`.

The `TWD 4,702` observation is therefore archived as `stale` discovery provenance, not as the current 120-day floor. This is intentionally conservative: absence from the currently surfaced page does not prove the fare never exists, but it is insufficient evidence to call it currently purchasable.

The exact page also reports an average TPE-OKA flight time around 1h35, so the SSOT short-haul 2–6 night window applies. An indexed `2026-09-19 → 2026-09-26` 7-night fare around `TWD 4,575` is cheaper sticker evidence but does not qualify as a usable complete-trip floor under this window.

## Korea — clean two-floor separation

### TPE → PUS

The current exact TPE-PUS page surfaced:

- **near-term**: `2026-09-09 → 2026-09-15`, 6 nights, 29 days to departure, `TWD 5,272`, lead bucket `d15_30`;
- **horizon**: `2026-09-20 → 2026-09-22`, 2 nights, 40 days to departure, `TWD 4,588`, lead bucket `d31_60`.

A current Skyscanner exact-airport route page reports an average direct TPE-PUS flight time around 2h21, placing the route in the SSOT `<=2.5h` 2–6 night window. Both examples therefore pass the trip-length search window.

Result: the current Korea sample cleanly proves that a good near-term fare can be materially above the 120-day horizon floor.

An indexed Expedia permutation advertised a lower route-level round-trip floor around `TWD 4,129` without an exact complete date pair in the surfaced result. Opening the current exact route page instead produced the exact `TWD 4,588` pair above. The lower number remains a deep-search/revalidation seed and is not written as a usable complete-trip history price.

### RMQ → ICN usability / exact-airport gate

The exact current RMQ-ICN page surfaced `2026-09-09 → 2026-09-16`, 7 nights, `TWD 4,927`, which is a usable near-term observation. The page reports an average route time around 3h41, so the SSOT 3–8 night window applies.

The same page's lower advertised round-trip floor `TWD 4,627` was attached to `2026-09-15 → 2026-09-16`, only 1 night. A `TWD 4,821` pair was 2 nights. Neither can silently replace the usable floor.

The exact page also explicitly lists GMP as an alternate Seoul airport. A generic `RMQ-SEL` query can improve recall but cannot itself authorize `SEL → ICN`; the individual itinerary must resolve the airport. The same rule applies to generic Osaka `OSA` versus KIX/ITM/UKB.

## Real historical comparison — sparse means sparse

Before this package there was no formal durable fare-history store. The only backfill performed was a migration of the already-recorded Issue #10 Korea checkpoint (`issuecomment-5252862716`) into the new GitHub history ref. That checkpoint contained real exact usable observations such as:

- TPE-PUS `2026-09-20 → 2026-09-22` around `TWD 4,588`;
- RMQ-ICN `2026-09-09 → 2026-09-16` around `TWD 4,927`.

The current validation repeated both exact route/date/price observations.

Under the new baseline rules:

### Current TPE-PUS horizon fare (`TWD 4,588`)

- lead bucket: `d31_60`;
- comparable prior run-level samples: **1**;
- confidence: `sparse`;
- prior all-time factual low: `TWD 4,588`;
- distance from prior low: `TWD 0` / `0%`;
- 7/30/90-day median baseline: **unknown** (needs at least 3 samples);
- historical percentile: **unknown** (needs at least 10 samples);
- `historical_floor` label: **not allowed** (needs at least 10 prior comparable samples);
- `unusually_low` label: not emitted because the SSOT threshold is intentionally uncalibrated.

This is an important guard: tying the only prior observed low does **not** become a claim that this is a statistically meaningful historical floor.

### Current RMQ-ICN fare (`TWD 4,927`)

The same result applies: one prior comparable sample, `sparse` confidence, factual all-time low can be shown, but moving median / percentile / historical-floor label remain unknown or absent.

### Current TPE-PUS near-term fare (`TWD 5,272`)

Its lead bucket is `d15_30`. The prior TPE-PUS checkpoint observation is `d31_60`, so it contributes **zero** comparable samples to this near-term baseline. Same route alone is not enough to cross lead-time buckets.

Japan has no defensible prior comparable durable samples in the new history ref, so its historical median/percentile/anomaly fields remain unknown. No old chat value was manufactured into production history.

## Query-permutation recall / staleness / airport integrity

This small controlled sample is not large enough for a production-quality recall statistic, but it exposes the important failure modes:

- **Route recall:** exact-IATA current pages produced usable exact-route observations for all four controlled route families (`TPE-OKA`, `TPE-KIX`, `TPE-PUS`, `RMQ-ICN`).
- **Floor convergence:** query/index permutations did not reliably converge on one current usable floor. At least TPE-OKA and TPE-PUS exposed lower indexed numbers that could not be promoted after current exact-page/usability checks.
- **Staleness:** the indexed TPE-OKA `TWD 4,702` exact pair was not repeated on the current opened exact page and was retained only as stale provenance.
- **Airport integrity:** exact-IATA pages preserved OKA/KIX/PUS/ICN. Generic `OSA` / `SEL` forms are useful recall surfaces but fail the exact-airport evidence gate until the individual itinerary resolves KIX/ITM/UKB or ICN/GMP.
- **Duplicate inflation:** different query permutations and sources in one radar run remain provenance. They do not count as multiple historical market samples or raise confidence.

The evidence supports continuing to use direct Web for discovery while retaining mandatory exact-airport/usability/revalidation gates. It does **not** yet justify building a new persistent crawler platform. The broader four-market repeatability benchmark remains a separate next package.

## Durable state created

Data-only durable history ref:

- `history/price-observations`
- prior evidence snapshot: `data/price-history/2026/08/11/issue10-korea-depth-5252862716.json`
- current validation snapshot: `data/price-history/2026/08/11/jp-kr-price-history-validation-20260811T210136+0800.json`

The snapshots are immutable evidence. GitHub Actions is not the durable database; it may only be used as disposable compute when future history aggregation becomes too large for direct orchestration.
