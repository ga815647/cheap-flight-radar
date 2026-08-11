# Free public Web/social airfare intelligence research — 2026-08-11

Status: evidence-backed **v1** registry checkpoint for Issue #10. `flight-radar.yaml` is the machine SSOT; this document records the research rationale and live acquisition evidence.

Observation window: 2026-08-11, Asia/Taipei.

## 1. Role model

- `fixed_watch`: deterministic public discovery source required when its latest successful attempt is older than its declared `cadence_hours`; a due source that is unavailable/blocked/fetch-failed/parse-failed reduces fixed-watch coverage.
- `opportunistic`: ChatGPT/open-Web/public-social/news/forum discovery. Useful sightings are retained, but inability to query a particular opportunistic source does not make fixed coverage incomplete.
- `verification_only`: airline/OTA/metasearch exact-itinerary surfaces used after a serious candidate exists.

A fixed-watch success proves only that the declared source contract was successfully read. It does not claim exhaustive airline, market, airport, or fare coverage.

## 2. Scheduler and cadence correction

Cheap Flight Radar is orchestrated by a **ChatGPT scheduled radar run**. GitHub Actions is an on-demand deterministic execution/crawler/Gate backend, not the primary scheduler.

`cadence_hours` means the maximum reusable age of the latest **successful** fixed-watch attempt:

- no successful prior attempt: due now;
- successful attempt younger than cadence: ChatGPT may reference that attempt id instead of rerunning it;
- successful attempt at/older than cadence: due now;
- failed attempts never refresh freshness.

There is no independent Actions cron in v1.

## 3. Acquisition research and safety boundary

Candidates were evaluated with ordinary public HTTP, stock browser rendering, and public Web search. No CAPTCHA bypass, stealth/fingerprint spoofing, proxy rotation, residential IP, login circumvention, or similar anti-bot evasion was used or permitted.

Earlier source-feasibility probes showed:

- China Airlines homepage: ordinary HTTP 200 and rich public HTML;
- PTT Japan_Travel: ordinary HTTP 200 and stable static board HTML;
- Tigerair current homepage: HTTP 200 but a very small/current app shell rather than a stable promotion DOM;
- Peach: stock headless could render expected public content, but incremental fixed-watch yield was not established;
- T'way/Jeju/EVA: datacenter HTTP/headless probes did not establish stable public content contracts;
- public Facebook editor pages: useful signals exist in indexed public Web results, but challenge/login markers make them inappropriate for required unattended coverage;
- Secret Flying/Fly4free: challenge responses and low Taiwan-outbound incremental yield keep them opportunistic.

The focused crawler-runtime spike is documented separately in `docs/crawler-runtime-spike-2026-08-11.md`.

## 4. Live fixed-source integration evidence

### Run `31473460091`

A one-shot GitHub-hosted Ubuntu integration probe used the new Scrapy runner against the original three fixed candidates:

- **China Airlines**: HTTP 200 and parser success, but the first parser was overly broad. It was subsequently restricted to real event pages and route-price cards.
- **PTT Japan_Travel**: HTTP 200 and parser success; there were zero matching `[資訊]` airfare/sale posts in that snapshot. Zero observations is valid success when the board contract is intact.
- **Tigerair Taiwan**: HTTP 200 but no stable public promotion-anchor contract, therefore `parse_failed` rather than false success.

### Run `31473909367`

The corrected probe used exact source head `86d3bf3e9c3e93ae32a9a8a1cbba5d5475181f12` and vanilla `scrapy-playwright` only for Tigerair:

- **China Airlines**: HTTP 200, narrowed parser succeeded, 8 normalized observations in the live snapshot.
- **PTT Japan_Travel**: HTTP 200, parser succeeded, zero matching current airfare signals.
- **Tigerair Taiwan**: ordinary Playwright still returned HTTP 200 but did not expose a stable promotion-anchor parser contract; the attempt correctly remained `parse_failed`.

Public Web discovery at the same checkpoint could find official Tigerair news and `static.tigerairtw.com` campaign/event pages. Therefore Tigerair remains a valuable signal source, but its current homepage is not a reliable deterministic coverage contract.

## 5. v1 source scorecard

Scores are qualitative (0–5) and role-specific.

| Source | Signal | Fresh | TW relevance | Detail | Public | Deterministic Actions | Parser stability | Anti-bot risk | Role |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| China Airlines official | 4 | 5 | 5 | 4 | 5 | 5 | 4 | 1 | **fixed_watch** |
| PTT Japan_Travel `[資訊]` | 5 | 4 | 5 | 5 | 5 | 5 | 5 | 1 | **fixed_watch (Japan)** |
| Tigerair Taiwan official | 4 | 5 | 5 | 4 | 5 | 1 for current homepage contract | 1 | 1 | **opportunistic** official Web/news/static events |
| TaiwanAirTkt public/editor posts | 5 | 5 | 5 | 5 | 3 | 1 | 1 | 5 | opportunistic |
| Peach official promotions | 4 | 4 | 4 | 5 | 5 | 4 headless | 2 | 2 | opportunistic; possible future fixed candidate if unique yield is measured |
| T'way official events | 4 | 5 | 5 | 4 | 5 normal Web | 1 | 3 | 3 | opportunistic |
| Jeju Air official events | 4 | 5 | 4 | 4 | 5 normal Web | 1 | 3 | 3 | opportunistic |
| EVA Air promotions/news | 3 | 4 | 5 | 4 | 5 normal Web | 1 | 3 | 3 | opportunistic |
| CheapFlyTW | 2 | 2 | 3 | 4 | 5 | 4 | 4 | 1 | opportunistic, low frequency |
| Secret Flying / Fly4free Taiwan | 1–2 | 2–3 | 2 | 4 | 4 normal Web | 1 | 3 | 5 | opportunistic, low priority |
| Airline/OTA/metasearch exact fare pages | n/a discovery | high when queried | exact candidate | potentially 5 | varies | varies | varies | varies | **verification_only** |

The fixed registry is deliberately small. A valuable source is not fixed unless its unattended public acquisition contract is stable enough that failure means something useful about coverage.

## 6. v1 fixed-watch registry

### `china_airlines_official`

- markets: Japan, Korea, China, World;
- cadence/freshness threshold: 6 hours;
- acquisition: direct HTTP via Scrapy;
- role: first-party FSC promotion / route-price signal;
- exact Taiwan airport identity is retained when explicit; no generic `Taipei` inference.

### `ptt_japan_travel_info`

- market: Japan;
- cadence/freshness threshold: 3 hours;
- acquisition: direct HTTP via Scrapy;
- parser contract: public `.r-ent` board rows, only `[資訊]`/`［資訊］` posts with airfare/sale signal text;
- role: multi-carrier Japan specialist signal, including LCC information.

### Tigerair correction

`tigerair_tw_official` is **not** a v1 fixed watch. The fixed candidate was demoted after both direct HTTP and ordinary Playwright produced HTTP 200 without a stable promotion DOM contract on GitHub-hosted Ubuntu.

Preferred Tigerair discovery is now opportunistic public Web search over official news and official static event pages. These sightings retain official provenance but do not repair fixed-watch coverage.

## 7. Market × role strategy

### Japan

Fixed: PTT Japan_Travel (3h), China Airlines (6h).

Opportunistic: Tigerair official news/static campaigns, public airfare editors/social search, Peach/Jetstar/Scoot/AirAsia and other public airline promotion pages, open Web/news/forums.

Verification: exact airline/OTA/metasearch candidate surfaces.

### Korea

Fixed: China Airlines (6h).

Opportunistic: Tigerair official Web discovery, T'way, Jeju Air, public social/editor/Web/news sources. This intentionally does not claim exhaustive Korea LCC coverage.

Verification: exact airline/OTA/metasearch candidate surfaces.

### China

Fixed: China Airlines (6h) for first-party Taiwan-origin promotions when present.

Opportunistic: public airline announcements, social/editor/Web/news sources. China deep-search provider routing remains a separate coverage domain.

Verification: exact carrier/OTA fare surfaces.

### World / other

Fixed: China Airlines (6h).

Opportunistic: Tigerair official Web/news/static campaigns, public editors/social, airline promotion pages, CheapFlyTW, and lower-priority Secret Flying/Fly4free signals.

Verification: exact airline/OTA/metasearch candidate surfaces.

## 8. Taiwan airport integrity

- Preserve exact TPE/TSA/RMQ/KHH when explicit.
- `Taipei` or `台北` is not sufficient to infer TPE or TSA.
- Source-attempt coverage is separate from whether the current observations contain every Taiwan airport.
- A source's registry presence never authorizes missing-airport inference.

## 9. Provenance and dedupe

A deal/candidate is distinct from a sighting.

Discovery provenance keeps immutable `first_seen_at` / `first_discovery_source_id`, append-only discovery sightings, and separate deep-search/revalidation/final-cross-check source records.

Campaign identity before an exact itinerary:

`carrier + sale period + travel period + normalized route set + promo code when known`

Exact itinerary identity after construction:

`trip type + exact origin + exact destination when known + outbound date/window + return date/window + flight identity when known`

Source identity is excluded from both identities. Price is excluded from exact-itinerary identity, so reobserved prices append to the same candidate instead of creating duplicate trips.

Coverage accounting is independent of dedupe: duplicate opportunistic sightings cannot substitute for a failed due fixed watch.

## 10. Runtime implication

Current fixed watches are direct HTTP and therefore the normal Actions execution installs only Scrapy. The repo keeps a conditional vanilla `scrapy-playwright` fallback interface for a future source only after repeatable public browser retrieval plus a deterministic fixture establish a real parser contract.

The repository owns registry/due semantics, attempt/run manifests, normalized sightings, parsers/fixtures, provenance/dedupe, and coverage interpretation. Scrapy owns crawling mechanics.

## 11. Durable checkpoint

Issue #10 now has both the role model and the minimal execution plumbing:

1. ChatGPT scheduler / GitHub backend boundary is explicit in SSOT;
2. cadence is successful-attempt freshness, not cron;
3. crawler runtime reuse spike selected Scrapy;
4. fixed registry was reduced from three to two after Tigerair live contract failure;
5. registry loader/due planner, attempt/run manifest, normalized sightings, provenance/dedupe, source fixtures/parsers, and caller-driven Actions execution are implemented;
6. one-shot live probe workflow was removed after evidence collection.

The next atomic package should integrate persisted prior-attempt state / artifact retrieval into the ChatGPT-triggered radar-run interface, then connect normalized fixed-watch observations to opportunistic discovery and downstream deep-search/revalidation without creating an independent GitHub schedule.