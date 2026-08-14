# Production search recall repair — Issue #26 — 2026-08-13

Status: implementation and live-validation evidence for the Issue #26 production-search recall repair. This document does not replace `PRODUCT_INTENT.md` or `flight-radar.yaml`; it records how the runtime was brought back into alignment with them.

## Scope preserved

The substrate decision is unchanged:

- Google Flight Deals remains primary destination-free Deal discovery and external anomaly truth.
- `gflights==0.3.0` remains the keyless production acquisition substrate.
- Production construction keeps the explicit `CheapFlightRadar/0.1 (+public-research; no-proxy)` User-Agent and `proxy=None`.
- Google exact / cheapest-date / multi-city remains the completion substrate.
- ChatGPT remains scheduler/orchestrator; GitHub Actions remains disposable execution/Gate only. No GitHub cron was added.

## P1 — selection model

The runtime now separates two bounded concepts that PR #25 had conflated:

1. **destination representative** — the lowest current complete airfare for an exact destination airport across accepted Taiwan origins, used for the primary same-destination opportunity and destination-airport anomaly normalization;
2. **expansion seed pool** — competitive origin/date endpoint variants retained independently for flexible-date, mixed-Taiwan-return, and open-jaw expansion.

Destination-level normalization therefore no longer destroys expansion evidence. The CJU regression is preserved: RMQ→CJU TWD 9,023 remains the representative against the TWD 11,576 same-destination baseline rather than promoting TSA→CJU TWD 17,639 against its much higher origin-specific typical.

`search.deep_search_candidate_limit` and `search.final_shortlist_limit` are now independent. The publication limit is applied after deep completion/ranking; it does not reduce the search pool.

## P2 — endpoint recall and completion

Google Explore is attempted as bounded secondary recall for every configured Taiwan origin rather than only when Flight Deals returns zero qualified rows.

Every selected competitive endpoint may enter Google cheapest-date expansion, followed by exact completion of the selected date pair. Direct provider-selected round-trip dates remain an independent exact path.

Normalized one-way or opportunistic-Web endpoint evidence can be supplied by the ChatGPT orchestrator through `SecondaryRecallAdapter`. The adapter merges those records into the same bounded secondary-recall path while preserving their original provider, surface, airport/date identity and lack of anomaly authority. A canonical `production_runtime.run_once()` regression proves that a one-way Web TPE→ICN seed actually reaches `cheapest_dates` and exact completion; merely instantiating the adapter is not considered runtime coverage.

No city × date × city brute-force matrix was added.

## P3 — mixed Taiwan return and open-jaw

`ProductionRadar.run()` itself now generates bounded multi-city attempts for strong endpoints:

- mixed Taiwan return: `TW1 → A / A → TW2`, where `TW2` is a different SSOT primary Taiwan return airport when available;
- open-jaw: `TW1 → A / B → TW1`, where `B` is selected from the current competitive endpoint pool, preferring same country, then same market, then another competitive endpoint.

Both are priced by one Google multi-city search. Radar never synthesizes a fare by adding unrelated one-way or half-round-trip prices.

Successful mixed/open-jaw fares are attached as airfare alternatives to qualified destination opportunities. They do not receive an invented multi-city typical-price baseline and therefore do not silently become separately ranked anomaly Deals.

## P4 — execution evidence and >24h semantics

Run coverage now records actual execution counters for:

- Flight Deals;
- Explore/secondary recall;
- conventional exact round trip;
- flexible dates;
- mixed Taiwan return;
- open-jaw.

Counters distinguish attempts, returned records, successes, failures and unsupported states. Publication exposes these counters and the separate deep/publication budgets. Multi-city alternatives retain exact leg airport/date/price identity in the manifest and rendered report.

When provider segments expose a complete trip with usable clock times, the minimum-away rule uses actual arrival-to-departure elapsed time and requires more than 24 hours. When the provider does not expose enough complete-trip timing identity, the runtime retains the conservative date-based fallback rather than inventing times.

Google exact round-trip results can expose only outbound segments while retaining the requested return date in reproducible search context. Publication therefore preserves that explicit return date instead of rendering a complete round trip as if it were one-way.

## P5 — fresh production live validation

A disposable GitHub-hosted Ubuntu live-validation job ran against search-runtime head:

- commit: `5155ff270a9df0257a629bf5581c6cb680a4bc3b`
- Actions run: `31710252191`
- live evidence artifact id: `9185002447`

Observed execution evidence:

| Surface | Attempts | Live result |
|---|---:|---|
| Flight Deals | 12 | 360 records |
| Explore | 4 | 372 records |
| Conventional exact | 20 | 20 successful completions |
| Flexible dates | 20 | attempts > 0 and captured in artifact |
| Mixed Taiwan return | 4 | all attempted; provider later returned 429 and failures were retained fail-closed |
| Open-jaw | 4 | all attempted; provider later returned 429 and failures were retained fail-closed |

The artifact also proves:

- TPE, TSA, RMQ and KHH were all swept;
- the expansion pool reached 20 while the final publication limit remained 10;
- destination-airport anomaly normalization remained `exact_destination_airport_across_tpe_tsa_rmq_khh`;
- the CJU regression fixture still passed;
- zero winning open-jaw fares was not mislabeled as zero search attempts.

The one-shot live-validation workflow scaffold was removed immediately after evidence capture. The normal CI workflow returned to its prior no-cron Gate-only form.

## Completion interpretation

Three claims remain deliberately distinct:

- **capability exists** — an adapter or helper can represent a search;
- **fixture-validated runtime** — `ProductionRadar.run()` / canonical runtime actually invokes that path in deterministic tests;
- **live-validated runtime** — a fresh production-style run records nonzero real attempts and fail-closed outcomes.

Issue #26 may be called production-ready only when the final PR head also has the repository Gate green. The live artifact above is evidence for the unchanged core `ProductionRadar.run()` search orchestration; later commits only refine publication compatibility, remove the disposable validation scaffold, and add the bounded secondary-recall wrapper/regression.
