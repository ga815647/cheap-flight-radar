# Airfare search substrate bake-off — 2026-08-13

Status: durable evidence for `flight-radar.yaml` source-routing convergence in PR #22.

## Decision

Cheap Flight Radar does **not** need to build its own broad airfare search engine or make its own price-history model the primary anomaly authority.

Production routing selected by this bake-off:

1. **Google Flight Deals** is the primary route-relative anomaly truth and destination-free Deal discovery surface.
2. **`gflights==0.3.0` (`nas-/google-flights-rs`, MIT)** is the selected keyless acquisition substrate for Google Flight Deals, Explore, exact search, flexible dates and multi-city/open-jaw. Production use must force a fixed explicit project User-Agent and `proxy=None`; do not use its default rotating browser User-Agent pool.
3. **Google Flights exact search / price insight** is the next anomaly-truth authority when it exposes qualified route-relative price context, and is also the preferred exact completion/revalidation substrate.
4. **Repository price history remains valuable, but only as supplemental evidence and fallback anomaly truth.** It is not required to establish a Deal when a higher-priority qualified external truth source is available.
5. **Expedia airport-origin Web** is the first destination-free fallback/recall surface. **Kiwi Anywhere** and **Skyscanner Everywhere** remain secondary seed/cross-check surfaces, not anomaly authorities.
6. **`punitarani/fli`** is a useful exact/flexible-date comparator/fallback, not destination-free discovery or anomaly truth.
7. **`MikkoParkkola/trvl`** is research-only, not production core. Its broad feature set did not compensate for currency-fidelity, provider-noise, reliability, license and uTLS-fingerprint costs observed in the live run.
8. No paid/trial/unknown-quota airfare API is a production dependency. Expedia Rapid, Kiwi Tequila and Skyscanner Flights API do not pass the current TWD-0 production gate.

The formal Deal truth conflict order is therefore:

`google_flight_deals` → `google_flights_exact_price_insight` → `own_price_history`

Conflicting anomaly estimates are **never averaged**.

## Why Google Flight Deals changes the architecture

Google's public Flight Deals product already supplies the core primitive the product needs: current round-trip airfare together with a typical-price comparison and percentage below typical. Google's product documentation describes Flight Deals as using historical prices for similar trips and ranking savings by percentage before absolute price. This maps directly to `PRODUCT_INTENT.md`: route-relative anomaly first, current complete airfare second.

That means a destination-free Google Flight Deals result can already be a serious complete-airfare candidate. The Radar no longer has to force every discovery through `cheap one-way → construct return → build own anomaly baseline` before it knows whether a route is genuinely unusual.

## GitHub-hosted Ubuntu live evidence

All live probes ran on clean GitHub-hosted Ubuntu 24.04 runners with no airfare API credentials. The one-shot workflows are research scaffolding only and are removed from the durable branch after evidence capture.

### `gflights` production-style probe

Workflow run `31618916741`, job `94188521229`, `gflights==0.3.0`.

The client was instantiated with:

- currency `TWD`
- locale `zh-TW` / `TW`
- fixed User-Agent `CheapFlightRadar/0.1 (+public-research; no-proxy)`
- `proxy=None`

Observed successful surfaces:

- exact TPE→NRT round-trip search: 21 results, TWD prices, including Tigerair Taiwan, Peach, Jetstar Japan and China Airlines;
- TPE Explore: 88 destinations;
- TSA Explore: 88 destinations;
- RMQ Explore: 109 destinations;
- KHH Explore: 88 destinations;
- Google Flight Deals: 30 results for each of TPE, TSA, RMQ and KHH;
- TPE→NRT three-month cheapest-date query: 84 date pairs;
- multi-city/open-jaw query TPE→NRT + KIX→KHH: 10 results.

Representative Deal records demonstrated exact origin airport, exact destination airport/city, outbound and return dates, TWD current price, typical price, discount percentage, airline and a Google booking/search URL:

| Origin | Destination | Current RT | Typical | Discount |
|---|---|---:|---:|---:|
| TPE | FKS | TWD 12,097 | TWD 39,759 | 70% |
| TSA | GMP | TWD 7,648 | TWD 12,350 | 38% |
| RMQ | KMG | TWD 13,382 | TWD 26,748 | 50% |
| RMQ | ICN | TWD 4,984 | TWD 7,658 | 35% |
| RMQ | SYD | TWD 21,436 | TWD 35,458 | 40% |
| KHH | ISG | TWD 7,297 | TWD 20,971 | 65% |

This passed the important guardrail test: the selected path did not require proxy rotation, residential IP, CAPTCHA bypass, credential/session bypass, or TLS-fingerprint impersonation. The library's default rotating browser User-Agent is deliberately not accepted for production; the fixed-UA run proved it is unnecessary.

### `fli`

`flights==0.9.0` successfully returned current TWD exact-route and flexible-date results for Taiwan/Japan, Korea, China, Hong Kong and Australia samples after installation was corrected.

The clean-wheel install exposed a packaging-maintenance defect: the CLI imports `click` but the wheel did not install it automatically, so the runner needed explicit `pip install flights click`. This is acceptable for a fallback comparator, but another reason not to make `fli` the primary production substrate. It also lacks an equivalent destination-free Deals/typical-price surface.

### `trvl` v1.21.4

Live Explore calls returned destinations for all four Taiwan origins, and the tool exposes exact, flexible-date, Explore and multi-city features. However the same run also observed:

- `--currency TWD` still producing USD output on tested flight/date paths;
- default flight aggregation mixing Google, Kiwi, Skiplagged and other providers rather than preserving one clean truth authority;
- provider 429/403 failures and noisy warnings;
- self-connect/split-ticket composition in default results;
- Google-provider implementation using uTLS/browser TLS fingerprint impersonation;
- PolyForm Noncommercial 1.0 licensing rather than a permissive production-core license.

No existing fingerprint guardrail needs to be weakened for `trvl`; it is not selected for production.

## Consumer Web/API findings

### Google Flights

- Flight Deals: primary Deal discovery/anomaly truth.
- Explore: strong destination-free endpoint discovery, but not every result has complete anomaly context.
- exact search / flexible date grid / multi-city: strong completion and revalidation surfaces.
- no qualified public airfare-shopping API was found for this use case; Google's public Travel Impact Model API is emissions data, not airfare search.

### Expedia

The public Taiwan airport-origin pages for TPE/TSA/RMQ/KHH can expose unknown destinations and one-way/round-trip deal cards and are directly usable by ChatGPT Web. They are good recall/fallback seed surfaces but do not expose a sufficiently explicit route-normal typical-price anomaly measure to become primary truth.

Expedia Rapid API requires authorization/partner access and new applications are currently constrained; it therefore fails the TWD-0 production API gate.

### Kiwi

Kiwi's public Anywhere/Anytime surface supports destination-free discovery, flexible dates and multi-city/NOMAD-style exploration and exposes Taiwan-origin results. It is useful as secondary recall/open-jaw inspiration, but does not supply the same qualified typical-price anomaly authority as Google Flight Deals.

Tequila API is not accepted as production core because new partnerships are invitation-based rather than a demonstrated recurring-free full-Radar quota.

### Skyscanner

Skyscanner Everywhere/flexible consumer Web remains useful as a secondary broad seed/cross-check source. Its API requires partnership approval and the available quota is not established as long-term free and sufficient for a complete daily Radar run. The indicative endpoint can also be cached, so it is not promoted to current Deal truth.

## 14-dimension bake-off matrix

Legend: `P` production-selected, `S` secondary/seed, `F` fallback/comparator, `R` research-only, `N` not qualified.

| Substrate | Unknown destination | OW / RT | Flexible horizon | Airport identity | Typical/anomaly truth | Fresh/reproducible | Exact itinerary | Open-jaw | TW LCC/FSC recall | ChatGPT Web | GH free runner | Key/login/anti-bot/license | TWD 0 | Qualified truth role |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Google Flight Deals via `gflights` | P | RT | broad provider-selected dates | exact IATA | **P: typical + discount %** | live-proven | dates/carrier + exact follow-up | via exact substrate | strong live sample | official Web also usable | **P live-proven** | keyless; fixed UA/no proxy; MIT client | **P** | **primary** |
| Google Explore via `gflights` / Web | P/S | mainly complete trip seeds | month/duration | city + flight airport | partial/no uniform anomaly | live-proven | follow-up required | exact substrate | strong | yes | live-proven | same client rules | P | seed only unless anomaly supplied |
| Google exact via `gflights` / Web | destination known | OW/RT | graph/grid/cheapest dates | exact IATA | price insight where exposed | live-proven | **P** | **P live-proven** | strong | yes | **P live-proven** | same client rules | P | secondary truth / primary completion |
| Expedia airport-origin Web | S | OW/RT | page-dependent | airport-origin, destination cards | no qualified normal | indexed/live | follow-up | multi-city Web exists | useful | **yes** | not selected runner scraper | no login for public pages; API gated | P Web | seed/fallback only |
| Kiwi Anywhere Web | S | OW/RT | strong | city/airport | no qualified normal | Web-current variable | follow-up | strong/NOMAD | useful | yes | not core runner path | public Web; API invite gate | P Web | seed only |
| Skyscanner Everywhere Web | S | OW/RT | strong | city/airport | no qualified normal for Radar | Web/indicative freshness varies | follow-up | multi-city available | useful | yes | not core runner path | API partnership/quota gate | P Web | seed/cross-check only |
| `fli` 0.9.0 | no | OW/RT | **F** | exact IATA | no | live-proven | **F** | library supports multi-city | good tested sample | n/a | yes after `click` workaround | keyless, MIT | yes | exact/flex fallback only |
| `trvl` 1.21.4 | yes | OW/RT | yes | mixed provider semantics | no clean authority | inconsistent providers | yes/noisy merge | yes | broad | n/a | live but noisy | uTLS path; PolyForm NC; provider failures | **failed fidelity test** | R |

## Search architecture conclusion

The evidence supports a shared, endpoint-driven search rather than market-specific deep-search engines:

1. Run destination-free Google Flight Deals from **each of TPE/TSA/RMQ/KHH**.
2. Run Google Explore / fallback consumer Web surfaces when they add recall.
3. Filter to Asia/Oceania production scope while preserving Japan, Korea and China as priority coverage slices.
4. A qualified complete round-trip Deal may proceed directly to current exact revalidation; do **not** split it into fictitious one-way halves.
5. Cheap one-way, Explore-only or weaker Web seeds are expanded only for endpoints that remain competitive.
6. For those endpoints, query flexible exact round-trip and open-jaw alternatives. Do not enumerate every city × date × city combination.
7. Formal Deal ranking is route-relative anomaly descending, then current complete airfare ascending.

The 120-day window remains a sensible normal compute budget, but not a permanent product boundary. Market-specific specialist pipelines may be added only if future measured recall demonstrates that the shared substrate misses meaningful Deals.

## Policies retired or demoted

The bake-off evidence justifies the following executable-SSOT convergence:

- `global` production scope → Asia/Oceania;
- absolute-cheapest / near-term cheapest as first-class Deal semantics → diagnostic/transition views only;
- outbound-one-way-first as mandatory architecture → one accepted seed path among direct RT Deal discovery;
- route trip-length fit / transport-efficiency / connection / self-transfer penalties → not formal Deal ranking inputs;
- ferry gateways → outside product scope;
- own price history → supplemental/fallback anomaly authority;
- fixed-watch success → Signal freshness, not Radar Deal coverage authority;
- China FlyAI specialist deep pipeline → no longer required; shared exact Google substrate covers normal airfare completion;
- 120 days → default compute budget, not durable product meaning.

Historical price observations, prior research documents and old policy rationale are retained as evidence/history rather than deleted.
