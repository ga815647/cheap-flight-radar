# Free public Web/social airfare intelligence research — 2026-08-11

Status: evidence-backed registry checkpoint for Issue #10. This document explains the `public_intelligence` policy now recorded in `flight-radar.yaml`; it does **not** define a final crawler/selector matrix.

Observation window: 2026-08-11, Asia/Taipei.

## 1. Research question

The daily radar needs a small set of public sources that are intentionally monitored and therefore count toward run coverage, while still allowing broad open-Web/social intelligence without pretending that opportunistic search is complete.

The roles are deliberately separate:

- `fixed_watch`: required on its declared cadence; an unavailable/blocked/fetch/parse failure is a coverage failure for that source.
- `opportunistic`: Google/Web, public indexed social posts, forums, news, and other public pages. Any useful signal can seed a candidate, but failure to query a particular source is not a coverage failure.
- `verification_only`: airline/OTA/metasearch exact-itinerary surfaces used only after a serious candidate exists.

A fixed-watch source proves only that **that source was attempted**, not that a market, airline set, airport, or fare universe is exhaustive.

## 2. Method and scoring

Candidates were evaluated on live public evidence plus unattended GitHub Actions probes. No CAPTCHA bypass, login circumvention, cookie harvesting, residential proxying, fingerprint spoofing, or other anti-bot evasion was used. The earlier FlyAI/SearchAPI fixed-basket work was not repeated.

Qualitative 0–5 dimensions:

- `signal_yield`: frequency and usefulness of genuinely cheap-fare/promotion signals;
- `freshness`: observed update cadence and recency;
- `taiwan_relevance`: Taiwan-origin usefulness, with exact TPE/TSA/RMQ/KHH evidence retained rather than a generic `Taipei` label;
- `detail`: route/date/price/tax/baggage/fare detail available in the discovery item;
- `public_access`: access without account or login bypass;
- `actions_feasibility`: observed GitHub-hosted-runner HTTP/headless usability;
- `parser_stability`: structural/static-page stability inferred from the accessible surface;
- `anti_bot_risk`: 0 is low risk; 5 is high risk;
- `duplicate_risk`: 0 is mostly unique; 5 is commonly repeated elsewhere.

A source is not promoted to `fixed_watch` merely because its content is valuable. The unattended acquisition path must also be sufficiently stable, and it must add incremental value after dedupe.

## 3. GitHub Actions feasibility evidence

Two temporary research workflows were run on the branch and then removed. The workflow runs remain durable GitHub evidence.

### 3.1 Direct HTTP probe

Run: `31469129828` on GitHub-hosted Ubuntu 24.04.

Observed results:

| Source endpoint | Result | Interpretation |
|---|---:|---|
| China Airlines home | HTTP 200, ~1.07 MB | direct HTTP viable; login text was normal page navigation, not a wall |
| Tigerair Taiwan home | HTTP 200, ~7.7 KB | direct HTTP viable |
| PTT Japan_Travel board | HTTP 200, ~23.7 KB | direct static HTML viable |
| CheapFlyTW | HTTP 200, ~120.7 KB, ~8.8 s | viable but relatively slow |
| Jeju Air events | HTTP 403 | not direct-HTTP fixed-watch material in this probe |
| T'way events | HTTP 403 | not direct-HTTP fixed-watch material in this probe |
| EVA Air news | HTTP 403 | not direct-HTTP fixed-watch material in this probe |
| Peach home | curl rc 92 / HTTP/2 stream error | transport failure, not CAPTCHA evidence; required browser follow-up |
| Secret Flying Taiwan | HTTP 403 + challenge marker | high anti-bot risk; do not promote |
| Fly4free Taiwan | HTTP 403 + challenge marker | high anti-bot risk; do not promote |
| TaiwanAirTkt Facebook page | HTTP 200 but challenge + login markers | public/indexable content does not equal a stable unattended page collector |

### 3.2 Stock Chrome headless probe

Run: `31469243375` on a GitHub-hosted Ubuntu 24.04 runner using stock `google-chrome --headless=new --dump-dom` only.

Observed results:

| Source | Headless result | Decision impact |
|---|---|---|
| Peach | rc 0, ~185 KB, content marker present, no challenge/login marker | technically automatable with headless, but incremental value/redirect stability still does not justify required fixed-watch status yet |
| Jeju Air events | rc 0 but only ~3 KB, expected content marker absent, login text present | not promoted |
| T'way events | rc 0 but only ~317 B, expected content marker absent | not promoted |
| EVA Air news | rc 0 but only ~318 B, expected content marker absent | not promoted |
| TaiwanAirTkt Facebook | rc 0, page marker present, but challenge + login markers present | opportunistic public-indexed intelligence only; no scraping workaround |

Important: a browser process returning exit code 0 is not treated as successful source coverage if expected public content is absent.

## 4. Evidence-backed source scorecard

Scores are qualitative and role-specific; they are not a universal ranking of websites.

| Source | Signal | Fresh | TW relevance | Detail | Public | Actions | Parser | Anti-bot | Duplicate | Role |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Tigerair Taiwan official | 4 | 5 | 5 | 4 | 5 | 5 | 4 | 1 | 3 | **fixed_watch** |
| China Airlines official | 4 | 5 | 5 | 4 | 5 | 5 | 4 | 1 | 4 | **fixed_watch** |
| PTT Japan_Travel `[資訊]` | 5 | 4 | 5 | 5 | 5 | 5 | 5 | 1 | 4 | **fixed_watch (Japan)** |
| TaiwanAirTkt public Facebook/editor posts | 5 | 5 | 5 | 5 | 3 | 1 | 1 | 5 | 5 | opportunistic |
| T'way official events | 4 | 5 | 5 | 4 | 5 in normal Web | 1 | 3 | 3 | 3 | opportunistic pending stable acquisition |
| Jeju Air official events | 4 | 5 | 4 | 4 | 5 in normal Web | 1 | 3 | 3 | 3 | opportunistic pending stable acquisition |
| Peach official promotions | 4 | 4 | 4 | 5 | 5 | 4 headless | 2 | 2 | 4 | opportunistic; fixed-watch candidate only if incremental yield is measured |
| EVA Air official promotions/news | 3 | 4 | 5 | 4 | 5 in normal Web | 1 | 3 | 3 | 4 | opportunistic |
| CheapFlyTW | 2 | 2 | 3 | 4 | 5 | 4 | 4 | 1 | 4 | opportunistic, low frequency |
| Secret Flying Taiwan | 1 for current Taiwan-outbound | 2 | 2 | 4 | 4 normal Web | 1 | 3 | 5 | 3 | opportunistic, low priority |
| Fly4free Taiwan | 2 for Taiwan-outbound | 3 | 2 | 4 | 4 normal Web | 1 | 3 | 5 | 3 | opportunistic, low priority |
| Airline/OTA/metasearch exact-fare pages | n/a discovery | high when queried | exact candidate | potentially 5 | varies | varies | varies | varies | n/a | **verification_only** |

### Why the three fixed watches are enough for v0

The registry intentionally stays small:

1. **Tigerair Taiwan official** gives a high-frequency Taiwan LCC first-party signal and has a clean direct-HTTP path.
2. **China Airlines official** gives a stable FSC first-party signal across Japan/Korea/China/World and visibly publishes time-limited offers and exact Taiwan-origin route fare cards.
3. **PTT Japan_Travel `[資訊]`** is a static, automation-friendly multi-carrier Japan specialist source. Recent 2026 posts captured Taiwan-origin Scoot and Jetstar promotions with exact fare semantics, date windows and explicit discrepancies between advertisement and current booking-system prices.

Adding every airline or editor would increase failure surface and duplication without proving proportional discovery gain. In particular, T'way/Jeju/EVA were not promoted after datacenter HTTP/headless probes failed to expose their normal public content, Facebook was not promoted despite excellent signal quality because challenge/login markers remain present, and Peach was not promoted merely because stock headless worked: Japan_Travel already captures many Peach/Jetstar/Scoot/Tigerair sale signals and the incremental fixed-watch yield has not yet been measured.

## 5. Market × source-role strategy

### Japan

**Fixed watch**

- PTT Japan_Travel `[資訊]` airfare/sale posts — 3-hour cadence.
- Tigerair Taiwan official — 3-hour cadence.
- China Airlines official — 6-hour cadence.

**Opportunistic**

- public Google/Web discovery;
- Taiwan airfare editors/public Facebook posts when indexable without bypass;
- Peach, Jetstar, Scoot, AirAsia and other airline promotion pages discovered through the open Web;
- other public travel forums/news.

**Verification only**

- exact airline booking/fare page;
- exact OTA/metasearch itinerary page when useful.

### Korea

**Fixed watch**

- Tigerair Taiwan official — 3-hour cadence.
- China Airlines official — 6-hour cadence.

This is intentionally narrow and does **not** claim exhaustive Korea LCC coverage.

**Opportunistic**

- T'way and Jeju Air official events through ordinary public Web discovery while the unattended paths remain unstable;
- public social editors, Google/Web, news/forums;
- other Korea-airline promotion pages.

**Verification only**

- airline/OTA exact itinerary surface; Naver/other comparison surfaces remain candidate-triggered benchmark evidence rather than fixed coverage.

### China

**Fixed watch**

- China Airlines official — 6-hour cadence for first-party Taiwan-origin China promotions when published.

No China-local public promo site was promoted merely to make the registry look symmetric. Fixed public intelligence coverage is intentionally narrow; separate provider routing already handles China deep search and must retain its own coverage semantics.

**Opportunistic**

- public social/editor signals;
- China Eastern/Air China/Xiamen/other airline public announcements when discoverable;
- Web/news/forums.

**Verification only**

- exact carrier/OTA fare pages. A promotional announcement is not revalidation.

### World / other international

**Fixed watch**

- China Airlines official — 6-hour cadence.
- Tigerair Taiwan official — 3-hour cadence for its own international network.

**Opportunistic**

- public editors/social posts and open-Web search;
- T'way connecting-network promotions;
- airline news/promotion pages not in the registry;
- CheapFlyTW as a low-frequency secondary signal;
- Secret Flying/Fly4free only as low-priority signals because current Taiwan-outbound yield is weak and the Actions probe encountered challenge pages.

**Verification only**

- exact airline, OTA, or metasearch candidate surface.

## 6. Taiwan airport integrity

A source's presence in the registry never authorizes airport inference.

- Exact TPE/TSA/RMQ/KHH must be retained when explicit.
- `Taipei` or `台北` is not sufficient to assert TPE or TSA.
- If a promotion covers only TPE/KHH, it cannot be credited as RMQ/TSA coverage.
- Fixed-watch coverage is recorded per source attempt independently of airport availability in the source's current items.

Current source evidence differs materially by airport. For example, China Airlines' current public offers include specific KHH and RMQ Japan deals, T'way's Taiwan-connection promotion exposes KHH/RMQ connections through ICN, while many editor/forum examples are TPE/KHH-heavy. This is a reason to retain exact airport metadata, not a reason to infer missing airport coverage.

## 7. Provenance and dedupe model

The system must distinguish a **deal/candidate** from a **sighting**.

### 7.1 Discovery provenance

For every normalized candidate retain:

- immutable `first_seen_at`;
- immutable `first_discovery_source_id`;
- append-only `discovery_sources[]`, each with source id, source URL/post identity, `observed_at`, claimed price/currency, and claim scope when available;
- separate `deep_search_sources[]`;
- separate `revalidation_sources[]`;
- separate `final_cross_check_sources[]`;
- `last_seen_at` derived from observations, never by overwriting first-seen evidence.

A popular fare being posted by five editors is one candidate with five discovery sightings, not five deals.

### 7.2 Two identity levels

**Campaign identity** is used before an exact itinerary exists:

`carrier + sale period + travel period + normalized route set + promo code when known`

**Exact itinerary identity** is used after itinerary construction/deep search:

`trip type + exact origin airport + exact destination airport when known + outbound date/window + return date/window + flight identity when known`

Neither identity includes the discovery source. The exact itinerary identity also deliberately excludes price: a TWD 5,999 sighting and a TWD 6,099 re-observation of the same itinerary are separate fare observations attached to the same candidate, not separate trips.

Baggage/tax/fare-family differences remain on fare observations and must be considered before comparing prices as equivalent.

### 7.3 Coverage is not dedupe

Coverage accounting is a separate run-level structure:

- every required fixed source records success/unavailable/blocked/fetch_failed/parse_failed;
- opportunistic success cannot replace a failed fixed source;
- duplicate discovery sightings can raise confidence/provenance richness but never repair missing fixed-watch coverage.

## 8. Verification boundary

Official airline promotion pages can be excellent discovery signals but they are not automatically final fare truth. A candidate becomes revalidated only after a candidate-triggered live/exact fare attempt can establish the requested airport/date/flight/price scope. Missing tax, baggage, fare-family or bookability information remains unknown.

Dynamic airline route-fare cards, airline booking/search pages, OTA exact-itinerary pages and metasearch exact-itinerary pages therefore stay `verification_only` even when they are publicly readable.

## 9. Crawler implications

This checkpoint deliberately does **not** write a DOM-selector matrix.

Implementation may now safely standardize:

- registry parsing from SSOT;
- fixed-watch attempt/coverage manifest semantics;
- generic normalized public-intelligence observation/provenance structures;
- dedupe keys and append-only sightings;
- deterministic fixtures for the three selected source classes.

Before a real live collector is promoted for any fixed source, add a source-specific fixture and demonstrate that failure/blocked/parse-failed states are visible. If a later source requires headless, it must first show repeatable expected-content retrieval on GitHub-hosted runners; a zero browser exit code alone is not enough.

## 10. Evidence URLs sampled

Representative evidence inspected during this research included:

- China Airlines home/offers: `https://www.china-airlines.com/tw/zh/index.html`
- China Airlines limited-time sale: `https://flights.china-airlines.com/zh-tw/limited-time_seats_sale`
- Tigerair Taiwan: `https://www.tigerairtw.com/zh-TW/`
- PTT Japan_Travel: `https://www.ptt.cc/bbs/Japan_Travel/index.html`
- T'way events: `https://www.twayair.com/app/promotion/event/being`
- T'way Taiwan connecting promotion: public event page titled `台灣出發，連接全球`
- Jeju Air events: `https://www.jejuair.net/zh-tw/event/pastEvent.do`
- Peach: `https://www.flypeach.com/`
- EVA Air news: `https://www.evaair.com/zh-tw/about-eva-air/news/`
- CheapFlyTW: `https://cheapfly.gocarry.tw/`
- Secret Flying Taiwan: `https://www.secretflying.com/cheap-flights-from/taiwan/`
- Fly4free Taiwan: `https://www.fly4free.com/flight-deals/taiwan/`
- TaiwanAirTkt public Facebook page: `https://www.facebook.com/TaiwanAirTkt/`

## 11. Durable checkpoint / next implementation package

Issue #10 research is sufficient to standardize the role model and v0 minimal fixed registry. The next package should implement policy plumbing rather than expand the source list:

1. add machine-readable registry loader/validation;
2. define fixed-watch attempt/run-manifest and normalized discovery-sighting models;
3. implement campaign/exact-itinerary dedupe with append-only provenance fixtures/tests;
4. add deterministic collectors/fixtures starting with direct-HTTP sources only;
5. run Gate and exact-head CI;
6. only then decide whether Peach adds enough unique Japan yield to justify a headless fixed-watch collector.

Do not promote T'way, Jeju Air, EVA, Facebook, Secret Flying or Fly4free by adding anti-bot workarounds. If their ordinary public acquisition becomes stable later, re-measure incremental signal yield and reconsider the registry.