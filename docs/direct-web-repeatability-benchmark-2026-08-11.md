# Direct-Web repeatability benchmark — 2026-08-11

## Scope

Observed run time: `2026-08-11T21:25:39+08:00`.

This package completes the controlled repeatability/revalidation benchmark requested after the Japan/Korea price-history validation. It exercises the shared `chatgpt_web_public_fare_index` route across all four configured Taiwan origins (`TPE`, `TSA`, `RMQ`, `KHH`) and all four report markets (Japan, Korea, China, World).

This is a **best-effort direct-Web benchmark**, not an exhaustive fare matrix and not checkout verification. The China slice below is direct-air broad discovery only; it is **not** a full China deep-radar run and therefore does not claim Kinmen/Matsu ferry coverage.

Validated current observations from this run were written separately to the immutable history ref:

- `history/price-observations`
- `data/price-history/2026/08/11/repeatability-benchmark-20260811T212539+0800.json`

Lower indexed/sticker/metro results that failed exact-airport, exact-date, current-surface, or trip-window gates were deliberately **not** promoted into usable fare history.

## Method

Each market/origin cell received an independent discovery attempt. Query permutations included combinations of:

- exact Taiwan origin IATA + market/destination + rolling-horizon/month context;
- exact-route IATA probes with round-trip/fare intent;
- public route-fare-index and indexed exact-fare result shapes;
- opening an exact-IATA current route page for serious candidates;
- alternate indexed/route-page permutations to test whether a low headline repeated.

A fare was eligible for the current usable floor only when the current surface exposed the exact origin airport, exact destination airport, exact date pair, and a trip length compatible with the SSOT route-time return window. A lower value remained a seed when it was one-way only, metro-area unresolved, stale/not repeated after opening the current exact page, or attached to an unusably short/long itinerary.

All accepted history observations remain `verification_state=discovery`; this benchmark does not claim checkout/bookability, tax, baggage, or fare-family verification where the public page did not expose those fields.

## Controlled results by market and origin

`unknown` means the cell was attempted but this pass did not establish a defensible current exact usable complete-trip floor. It does not mean the route has no fare.

| Market | Origin | Usable 0–30d | Usable 0–120d | Lower/incomplete seed or failure mode |
|---|---|---|---|---|
| Japan | TPE | OKA 2026-09-06→09-11, TWD 5,143 | same, TWD 5,143 | indexed TPE-OKA ~TWD 4,575 did not survive current-page/usability gates; 7 nights also exceeds the 2–6 night short-haul window |
| Japan | TSA | HND 2026-09-08→09-13, TWD 16,769 | HND 2026-10-20→10-24, TWD 14,838 | older indexed route floor ~TWD 14,759 drifted from the current exact page |
| Japan | RMQ | unknown | unknown | RMQ-NRT ~TWD 8,396 surfaced on a Tokyo route page but the cheapest exact pairs were too short / route-usability evidence was insufficient for promotion |
| Japan | KHH | OKA 2026-09-08→09-11, TWD 7,543 | OKA 2026-09-29→10-02, TWD 7,243 | cheaper one-way/indexed values remain incomplete seeds |
| Korea | TPE | PUS 2026-09-09→09-15, TWD 5,272 | PUS 2026-09-20→09-22, TWD 4,588 | indexed ~TWD 4,129 same-day / ~TWD 4,142 signals did not converge to the reopened current exact page |
| Korea | TSA | GMP 2026-09-02→09-09, TWD 6,999 | same, TWD 6,999 | lower one-way values remain incomplete |
| Korea | RMQ | unknown | unknown | indexed/current route headlines drifted around TWD 5,164→4,627, but this pass did not re-establish an eligible exact date pair at the lower value |
| Korea | KHH | GMP 2026-09-05→09-08, TWD 5,340 | GMP 2026-10-01→10-06, TWD 5,276 | route headline ~TWD 5,175 belonged to a 16-night itinerary and is unusable |
| China direct-air | TPE | PVG 2026-08-27→08-31, TWD 8,125 | PVG 2026-10-01→10-06, TWD 6,794 | older indexed ~TWD 3,096 was one-way/incomplete and materially below the current exact surface |
| China direct-air | TSA | unknown | unknown | FOC route headline ~TWD 8,341; surfaced exact pairs were 16+ nights and failed the short-haul window |
| China direct-air | RMQ | unknown | unknown | FOC exact route seed ~TWD 9,967 surfaced, but route-time/usability evidence was insufficient to promote it in this pass |
| China direct-air | KHH | PVG 2026-08-30→09-04, TWD 7,667 | same, TWD 7,667 | current route floor ~TWD 4,755 was attached to a 7-night trip, longer than the 2–6 night window |
| World | TPE | BKK 2026-09-04→09-09, TWD 9,017 | same, TWD 9,017 | indexed TPE-DMK ~TWD 5,453 did not survive current exact-page revalidation and remains a deep-search seed |
| World | TSA | unknown | unknown | TSA-HKG ~TWD 9,349 surfaced, but this pass did not establish enough route-time evidence to promote the 8-night pair |
| World | RMQ | HAN 2026-08-27→09-01, TWD 7,426 | HAN 2026-09-18→09-23, TWD 7,030 | the same HAN date pair also surfaced at TWD 7,413; MFM 2026-10-01→10-07 surfaced at both TWD 7,044 and TWD 7,352 |
| World | KHH | DMK 2026-09-09→09-13, TWD 5,899 | same, TWD 5,899 | route floor ~TWD 5,680 belonged to a 14-night itinerary and is unusable |

## Market-level retained floors

These are floors found in this controlled pass, not claims of exhaustive market minima.

| Market | Usable 0–30d floor | Usable 0–120d floor | Lower seed retained for deep search/revalidation |
|---|---:|---:|---:|
| Japan | TPE-OKA TWD 5,143 | TPE-OKA TWD 5,143 | ~TWD 4,575 indexed/unusable-stale signal |
| Korea | TPE-PUS TWD 5,272 | TPE-PUS TWD 4,588 | ~TWD 4,129 indexed same-day / non-converged signal |
| China direct-air | KHH-PVG TWD 7,667 | TPE-PVG TWD 6,794 | KHH-PVG TWD 4,755 exact but 7-night unusable route-floor pair; indexed TPE-PVG ~TWD 3,096 one-way remains incomplete |
| World | KHH-DMK TWD 5,899 | KHH-DMK TWD 5,899 | indexed TPE-DMK ~TWD 5,453 requiring current exact revalidation |

## Repeatability measurements

### Origin/market attempt coverage

- market × Taiwan-origin cells attempted: **16/16 (100%)**;
- cells where this controlled pass established at least one defensible current exact usable complete-trip observation: **11/16 (68.75%)**;
- unknown cells remain explicit rather than being filled from metro labels, old index snippets, or plausible trip assumptions.

The 68.75% figure is a controlled-pass usable-observation yield, **not** a statistical estimate of global fare recall. It mainly captures how often a current public route surface exposed enough exact airport/date/usability evidence during this pass.

### Price convergence / staleness

Direct-Web query permutations did not behave like a deterministic fare matrix:

- TPE-OKA route/index evidence around TWD 4,575 did not converge to the reopened current exact route page, whose retained usable pair was TWD 5,143;
- TPE-PUS indexed values around TWD 4,129–4,142 did not become the current usable exact floor; the reopened exact route retained TWD 4,588 for 2026-09-20→09-22 and TWD 5,272 for the near-term 2026-09-09→09-15 pair;
- TPE-PVG older indexed one-way ~TWD 3,096 was materially below the current exact route one-way surface and was not promoted;
- within a single current RMQ-HAN route surface, the exact 2026-09-18→09-23 pair appeared at TWD 7,030 and TWD 7,413, a **5.45%** spread;
- within a single current RMQ-MFM route surface, the exact 2026-10-01→10-07 pair appeared at TWD 7,044 and TWD 7,352, a **4.37%** spread.

The two same-pair duplicate samples therefore show a 4.37–5.45% current-surface divergence. `n=2` is intentionally too sparse to turn into a stable general error-rate claim.

### Exact-airport integrity

Metro/route-page substitution remains a real failure mode. Concrete permutations observed pages/search results where:

- a `KHH-SHA` context exposed `KHH-PVG` itineraries;
- a `TPE-SHA` context exposed `TPE-PVG` itineraries;
- a `TPE-GMP` search context exposed a `TSA-GMP` itinerary.

These observations validate the SSOT rule: route-page or metro labels cannot authorize an exact airport identity. Only the individual itinerary's resolved IATA pair is accepted into price history. No accepted history observation in this run relies on metro-airport inference.

## Historical baseline state

This snapshot adds real observed evidence but does not manufacture historical precision. Existing history is still sparse for most comparable route/trip-type/lead-time buckets.

Therefore:

- 7/30/90-day median remains `unknown` where fewer than 3 prior comparable run-level samples exist;
- historical percentile remains `unknown` where fewer than 10 prior comparable samples exist;
- `historical_floor` is not emitted unless the SSOT's 10-prior-sample requirement is met;
- `unusually_low` remains uncalibrated;
- no indexed seed or duplicate query sighting is counted as an extra historical sample.

## Architecture decision

The benchmark confirms that direct Web is **not deterministic**, but the observed failure modes are currently manageable through the existing exact-airport, trip-usability, current-page revalidation, and `unknown` gates.

The evidence does **not** show a systematic acquisition failure that justifies an ephemeral deterministic collector in this package, and it provides no justification for a persistent crawler platform. The normal path therefore remains:

`ChatGPT direct-Web discovery → exact-route/deep-search revalidation → validated immutable price-history snapshot`

GitHub Actions remains disposable compute/crawler/Gate only. No GitHub cron, daemon, queue, durable Actions state service, or parallel scheduler is added.

## Next evidence target

The next radar cycle should use this snapshot as prior history, re-probe the current market floors, and spend extra deep-search effort on the cells that remained `unknown` here (especially RMQ Japan/Korea and TSA/RMQ China/World) plus the lower indexed seeds that failed current exact revalidation. A collector should be reconsidered only if repeated cycles show a material, reproducible direct-Web recall failure that exact-page/deep-search permutations cannot repair.
