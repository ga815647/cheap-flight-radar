# CFR Phase 1 substrate reassessment — 2026-08-21

Status: Phase-1 durable research conclusion for issue #56 under the Travel Stack Substrate Reassessment program.

This document is research/architecture evidence. It does not itself change runtime provider routing. Product Intent changes are handled separately from implementation changes.

## 1. Preserved product value

Cheap Flight Radar (CFR) should preserve the differentiated parts of the product and borrow commodity airfare-search capability whenever a mature substrate can provide it reliably.

Preserved product value:

- **Daily Radar** — without requiring manual search, autonomously discover and organize unusually cheap airfare from Taiwan, roughly daily.
- **Query / Scoped Mode** — given one or more supplied availability windows, autonomously find where airfare is cheap.
- Formal Deal truth remains **anomaly-first**: relative discount versus normal/typical price is the primary Deal concept.
- Exact **absolute-low non-Deal** airfare is separately useful, especially to FTR.
- Open-jaw is first-class; CFR may delegate multi-city/open-jaw search to mature substrates.
- One adult, economy remains the normalized discovery probe.
- Recurring production remains TWD 0 unless the owner explicitly approves a paid dependency.

## 2. Evidence base and measurements

Fresh authority was resolved from current main before the reassessment. Phase 1 began from `09fb37c7ccb9baec1ae40a24eb54c29b40a44a66`.

Accepted prior durable evidence:

- `docs/substrate-bakeoff-2026-08-13.md`
- `docs/provider-source-research-2026-08-10.md`
- `docs/search-strategy.md`
- `docs/production-sticky-429-circuit-2026-08-19.md`
- `docs/ftr-scoped-search.md`
- `docs/ftr-handoff.md`
- issue #51 as prior context only, not this reassessment contract

The clean GitHub-hosted Ubuntu bakeoff on 2026-08-13 established that the current Google/gflights path could provide commodity capabilities CFR otherwise would have had to build:

- exact TPE→NRT round trip: 21 results with LCC/FSC examples;
- Explore: TPE 88, TSA 88, RMQ 109, KHH 88 destination records;
- Flight Deals: 30 records per TPE/TSA/RMQ/KHH probe;
- TPE→NRT flexible-date search: 84 date pairs;
- TPE→NRT + KIX→KHH open-jaw/multi-city: 10 results;
- current TWD fares plus representative typical-price/discount evidence.

Reliability is not assumed from that success. The explicit 2026-08-19 operator run recorded a sticky Google/gflights 429 state: only one of twelve Flight Deals calls returned records; TSA/RMQ/KHH discovery failed; exact/flexible completion did not converge; CFR correctly degraded/fail-closed instead of resetting identity, rotating sessions/proxies or hiding missing coverage.

Current official/public documentation and surfaces were rechecked on 2026-08-21 for Google Flights / Flight Deals, Trip.com, Skyscanner, Kiwi.com, Expedia, airline/member surfaces, and selected qualified API classes.

Representative sources:

- Google Flights / Flight Deals:
  - https://www.google.com/travel/flights
  - https://support.google.com/travel/answer/16497283
  - https://support.google.com/travel/answer/2475306
- Trip.com:
  - https://www.trip.com/flights/
  - https://developers.trip.com/
- Skyscanner:
  - https://help.skyscanner.net/hc/en-gb/articles/201151912-How-do-I-search-for-flights-to-Everywhere
  - https://developers.skyscanner.net/docs/flights-live-prices/overview
  - https://developers.skyscanner.net/docs/getting-started/authentication
- Kiwi.com:
  - https://www.kiwi.com/
  - https://www.kiwi.com/en/pages/content/tequila-api-deprecation/
  - https://www.kiwi.com/en/pages/content/mcp/
- Expedia:
  - https://www.expedia.com/Flights
  - https://www.expedia.com/product/flight-deals/
  - https://developers.expediagroup.com/docs/products/rapid
- Duffel:
  - https://duffel.com/docs/api/v2/offer-requests
  - https://duffel.com/pricing

Search-engine snippets, cached/indexed fares, and unverified app/member hints are never exact Deal truth.

## 3. Required fare/access semantics

The target architecture must keep these concepts separate:

1. **`fare_exists`** — a fare may exist somewhere in the market or a restricted channel.
2. **`surface_shows_fare`** — a named surface displays a fare/hint; it may still be cached, indicative, restricted or stale.
3. **`radar_can_observe_fare`** — CFR's authorized automatic execution plane can obtain the observation without hidden human work or bypass/evasion.
4. **`radar_can_reproduce_exact_fare`** — CFR can re-run/follow the exact dates/itinerary to a current complete fare with trusted seller/provenance.
5. **`formal_deal_truth`** — the exact/reproducible fare also satisfies CFR's anomaly-first Deal rules.

`Radar cannot access a fare` never implies `the fare does not exist`.

Suggested later machine coverage classes:

- `public_automatable`
- `public_agent_observable_seed_only`
- `restricted_login_member_or_app`
- `credential_or_partner_gated`
- `not_observed_or_unknown`

Coverage reports describe what CFR attempted/could observe, not exhaustive market existence.

## 4. Capability matrix

| Substrate / access path | Destination-free | Scoped/window | Anomaly/typical | Absolute-low | Flexible | Open-jaw / multi-city | TW/LCC | Global | Exact/fresh | Access/automation | Sustainable TWD-0 | Blind spots / constraints | Phase-1 role |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Google Flight Deals semantic surface** | **strong** | partial; current feature does not support every search shape | **strong**; current official Deal logic uses typical-price history and savings | **strong**; current feature also surfaces lowest-priced non-savings matches | strong product-level flexibility | Flight Deals itself excludes multi-city; pair with Google Flights exact/multi-city | **live-proven CFR basket** | **strong** | Deal discovery needs exact/seller follow-up | official Web; current backend through unofficial client | semantic surface free; machine access not guaranteed | partner coverage not exhaustive; seller/member inventory can differ | **BORROW primary destination-free/anomaly semantics** |
| **Google Explore / Flights exact / calendar / price graph / multi-city** | **strong Explore** | strong when query shape is supported | partial price insight | **strong** | **strong** | **strong** | live-proven | **strong** | **strong after exact revalidation** | official Web; current backend via `gflights` | semantic surface free; machine access not guaranteed | Google itself states not all airlines/offers are included | **BORROW commodity discovery/completion** |
| **`gflights` current machine adapter** | strong | partial by exposed request shape | strong for Flight Deals | strong | strong | strong | live-proven | strong | live-proven but volatile | GitHub runner/local, unofficial Google client | keyless today | sticky 429; upstream/interface/ToS drift; no proxy/session/UA evasion allowed | **ADAPT replaceable adapter; reliability probation** |
| **Trip.com consumer Web/app** | **strong Anywhere** | **strong UI/date flexibility** | no uniformly qualified CFR route-normal authority | strong | **strong** | **strong** | useful LCC/FSC evidence | strong | current seller results, but deterministic unattended exact extraction not proven | public Web + app | public Web TWD 0; flight API self-service not proven | explicit member/app discounts | **VERIFY-ONLY / seed; Scoped candidate** |
| **Skyscanner Everywhere / consumer Web** | **strong** | strong consumer controls | no CFR-qualified anomaly authority | strong indicative | **strong** | **strong** | strong | strong | Everywhere/month values may be estimated from prior searches; live step needed | public Web; API only if approved | Web free | API/partnership gate; seller/member differences | **VERIFY-ONLY / seed** |
| **Skyscanner APIs** | Indicative suitable for broad discovery | strong route/date live search | no CFR anomaly authority | strong if queried | API family supports indicative/flexible patterns | Live supports multi-city | likely broad but unmeasured without key | strong | **strong live + refresh** | backend only with approved partner key | **not available as owner-independent production dependency today** | partner/API-key qualification gate | **credential/partner-gated candidate, not core** |
| **Kiwi consumer Anywhere / Nomad** | **strong** | **strong ranges** | no qualified CFR anomaly authority | strong | **strong** | **strong**, including virtual interlining/self-transfer | useful | strong | current consumer results; itinerary risk needs normalization | public Web/app | Web free | app-exclusive offers; self-transfer risk | **VERIFY-ONLY / recall + Scoped candidate** |
| **Kiwi official MCP** | current exposed contract has no proven Anywhere primitive | bounded route/date/flex search | no | route-local strong | bounded flexibility | narrower than consumer Nomad | unqualified for CFR | broad | current search + booking links | agent/custom connector | public service, but not installed in current Chat environment | human connector setup; evolving surface | **VERIFY-ONLY agent-native candidate, not Daily primary** |
| **Expedia public Flights** | no qualified public destination-free anomaly feed | ordinary route/date search | no public CFR-qualified anomaly feed | route/date search | consumer flexibility | multi-city | useful | strong | exact public search can be cross-check evidence | public Web | TWD 0 Web | member/account inventory differences | **VERIFY-ONLY ordinary fare/seller cross-check** |
| **Expedia Flight Deals app** | **strong worldwide feed from home airport** | app filters destination/date | **strong concept: at least 20% below typical predicted price** | deal feed | app filtering | not established as CFR open-jaw substrate | potentially useful | strong | real consumer Deal feed | **app-exclusive according to Expedia official product page** | app use itself may be free, but no authorized unattended CFR path proven | **app-only restricted surface** | **ACCESS BLIND SPOT / benchmark, not public Web fallback** |
| **airline official public booking surfaces** | no cross-carrier discovery | own-route exact | promo context only | route-local | carrier-dependent | carrier-dependent | **best own-inventory identity**, incl LCC | carrier-limited | **strong seller/existence check when public** | Web/manual/agent; selective official feed only | generally public | member/app/subscription fare classes may be lower | **VERIFY-ONLY final seller truth** |
| **airline member/app/subscription fares** | no | carrier-dependent | no general anomaly authority | may contain real lower fares | carrier-dependent | carrier-dependent | material, including Taiwan LCC programs | carrier-limited | fare may genuinely exist | **restricted** | no autonomous public guarantee | login/member/app/payment/subscription | **ACCESS BLIND SPOT, never negative evidence** |
| **`fli` / `flights==0.9.0` prior bakeoff** | no | known route/date | no | route-local | useful | supported | fixed-basket evidence | broad | prior live comparator evidence | GitHub runner if integrated | keyless historically | not integrated; packaging/maintenance uncertainty | **VERIFY-ONLY comparator/fallback candidate** |
| **Duffel Flights API** | no | **strong known route/date slices** | no | route-local | not destination-free | multiple slices | requires credentialed coverage test | broad network | **strong live offers; short expiry** | credentialed backend | **not suitable as free discovery core at high search:book ratio** | access token; excess-search fee above 1500:1 | **VERIFY-ONLY purchase-oriented exact check, not Daily core** |
| **CFR own price history** | no | n/a | useful supplemental/fallback anomaly | observed floors only | n/a | preserves observed shapes | only CFR-observed | only CFR-observed | as exact as retained evidence | deterministic backend | **yes** | cannot see unsearched/restricted space | **BUILD/KEEP provenance + fallback, not search engine** |
| **CFR public-intelligence collectors** | seed-only | seed-only | no | hint only | no | no | useful promo/editorial hints | broad if public/indexed | not exact Deal truth | Web/bounded crawler | yes if low-maintenance | private/login surfaces invisible | **SIMPLIFY to optional Signal/seed lane** |
| **custom city×date×city brute force** | potentially | yes by enumeration | no unless another baseline built | potentially | costly | combinatorial | provider-dependent | expensive | provider-dependent | custom backend | poor sustainability | still misses restricted inventory | **DO NOT BUILD now** |

## 5. Fresh-source corrections and implications

### 5.1 Google supports CFR's semantic split directly

Current official Google Flight Deals documentation distinguishes:

- savings Deals that are materially below typical price; and
- cheap flights that are among the lowest fares for matching destinations but may **not** be below typical price.

It ranks savings first by savings magnitude, then lower absolute price, and ranks non-savings results by lowest price. This independently supports CFR's existing separation between anomaly-qualified `Deal` and exact `absolute_low_non_deal` rather than merging them.

### 5.2 Google is broad but not exhaustive

Google Flights documents more than 300 airline/OTA/aggregator partners and explicitly says not all airlines or available flights are included. Worldwide substrate-native discovery therefore supports broader CFR geography, but never justifies an exhaustive-market claim.

### 5.3 Expedia Flight Deals is an access-blind-spot example, not a public fallback

Expedia's current official Flight Deals product scans millions of flights and identifies fares at least 20% below typical predicted price, with anywhere/date filtering. However, Expedia explicitly says the Flight Deals feature is **exclusive to the app**.

Therefore:

- the anomaly capability is real;
- it is useful product/substrate evidence;
- CFR does **not** currently have an authorized repeatable unattended path to treat it as backend coverage or formal Deal authority;
- it belongs in the restricted/app-only blind-spot class unless a future authorized machine interface is proven.

This supersedes any interpretation of indexed/search-visible Expedia Deal snippets as a public Web anomaly collector.

## 6. Target architecture

Use the smallest stable architecture that preserves CFR's differentiated truth.

### Layer A — CFR product/truth core: BUILD / KEEP

CFR owns:

- normalized 1-adult economy probe policy;
- exact Taiwan outbound/return gateway and destination route-shape identity;
- anomaly-first Deal qualification/ranking;
- separate exact absolute-low non-Deal selection;
- Signal isolation;
- exact/reproducible/fresh/trusted seller gates;
- attempted-coverage and access-blind-spot truth;
- immutable provenance/history/audit evidence;
- bounded Daily/Scoped orchestration and fail-closed health semantics;
- versioned CFR→FTR handoff.

### Layer B — commodity airfare search: BORROW

Borrow instead of rebuilding:

- destination-free discovery;
- normal-price/anomaly intelligence;
- worldwide broad discovery;
- flexible-date/fare-calendar search;
- exact airfare shopping;
- open-jaw/multi-city search;
- seller/deeplink handoff.

Google Flights / Flight Deals remains the best currently qualified **semantic substrate** because CFR has live evidence for destination-free, flexible, exact and multi-city/open-jaw capability plus typical-price/discount evidence.

### Layer C — replaceable machine access: ADAPT

The current `gflights` path is an **access adapter**, not the product architecture and not an official Google API.

A thin capability interface should express intent rather than brand assumptions, for example:

- `discover_destination_free(origin, policy)`
- `discover_scoped(origin, availability_window, policy)`
- `search_exact(itinerary_query)`
- `search_flexible(route_query)`
- `search_multi_city(legs)`
- `get_anomaly_context(candidate)`
- `get_booking_offers(candidate)`

Current gflights calls may sit behind this boundary with fixed project identity, no proxy, no session/UA rotation, bounded budgets and sticky-429 fail-closed handling. Replacement or an additional access adapter should not change Deal/FTR semantics.

Any newer upstream gflights release must be qualified against the pinned production client before dependency change; newer is not automatically better.

### Layer D — Web/agent lane: VERIFY-ONLY by default

Public Google/Trip/Skyscanner/Kiwi/Expedia ordinary-search/airline surfaces can legitimately supply:

- independent recall seeds;
- current capability checks;
- final seller/cross-check evidence;
- blind-spot reporting.

A Web/agent observation cannot silently satisfy canonical backend coverage or formal Deal truth. Promotion requires exact query identity, complete current price, trusted seller/provenance and repeatable authorized observation.

Kiwi's official MCP merits bounded follow-up because it is an explicit agent search interface with booking links. Today it is not a Daily replacement: the currently exposed contract is narrower than consumer Anywhere/Nomad and the current Chat environment has no installed Kiwi connector.

## 7. Daily Radar conclusion

Target Daily Radar:

1. Borrow destination-free Flight Deals/Explore-style discovery per configured Taiwan origin rather than enumerate destination matrices.
2. Use qualified route-relative anomaly as formal Deal authority.
3. Retain exact low-price non-Deals separately.
4. Revalidate competitive candidates on exact route/date/current fare.
5. Delegate flexible-date and multi-city/open-jaw search to mature substrate primitives.
6. Expand geography through substrate-native worldwide results; JP/KR/CN remain priority slices, not hard boundaries.
7. Fail closed when automatic access collapses. Web/app evidence may expose Signals or blind spots but cannot fabricate successful canonical coverage.

No custom global fare engine or city×date×city matrix passes the BUILD gate.

## 8. Query / Scoped Mode conclusion

The smallest stable product interface remains:

`availability_windows -> cheap airfare opportunities`

with `Deal` and `absolute_low_non_deal` retained separately.

Current RP-03 is a useful **ADAPT interim** because it:

- sends provider calls inside supplied windows rather than canonical-horizon post-filtering;
- records deterministic per-window coverage;
- fails closed when a window was not actually attempted;
- reuses CFR exact revalidation/truth classes.

It is not the final ideal substrate architecture. The current adapter cannot truthfully claim arbitrary-window coverage from every Explore/flexible/open-jaw surface.

Target:

- retain the bounded planner until a better borrowed primitive qualifies;
- expose a provider-capability `discover_scoped()` contract;
- run a focused qualification of native destination-free supplied-window behavior across current Google, Trip.com, Skyscanner, Kiwi and ordinary Expedia access paths;
- prefer BORROW if an option is repeatable, authorized and TWD 0;
- do not build a destination/date matrix unless qualified external substrates are proven insufficient.

Scoped open-jaw should be delegated completion of selected endpoints where supported, not a combinatorial search mandate.

## 9. Access blind spots

Known restricted classes include:

- Expedia Flight Deals: official **app-exclusive** anomaly feed;
- Trip.com member/app discounts;
- Kiwi app-exclusive offers/features;
- airline member/subscription/app inventory, including Taiwan-LCC programs.

Truth rules:

- formal Deals require observable/reproducible evidence under CFR's trust contract;
- exact absolute-low candidates require the same current/exact discipline, minus anomaly qualification;
- known restricted classes may be recorded as `restricted_known` blind spots;
- CFR never invents the inaccessible fare price;
- CFR never describes the best public observed fare as `the cheapest fare that exists` unless such a stronger claim is actually supportable;
- restricted hints may be Signals, never formal Deals or exact absolute-low candidates without authorized exact evidence.

## 10. Keep / retire / simplify

### KEEP

- anomaly-first Deal semantics;
- exact/revalidated complete-airfare gate;
- separate bounded absolute-low non-Deal producer;
- open-jaw/different Taiwan gateway route-shape semantics;
- immutable Git-backed price/run/provenance evidence;
- provider health and slice-faithful attempted coverage;
- sticky-429 fail-closed semantics;
- canonical/scoped/recovery identity isolation;
- CFR→FTR schema/checksum/freshness/repair contract.

### KEEP BUT DEMOTE / ADAPT

- `gflights`: current machine adapter, not sacred architecture or sole durable substrate;
- own price history: provenance/rolling lows/supplemental fallback, not primary normal-price engine;
- source router: thin capability router, not a reason to maintain separate custom fare engines;
- public Web intelligence: typed Signal/seed/cross-check only.

### SIMPLIFY

- JP/KR/CN remain priority slices but need not have separate search algorithms;
- fixed-watch crawler program should retain only low-maintenance/high-signal public sources;
- absolute-low display remains separate from anomaly ranking;
- open-jaw construction should use substrate multi-city when available.

### RETIRE / DO NOT REVIVE

- mandatory outbound-one-way-first architecture;
- unbounded city×date×city brute force;
- `trvl` as production core;
- claims of fallback providers that are not actually invokable;
- CAPTCHA bypass, stealth fingerprinting, proxy rotation, residential proxy, rotating identity/session evasion;
- permanent Asia/Oceania product ceiling;
- assumption that inaccessible app/member fares do not exist.

### VERIFY-ONLY / CANDIDATES

- Trip.com / Skyscanner / Kiwi consumer surfaces for recall/scoped/final cross-check;
- Kiwi MCP as agent-native bounded search candidate;
- `fli` as exact/flexible comparator;
- airline public seller pages as final existence verification;
- Expedia public ordinary Flights as cross-check only; **Expedia Flight Deals app is a restricted benchmark/blind spot, not a current public fallback**;
- Skyscanner Live only if approved access becomes available without violating owner cost policy.

## 11. Sustainable cost conclusion

Recurring TWD 0 remains achievable only if production relies on qualified public/free borrowed surfaces plus already-allowed disposable compute.

Do not adopt as unattended Daily core without owner approval:

- Skyscanner API: partnership/API-key approval gate;
- Kiwi Tequila/new B2B access: invitation/partnership gate;
- Expedia partner flight connectivity: not a demonstrated self-service free CFR dependency;
- Duffel: credentialed and structurally exposes excess-search fees above a 1500:1 search-to-book ratio;
- paid search wrappers, proxies or scraping APIs.

## 12. CFR → FTR implications

The existing handoff architecture is largely correct and survives the reassessment:

- FTR consumes exact airfare opportunities, not CFR's search implementation;
- formal `deal` and exact `absolute_low_non_deal` remain separate candidate kinds;
- generic Signals never silently enter the exact low-price set;
- exact dates, Taiwan gateways, destination route shape, complete fare, observation time and provenance remain required;
- provider/surface/origin/market coverage is execution truth, never candidate count.

Future-compatible additions should remain small:

1. geographic attempted coverage must not assume Asia/Oceania exhaustiveness;
2. typed access-blind-spot metadata may tell FTR that restricted/unobservable fare classes exist without inventing prices;
3. provider identity stays abstract enough that replacing gflights or adding a qualified agent lane does not alter consumer semantics;
4. Scoped snapshots retain per-window attempted/not-attempted truth with any new adapter.

No FTR Phase 2 work is authorized by this document.

## 13. BORROW / ADAPT / VERIFY-ONLY / BUILD

### BORROW

- destination-free discovery
- worldwide broad discovery
- typical-price/anomaly context
- flexible-date/fare-calendar search
- exact airfare shopping
- open-jaw/multi-city search
- seller/deeplink handoff

### ADAPT

- thin capability router and normalized adapters
- current gflights adapter under strict no-evasion and health accounting
- current bounded Scoped planner until a native arbitrary-window substrate qualifies
- source-specific normalization into CFR evidence types

### VERIFY-ONLY

- public OTA/metasearch/airline Web surfaces
- Trip.com / Skyscanner / Kiwi recall and scoped research
- Kiwi MCP pending connector/capability qualification
- Expedia public ordinary Flights; Expedia app-only Flight Deals as restricted benchmark
- `fli` comparator
- airline seller surfaces

### BUILD

Only CFR-specific product truth/orchestration:

- anomaly Deal semantics
- absolute-low non-Deal semantics
- trust/freshness/reproducibility gates
- access/coverage truth
- durable evidence/history
- FTR handoff
- bounded fail-closed orchestration

A custom airfare search engine or brute-force fare floor does **not** pass BUILD today.

## 14. Product Intent change separated from implementation

The accepted Phase-1 Product Intent delta is:

1. Daily Radar and Query/Scoped are explicit first-class CFR modes.
2. Asia/Oceania is no longer a permanent product ceiling; worldwide substrate-native discovery is desired when qualified/sustainable, with JP/KR/CN still priority.
3. Broader substrate capability does not imply exhaustive global coverage.
4. Access blind spots are explicit: restricted/member/app/login fares may exist even when CFR cannot observe or reproduce them.
5. Search implementation is not sacred; mature external commodity capability is preferred.
6. Anomaly-first Deal, separate exact absolute-low, open-jaw, 1-adult economy normalization, exact/reproducible trust and TWD-0 default remain unchanged.

Runtime / `flight-radar.yaml` changes are separate follow-up implementation packages.

## 15. Issue #51 disposition

Issue #51 is **superseded by #56 / this Phase-1 conclusion** and should close rather than remain the architecture contract.

Its surviving work maps as follows:

- SR-01 source census: absorbed/superseded by Phase-1 evidence.
- SR-02 custom brute-force producer: rejected for now under BUILD-vs-BORROW; reconsider only if focused borrowed-substrate qualification fails.
- SR-03 curated intelligence: retain only as simplified optional Signal/seed work.
- SR-04 executable redundancy: retain only as a narrow future access-adapter qualification/integration package.

## 16. Remaining blockers

### Technical / researchable

- qualify current upstream gflights versus the pinned client under CFR fixed-UA/no-proxy/no-evasion rules;
- focused Scoped native-window bakeoff across qualified public/agent surfaces;
- qualify whether any agent-native path can provide repeatable exact evidence that legitimately counts as an execution lane;
- identify a genuinely public/repeatable second anomaly source, if one exists; Expedia app-only Flight Deals does not satisfy that today.

### Inaccessible substrate

- app-only/member-only/login-only fare classes without authorized automated observation.

### Credential / human-action gates

- Skyscanner partnership/key;
- Kiwi custom MCP/connector setup if later chosen for direct qualification;
- airline/OTA member login where restricted inventory is intentionally being investigated.

None is required for Phase-1 acceptance.

### Paid-resource gates

- Duffel at radar-scale search ratios;
- paid search wrappers/proxies/APIs;
- any production API without a proven sustainable free quota.

### Genuine unresolved product-intent decision

None after the 2026-08-21 owner clarifications.

## 17. Recommended atomic follow-ups

1. **CFR-SR-A — machine scope / capability-router convergence**
   - align machine SSOT with worldwide substrate-native intent and truthful attempted coverage; no global brute force.
2. **CFR-SR-B — gflights current-release + access-reliability qualification**
   - fixed basket, fixed UA, no proxy/evasion; dependency change only if evidence supports it.
3. **CFR-SR-C — Scoped native-window BORROW bakeoff**
   - compare external supplied-window primitives before custom implementation.
4. **CFR-SR-D — executable access redundancy qualification**
   - seek a real authorized TWD-0 second execution path; do not count app-only Expedia Flight Deals as one.
5. **CFR-SR-E — access-blind-spot evidence schema**
   - add typed restricted/unobservable coverage metadata without fabricating fares.
6. **CFR-SR-F — public-intelligence simplification**
   - retire low-value crawler/fixed-watch complexity that does not improve Deal truth or recall enough to justify maintenance.

Implementation must not be bundled into this research conclusion.
