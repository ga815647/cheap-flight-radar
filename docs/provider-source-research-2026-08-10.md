# Airfare provider source research — 2026-08-10

Status: research checkpoint; credentialed provider benchmark still required before implementing a production collector.

Observation window: 2026-08-10, Asia/Taipei.

This document records evidence for choosing airfare data sources by **market × search stage × acquisition method**. It does not override `flight-radar.yaml`; unknown values stay unknown until they are measured.

## 1. Research question

Cheap Flight Radar should not ask one provider to do every job. The target architecture is a source router that chooses a provider from:

- market/profile: Japan, Korea, China, World/other;
- stage: broad discovery, deep search, revalidation, final cross-check;
- acquisition method: ChatGPT direct, API/feed, permitted scraper fallback, or benchmark-only.

The key distinction is between a low price displayed in discovery and an itinerary/fare that can still be found close to purchase time.

## 2. Fixed empirical basket

Unless a source cannot represent the condition, use one adult, economy, round trip, currency retained as returned by the source, and record baggage/fare family separately. Broad-discovery tests use the outbound leg first, matching the SSOT.

| ID | Market | Basket | Why |
|---|---|---|---|
| J1 | Japan | TPE-NRT 2026-10-13 / 2026-10-17 | popular route; LCC + FSC |
| J2 | Japan | TSA-HND 2026-10-13 / 2026-10-18 | exact airport identity; FSC-heavy |
| J3 | Japan | RMQ-KIX 2026-10-13 / 2026-10-17 | non-Taipei origin; direct/1-stop coverage |
| J4 | Japan | KHH-FUK 2026-10-13 / 2026-10-17 | non-Taipei origin; regional/LCC coverage |
| J5 | Japan deep | TPE-NRT 2026-10-13; KIX-TPE 2026-10-18 | open-jaw capability |
| K1 | Korea | TPE-ICN 2026-10-13 / 2026-10-17 | popular route; LCC + FSC |
| K2 | Korea | KHH-PUS 2026-10-13 / 2026-10-17 | secondary route; regional carrier coverage |
| C1 | China | TSA-SHA 2026-10-13 / 2026-10-17 | downtown-airport identity; FSC |
| C2 | China | TPE-XMN 2026-10-13 / 2026-10-17 | China gateway; useful for later multimodal expansion |
| S1 | Southeast Asia | TPE-SGN 2026-10-13 / 2026-10-17 | LCC + FSC |
| L1 | Long haul | TPE-LAX 2026-10-13 / 2026-10-23 | long-haul direct/connection benchmark |

Every observation must retain source, observation timestamp, requested and returned airports, dates, currency, tax/baggage semantics when visible, cache/live semantics, and verification state.

## 3. What ChatGPT Web could actually read

The current ChatGPT Web environment was tested directly; public accessibility was not assumed to imply machine readability.

| Source | ChatGPT direct | Empirical result |
|---|---|---|
| Google Flights | Partial | Public route/discovery pages are readable and useful for broad benchmarking, including Taiwan-origin suggestions. Exact-date queries did not reliably preserve the requested basket dates. City aggregation can combine airports, so returned segment airports must be re-checked. |
| Skyscanner | Partial | Route pages expose fares, airlines and LCC examples. Exact basket dates were not reliably preserved by Web search. This is useful manual evidence, not a deterministic collector. |
| Trip.com | Partial | Airport-pair pages expose itinerary snippets, recent-low semantics, LCC/FSC and taxes/fees text. Exact requested dates were not reliably preserved. A TSA-SHA airport-pair page also surfaced a round-trip example whose return used PVG-TPE, demonstrating that every segment airport must be validated instead of trusting the page title. |
| Naver Flights | No for core results | Help/documentation pages are readable, but the core `flight.naver.com` result surface was blocked in the current Web environment. Do not plan a ChatGPT-direct Korea collector around it. |
| skyticket | Partial | Japan route pages are readable and often preserve exact airport-pair distinctions, but dates are page/default observations rather than a deterministic exact-date query in this environment. |
| Qunar | Partial | Static route/SEO pages are readable but can be city-level and stale; insufficient for exact-airport live collection. |
| Fliggy consumer web | Partial/No for fare extraction | Search UI is visible but exact fare results were not reliably extractable through current Web access. |
| Airline fare pages | Partial | Some carrier pages expose dated fare observations. ANA returned the exact J1 date pair in search evidence; Korean Air/EVA pages returned useful current route/date observations. These are still marketing/search fare observations, not checkout confirmation. |

### Direct-Web conclusion

No tested consumer site currently provides a sufficiently deterministic **exact-date, exact-airport, unattended** collector through ChatGPT Web alone. ChatGPT direct remains useful for research, benchmark and final human-style cross-checks, not as the production data pipeline.

## 4. Provider evidence

### 4.1 Skyscanner APIs

Primary evidence:

- Indicative Prices API: https://developers.skyscanner.net/docs/flights-indicative-prices/overview
- Live Prices API: https://developers.skyscanner.net/docs/flights-live-prices/overview
- API limits: https://developers.skyscanner.net/docs/getting-started/rate-limits
- API key/partnership: https://developers.skyscanner.net/docs/getting-started/authentication

Evidence summary:

- Indicative is explicitly intended for exploratory cases where destination and/or dates are not fully known.
- Indicative prices may be cached up to four days: strong for broad discovery, not final validation.
- Live Prices searches exact route/date inventory; create can return a partial cached set and polling completes the result set.
- Access requires a Skyscanner partnership/API key and is oriented around searches that lead users toward booking/deeplinks.
- Documented standard rate limits are high enough for a staged radar, subject to granted-key limits.

Decision: strongest candidate for **World/Japan/Korea broad discovery + deep search**, if partnership eligibility fits this product. Do not scrape Skyscanner if proper API access is available.

### 4.2 Travelpayouts

Primary evidence:

- Flight data/API documentation: https://support.travelpayouts.com/hc/en-us/articles/203956163-Data-API
- Flight Search API rules: https://support.travelpayouts.com/hc/en-us/articles/210995808-How-to-use-Flight-Search-API

Evidence summary:

- Data API is cached and suitable for static/low-fare data; recent-price endpoints expose discovery observations rather than guaranteed live offers.
- Its real-time Flight Search API is intended for user-initiated searches and explicitly disallows automatic collection of search results.
- Therefore real-time Travelpayouts must not be the unattended daily collector.

Decision: possible **secondary cached broad-discovery feed** after a token-backed Taiwan-origin coverage test; not a production live revalidation source.

### 4.3 Duffel

Primary evidence:

- Offer requests: https://duffel.com/docs/api/offer-requests
- Offers: https://duffel.com/docs/api/offers
- Pricing: https://duffel.com/pricing

Evidence summary:

- Requires known origin, destination and date slices, so it is not an "anywhere / flexible horizon" discovery engine.
- Offer retrieval/refresh is designed to return an up-to-date offer close to booking; offers can expire quickly.
- Public pricing is compatible with low-volume deep search, but excess-search economics matter for a radar with a very high search-to-order ratio.
- Exact Taiwan LCC/FSC coverage must still be measured with access credentials.

Decision: high-potential **deep-search/revalidation secondary**, not broad discovery.

### 4.4 Amadeus Self-Service

Primary evidence:

- Flight APIs overview: https://developers.amadeus.com/self-service/category/flights
- FAQ/coverage: https://developers.amadeus.com/support/faq/about-self-service-apis

Evidence summary:

- Provides cached inspiration/cheapest-date APIs plus live Flight Offers Search/Price workflows.
- Self-Service documentation states that some major US carriers and low-cost carriers are not returned; negotiated/special fares are also not the same as every consumer channel.
- That omission conflicts with Cheap Flight Radar's LCC-first completeness requirement.

Decision: at most a secondary FSC/sanity source. Do **not** prioritize engineering or credentials for v0.1.

### 4.5 Trip.com

Primary evidence:

- Consumer route pages tested through Trip.com public flight pages.
- Partner/developer material: https://developers.trip.com/

Evidence summary:

- Public route pages have excellent human-readable LCC/FSC coverage and often state that displayed lows were found in the last 24 hours; many routes claim real-time updates.
- They are useful benchmark evidence, but the current ChatGPT Web path did not deterministically preserve exact dates.
- Airport-pair page titles are not sufficient proof that every returned segment uses those airports; returned itinerary airports must be normalized.
- Public developer material does not expose a general self-service consumer airfare search API comparable to Skyscanner Live; flight connectivity is partnership/restricted.

Decision: strong **benchmark/manual cross-check**, API partnership candidate only after higher-priority sources; scraper is fallback-only and should not be promoted while better API paths remain.

### 4.6 Google Flights

Primary evidence:

- Consumer Google Flights pages tested through current Web search.

Evidence summary:

- Excellent broad-discovery and price-benchmark UX, and public route pages expose Taiwan-wide route ideas.
- Current ChatGPT Web access is not a deterministic exact-date API, and city-level pages can group TPE/TSA or destination metro airports.
- No supported public consumer-airfare collection API was identified in this research.

Decision: **benchmark-only/manual discovery**. Do not spend engineering time on a production Google Flights scraper.

### 4.7 Japan regional: skyticket / Travel.jp

Primary evidence:

- skyticket flight route pages: https://skyticket.com/
- Travel.jp airfare/LCC comparison: https://www.travel.co.jp/

Evidence summary:

- skyticket pages expose Taiwan-Japan airport-pair variants and Japanese-market carrier/LCC prices; useful for finding discrepancies a global provider might miss.
- Travel.jp is useful as Japan-local comparison evidence but is less natural as a Taiwan-origin automated feed.
- No production-grade public airfare API was identified for either during this research.

Decision: **Japan benchmark layer**, especially skyticket; scraper only if later API benchmarks show a persistent Japan-specific gap large enough to justify maintenance.

### 4.8 Korea regional: Naver Flights

Primary evidence:

- Naver Flights help: https://help.naver.com/service/5626
- Naver developer portal: https://developers.naver.com/

Evidence summary:

- Naver says it compares current prices from multiple Korean and overseas sellers for the same flight.
- Its low-price graph/calendar is based on recent user searches and can differ from the current bookable price: it is discovery evidence, not revalidation.
- The core result surface was not readable through the current ChatGPT Web environment.
- No public Naver airfare API suitable for this collector was identified.

Decision: valuable **Korea-local benchmark**, but not an automated collector. Scraper: avoid.

### 4.9 China regional: Fliggy FlyAI

Primary evidence:

- FlyAI documentation: https://open.alitrip.com/docs/flyai/
- Alibaba/FlyAI repository: https://github.com/alibaba/FlyAI

Evidence summary:

- 2026 FlyAI is materially more relevant than legacy seller/open-platform APIs for this project.
- Its flight-search capability accepts structured origin/destination, departure/return date or date ranges, direct/connecting constraints, cabin, transfer city, duration, max-price and sorting parameters, with structured JSON output and booking/deeplink fields.
- Public material describes connection to Fliggy product/inventory data and current bookable search results; highly volatile offers may require following a jump URL for the latest quote.
- A formal API key is recommended for stable/higher-volume use. Public rate limits and total cost for this use case were not established in this research.
- Runtime installation could not be tested in the current execution container because its package/network environment could not fetch the FlyAI package/repository. This is an environment limitation, not evidence of provider failure.

Decision: highest-priority **China specialist deep-search/revalidation candidate**. Obtain access and run the fixed basket before considering a China fare scraper.

### 4.10 China regional: Qunar

Primary evidence:

- Public Qunar airfare route pages tested through Web search.

Evidence summary:

- Useful China-market fare benchmark, but the pages observed were static/city-oriented and less fresh than the best global/Trip evidence.
- Exact airport and exact target-date extraction was not reliable enough for production use in current access.

Decision: **China benchmark-only** for now. Do not build a Qunar scraper before FlyAI/API benchmarking.

### 4.11 Airline websites

Carrier pages are the final existence/cross-check layer, not the broad collector. They have perfect own-inventory scope but no cross-carrier coverage and inconsistent automation interfaces.

Evidence from this run included an ANA page returning the J1 date pair and current dated Korean Air/EVA fare pages. Search/marketing fares can still differ at checkout; final state should remain `revalidated` or `cross_checked` unless the fare is actually carried to a purchase surface.

Decision: **final cross-check**, selectively automated only when an official carrier API/feed is available; otherwise manual/ChatGPT direct fallback.

## 5. Empirical price-comparison limitation

The requested metric "lowest-price hit rate / gap to lowest verifiable fare" is intentionally **unknown** at this checkpoint.

Reason:

1. Google Flights, Skyscanner, Trip.com and regional consumer pages could be read at route level, but Web search did not consistently preserve the exact fixed basket dates.
2. Skyscanner Live, Duffel and FlyAI need real API access to run the same exact basket programmatically.
3. A route-page low from a different date is not comparable to an exact-date carrier fare.
4. No checkout surface was reached consistently enough to label a cross-provider price `bookable`.

Observed route-page examples still proved useful for coverage/LCC evidence: Trip.com exposed Tigerair Taiwan on KHH-FUK, VietJet on TPE-SGN, and long-haul TPE-LAX options; however these observations must not be turned into a fabricated exact-basket winner.

## 6. Decision matrix

| Market | Broad discovery | Deep search | Revalidation | ChatGPT/manual benchmark | Final cross-check |
|---|---|---|---|---|---|
| World/other | **Skyscanner Indicative** if access; Travelpayouts Data API as cached secondary after coverage test | **Skyscanner Live**; Duffel secondary | **Duffel offer refresh/get** or Skyscanner Live | Google Flights + Trip.com | carrier/OTA itinerary page |
| Japan | **Skyscanner Indicative** | **Skyscanner Live**; Duffel secondary; compare skyticket benchmark | Duffel / Skyscanner Live | skyticket + Google Flights + Trip.com | airline site |
| Korea | **Skyscanner Indicative** | **Skyscanner Live**; Duffel secondary | Duffel / Skyscanner Live | Naver Flights is Korea-local benchmark; Trip/Google as accessible secondary | airline site / seller page |
| China | shared Skyscanner Indicative for World seed discovery | **FlyAI first**, Skyscanner Live secondary | **FlyAI latest quote/deeplink**, then Skyscanner/Duffel where useful | Trip.com + Qunar + Fliggy consumer pages | airline/OTA/deeplink destination |

This intentionally allows different provider stacks by country and stage.

## 7. Source router recommendation

Yes: build a source router rather than sending every query to one provider.

Suggested routing inputs:

```text
profile
origin_airport
destination_country / destination_airport
search_stage
exact_dates_known
flexible_date_range
open_jaw_requested
required_freshness
provider_health
provider_access_available
```

Suggested output is an ordered provider plan, not one hard-coded provider. Each provider attempt must emit source health and coverage state. Failure must not silently substitute an airport, market, or lower-quality cache source while still claiming full coverage.

Routing sketch:

```text
World broad -> Skyscanner Indicative
  unavailable -> Travelpayouts cached discovery (if exact-origin coverage passes)
  manual benchmark -> Google Flights

Japan/Korea deep -> Skyscanner Live -> Duffel secondary
China deep -> FlyAI -> Skyscanner Live secondary

revalidation -> provider live/refresh path -> final carrier/OTA cross-check
```

No rule may translate `Taipei` into TPE or TSA without segment-level airport evidence.

## 8. Per-source operational scorecard

Qualitative values reflect current evidence; `unknown` means not measured.

| Source | Best use | Bad use | Direct | API | Scraper | Price competitiveness | Coverage | Freshness | Automation stability | Operational burden | Access/cost | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Skyscanner | broad + live deep | final truth without revalidation | Partial | Restricted | Avoid | High potential; exact basket pending | High potential incl. LCC | Indicative <=4d cache; Live current | High if access | Medium | partnership; commercial details unknown | High capability / Medium access |
| FlyAI | China deep + revalidation | assume global-anywhere discovery before test | Partial | Yes, access/key recommended | Avoid | unknown pending basket | strong China/global claim; Taiwan basket pending | real-time/latest-quote semantics | promising | Low-Medium | rate/cost unknown | Medium-High |
| Duffel | exact deep + revalidation | broad flexible discovery | No | Yes | N/A | unknown for Taiwan | broad airline claim; exact LCC basket pending | high | High | Medium | public usage/search economics | High capability / Medium coverage |
| Travelpayouts | cached broad secondary | unattended real-time collection | N/A | Yes/Restricted-by-use | Avoid | unknown | Taiwan exact-origin pending | cached/recent; not final | Medium | Low | affiliate token; live automation constrained | High on policy |
| Trip.com | benchmark, manual cross-check | exact-date unattended collector via Web | Partial | Restricted | Fallback only | strong visible LCC/FSC examples; exact basket unknown | High visible | often <=24h on route pages | Low via Web | High if scraped | partnership details unknown | High benchmark |
| Google Flights | broad/manual benchmark | production scraper | Partial | No supported public fare API found | Avoid | strong benchmark | High but metro aggregation risk | current discovery pages, exact semantics variable | Low via Web | High if scraped | manual access | High benchmark |
| Naver Flights | Korea-local seller benchmark | ChatGPT collector | No core result access | No suitable public fare API found | Avoid | likely strong Korea benchmark; exact basket not measured | High seller comparison claim | search real-time; graph cached | Low | High if scraped | manual | High role / no automation |
| skyticket | Japan-local benchmark | primary unattended collector | Partial | No suitable public fare API found | Fallback only | promising Japan/LCC benchmark | good Japan/TW route pages | page-dependent | Low | High if scraped | manual | Medium |
| Qunar | China benchmark | production collector now | Partial | unknown current consumer fare API | Avoid for now | unknown | strong China-market relevance | observed pages can be stale | Low | High | unknown | Medium-Low |
| Amadeus Self-Service | FSC secondary sanity | Cheap Radar primary due LCC omissions | No | Yes | N/A | weaker for this product | material LCC/airline gaps | live offers + cached discovery | High | Low-Medium | pay-as-you-go/free quota model | High |
| airline sites | final existence check | broad discovery | Partial | varies | Avoid | own-channel only | own carrier only | current to cached marketing | low across many carriers | High if many adapters | varies | High for route existence |

## 9. What access is worth obtaining now

Priority order:

1. **Skyscanner partnership/API access** — only if Cheap Flight Radar can satisfy the booking/deeplink/partner use model. This unlocks the most natural broad + live two-stage architecture.
2. **Fliggy FlyAI formal API key** — highest-value China-specific experiment; run C1/C2 plus China domestic/open-jaw variants before any China scraper work.
3. **Duffel developer access** — run exact deep/revalidation basket and measure Taiwan LCC/FSC availability plus search economics.
4. **Travelpayouts token** — lower priority; only to measure whether cached Data API gives meaningful exact TPE/TSA/RMQ/KHH discovery coverage.

Do not prioritize Amadeus, Naver scraping, Google Flights scraping, or Qunar scraping at this stage.

## 10. Scraper decisions

### Recommended now

None.

### Fallback-only candidates

- a narrow Trip.com or skyticket public-page parser **only** if credentialed API benchmarking proves a persistent coverage hole that materially changes deal discovery;
- any such parser must document robots/terms, rate limiting, DOM failure behavior and graceful disable path before promotion.

### Avoid

- Google Flights production scraper;
- Skyscanner scraper when API partnership is the intended path;
- Naver Flights scraper;
- Qunar scraper before FlyAI has been measured;
- broad Trip.com scraper merely because pages are readable.

## 11. Issue impact

### Issue #2 — data-source spike

Needs adjustment, not closure yet. The public-evidence phase is complete enough to narrow the stack, but the exact-basket price hit/gap metrics remain blocked on provider access. Issue #2 should become the credentialed validation gate for Skyscanner Live/Indicative, FlyAI and Duffel, with Travelpayouts cached coverage as optional.

### Issue #3 — collector layer

Needs adjustment. Add an explicit **source router** before provider adapters. The normalized interface must carry requested airport vs returned segment airport, stage, cache/live semantics, fare family/baggage and provider-health/coverage state.

Implementation should not begin with a single universal adapter. First production adapter depends on credentialed benchmark outcome; likely Skyscanner for global discovery or FlyAI for China specialist.

### Issue #4 — normalized schema/history

Small adjustment. Add `search_stage`, `requested_origin`, `requested_destination`, `returned_segment_airports`, provider freshness/cache metadata, fare-family/baggage normalization state, and final-cross-check state. This is necessary to diagnose airport substitution and stale discovery prices.

### Issue #5 — daily runner

Needs adjustment. Preserve shared broad discovery where appropriate, but route **market/stage** through the source router. Japan/Korea/China deep expansion must be allowed to use different providers, and China should not be forced through the World provider stack.

## 12. Next atomic package

Do not implement a production collector before the access-dependent basket is measured.

Next package:

1. obtain available Skyscanner, FlyAI and Duffel credentials/access status;
2. execute J1-J5, K1-K2, C1-C2, S1, L1 under the same timestamped normalization rules;
3. calculate exact-date coverage, LCC miss rate, lowest-verifiable hit rate, price gap, stale-result rate and revalidation success;
4. select the first production adapter;
5. continue directly through adapter + deterministic fixtures/tests + Gate + PR + exact-head CI if the evidence is decisive and CWU allows.
