# CFR Phase 1 substrate reassessment — 2026-08-21

Status: Phase-1 durable research conclusion for issue #56 under the Travel Stack Substrate Reassessment program.

This document is research/architecture evidence. It does not itself change runtime provider routing. Product Intent changes are handled separately from implementation changes.

## 1. Question and preserved product value

Cheap Flight Radar (CFR) should preserve the parts that are genuinely differentiated and borrow commodity airfare-search capability whenever a mature surface can provide it reliably.

Preserved product value:

- Daily Radar: without asking the user to search manually, discover and organize unusually cheap airfare from Taiwan, roughly daily.
- Query / Scoped Mode: given one or more supplied date windows, autonomously find where airfare is cheap.
- Formal Deal truth remains anomaly-first: relative discount versus a normal/typical route price is the primary Deal concept.
- Absolute-low current airfare is a separate useful axis and is an important bounded downstream input for Family Trip Radar (FTR).
- Open-jaw is first-class, but CFR does not need to manufacture combinations itself when a mature substrate can search multi-city/open-jaw directly.
- One adult, economy remains the normalized discovery probe.
- Sustainable recurring production cost remains TWD 0 unless the owner later approves a paid dependency.

## 2. Evidence base

Fresh authority was resolved from current main before this reassessment. At Phase-1 start, current main was `09fb37c7ccb9baec1ae40a24eb54c29b40a44a66`.

Durable prior CFR evidence accepted as still relevant:

- `docs/substrate-bakeoff-2026-08-13.md`
- `docs/provider-source-research-2026-08-10.md`
- `docs/search-strategy.md`
- `docs/production-sticky-429-circuit-2026-08-19.md`
- `docs/ftr-scoped-search.md`
- `docs/ftr-handoff.md`
- issue #51 as prior source-expansion context, not as the new Phase-1 contract

Key prior live measurements on clean GitHub-hosted Ubuntu from 2026-08-13 remain useful:

- `gflights==0.3.0` exact TPE→NRT round trip: 21 results, including Taiwan/Japan LCC and FSC examples.
- Google Explore through the same client: TPE 88, TSA 88, RMQ 109, KHH 88 destination records.
- Google Flight Deals: 30 records for each TPE/TSA/RMQ/KHH probe.
- TPE→NRT three-month cheapest-date query: 84 date pairs.
- multi-city/open-jaw TPE→NRT + KIX→KHH: 10 results.
- the same path returned current TWD fare, exact Taiwan origin/destination identity and representative Flight Deals typical-price/discount evidence.

The reliability counter-evidence is also material. The explicit 2026-08-19 operator acquisition recorded a sticky Google/gflights 429 state: only one of twelve Flight Deals calls returned records, TSA/RMQ/KHH discovery failed, exact/flexible completion did not converge, and the run became degraded. CFR correctly fails closed after the first sticky-client failure rather than resetting the client, rotating identity, or hiding missing coverage.

Current official/public product documentation and surfaces were rechecked on 2026-08-21, including Google Flights / Flight Deals, Trip.com, Skyscanner, Kiwi.com, Expedia, airline/member surfaces, and selected API/provider documentation.

Representative current official sources:

- Google Flights / Flight Deals:
  - https://www.google.com/travel/flights
  - https://support.google.com/travel/answer/16496104
- Trip.com Flights:
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
  - https://www.expedia.com/deals/flights
  - https://developers.expediagroup.com/docs/products/rapid
- Duffel:
  - https://duffel.com/docs/api/v2/offer-requests
  - https://duffel.com/pricing

No search-engine snippet or cached/indexed fare is accepted as exact Deal truth.

## 3. Semantic separation required by the target architecture

The following states must remain distinct:

1. `fare_exists`
   - A fare may exist in the market or in a restricted channel.
   - Absence from CFR evidence never proves market nonexistence.
2. `surface_shows_fare`
   - A named surface displayed a fare or fare hint.
   - This can still be cached, indicative, member-only, app-only, incomplete, or stale.
3. `radar_can_observe_fare`
   - CFR's currently authorized execution plane can automatically obtain the observation without bypass/evasion or a hidden human step.
4. `radar_can_reproduce_exact_fare`
   - CFR can re-run or follow the exact itinerary/date identity to a current complete fare with trusted seller/provenance evidence.
5. `formal_deal_truth`
   - The fare additionally satisfies CFR's anomaly-first Deal rules and current exact/reproducible/trust requirements.

This distinction is especially important for app/member/login fare classes. A known inaccessible class is a coverage blind spot, not a negative fare observation.

Suggested access-coverage states for later machine SSOT implementation:

- `public_automatable`
- `public_agent_observable_seed_only`
- `restricted_login_member_or_app`
- `credential_or_partner_gated`
- `not_observed_or_unknown`

Coverage reports must say what CFR attempted and could observe. They must not claim exhaustive market fare existence.

## 4. Capability matrix

Legend:

- `strong`: mature/current capability exposed by the substrate.
- `partial`: useful but incomplete or requires another surface for exact truth.
- `no`: capability not supplied for the CFR role.
- `gated`: access depends on credentials/partnership/login/member/app/human setup.

| Substrate / access path | Destination-free | Supplied date-window | Typical/anomaly | Absolute-low | Flexible dates | Open-jaw / multi-city | Taiwan / LCC evidence | Global breadth | Exact complete fare / freshness | Automation plane | Stable recurring TWD-0 | Access blind spots | Phase-1 role |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Google Flight Deals semantic surface | **strong** | partial/provider-selected constraints | **strong: typical + discount** | strong: also surfaces lowest-price matches | strong at Google product level | via Google Flights exact/multi-city | **live-proven** on TPE/TSA/RMQ/KHH and LCC/FSC examples | **strong** consumer surface | Deal record needs exact follow-up; seller revalidation still required | official Web; current backend via unofficial client | semantic surface free; automation access not guaranteed | partner/seller/member inventory can differ | **BORROW primary discovery/anomaly concept** |
| Google Explore / Flights exact / price graph / multi-city | **strong Explore** | strong when query shape is supported | partial price-insight context | **strong** | **strong** | **strong** | live-proven | **strong** | **strong after exact revalidation** | official Web; current backend via `gflights` | semantic surface free; automation access not guaranteed | same as above | **BORROW commodity search/completion** |
| `gflights` access client (current 0.3.0; upstream 0.3.1 exists) | strong | partial according to exposed request shape | strong for Flight Deals | strong | strong | strong | live-proven | strong | live-proven but subject to Google changes | GitHub runner/local | keyless today; not an official Google API; reliability risk | sticky 429; upstream/interface/ToS drift; no evasion allowed | **ADAPT replaceable machine adapter, reliability probation** |
| Trip.com consumer Web / app | **strong Anywhere** | **strong consumer UI** | no uniform CFR-qualified normal-price authority | strong | **strong** | **strong** | strong public examples | strong | current seller search available, but deterministic unattended exact extraction not proven | ChatGPT/public Web only in current CFR | public Web TWD 0; flight API self-service not proven | **member-only/app-only discounts explicitly exist** | **VERIFY-ONLY / recall seed; scoped substrate candidate** |
| Skyscanner Everywhere / consumer Web | **strong** | strong consumer UI | no CFR-qualified route-normal anomaly authority | strong indicative | **strong** | **strong** | strong | strong | Everywhere/month values can be estimated/cached; live search required for exact | ChatGPT/public Web; API if approved | Web TWD 0; API requires partner approval/key | API partnership gate; seller/member differences | **VERIFY-ONLY / recall seed; API inaccessible today** |
| Skyscanner Live API | no destination-free by itself; Indicative covers broad discovery | strong route/date live search | no CFR anomaly authority | strong if queried | API family supports indicative/flexible patterns | multi-city supported | likely broad but CFR access not granted | strong | **strong live + refresh** | backend only with approved API key | **not currently available as owner-independent TWD-0 dependency** | partnership criteria / API key | **credential/partner-gated candidate, not production dependency** |
| Kiwi consumer Anywhere / Nomad | **strong** | **strong date/range UI** | no qualified CFR anomaly authority | strong | **strong** | **strong, including Nomad/self-transfer** | useful | strong | current consumer results; final itinerary risk must be normalized | ChatGPT/public Web | public Web TWD 0 | app-only offers; self-transfer/virtual-interlining risk | **VERIFY-ONLY / recall and scoped candidate** |
| Kiwi official MCP | no proven destination-free primitive in current exposed search contract | bounded date/flex search | no | strong for requested route | ±date flexibility in current contract | current MCP contract is narrower than full consumer Nomad | plausible, not CFR-qualified live | broad | current search + booking links | agent/custom connector | service is public, but current Chat environment has no installed Kiwi connector | custom connector/human setup; MCP still evolving | **VERIFY-ONLY; promising agent lane, not Daily primary** |
| Expedia public Flights / Flight Deals | public destination/deal browsing available | strong consumer UI | **promising: current public deal cards can expose % less than typical** | strong | strong UI | multi-city | useful | strong | exact follow-up needed | ChatGPT/public Web | public Web TWD 0 | member/account deals; partner APIs gated | **VERIFY-ONLY now; fresh anomaly-fallback qualification candidate** |
| airline official public booking surfaces | no cross-market discovery | strong for own routes | promotion context only, not cross-route normal | route-local | carrier dependent | carrier dependent | **best own-inventory identity** incl LCC | carrier limited | **strong final seller/existence check when public** | Web/manual/agent; selective backend only when official feed exists | usually public | member/app/subscription inventory can be lower and inaccessible | **VERIFY-ONLY final seller truth** |
| airline member/app/subscription fare classes | no | carrier dependent | no general anomaly authority | can contain real low fares | carrier dependent | carrier dependent | material for Taiwan LCCs | carrier limited | real fare may exist | **restricted** | no autonomous public guarantee | login/member/app/payment/subscription | **ACCESS BLIND SPOT, never negative evidence** |
| `fli` / `flights==0.9.0` prior bakeoff | no | known-route/date/flexible only | no | route-local | strong in prior test | supported | useful fixed-basket evidence | broad | live-proven in prior bakeoff | GitHub runner if integrated | keyless; prior packaging defect | not currently integrated; maintenance uncertainty | **VERIFY-ONLY comparator/fallback candidate** |
| Duffel Flights API | no | **strong known route/date slices** | no | route-local | no destination-free discovery | multiple slices possible | requires credentialed coverage measurement | broad airline API network | **strong live offers; short expiry** | credentialed backend | **fails Daily TWD-0 economics at high search:book ratio** | access token + excess-search fee after 1500:1 | **VERIFY-ONLY for purchase-oriented exact checks, not Daily Radar** |
| CFR own price history | no | n/a | useful fallback/supplemental anomaly | records observed floors only | n/a | preserves observed shapes | only what CFR observed | only what CFR observed | exactness equals retained source evidence | deterministic backend | **yes** | cannot see inaccessible or never-searched space | **BUILD/KEEP as provenance + fallback evidence, not primary search engine** |
| CFR public-intelligence crawlers | seed-only | seed-only | no | hint only | no | no | useful for promos/local editorial | broad if indexed | not exact fare truth | Web / bounded crawler | yes if low maintenance | login/private groups invisible | **SIMPLIFY: optional Signal/seed lane only** |
| custom city×date×city brute force | potentially | yes by enumeration | no unless external baseline added | potentially | yes at high cost | combinatorial | depends on provider | costly | only as good as provider | custom backend | poor sustainability/reliability | still cannot cover restricted inventory | **DO NOT BUILD now** |

## 5. What changed since the 2026-08-13 convergence

The 2026-08-13 core insight survives: CFR should borrow Google airfare-search primitives rather than build a broad search engine or make repository price history its primary anomaly model.

Three corrections are required now:

### 5.1 Semantic substrate versus access adapter

Google Flights / Flight Deals is the borrowed semantic substrate. `gflights` is only one unofficial access adapter to that substrate.

Current CFR accidentally risks treating those as the same architectural commitment. They must be separated. A future adapter replacement must not require changing CFR Deal semantics, FTR handoff semantics, or search intent.

The 2026-08-19 sticky-429 incident proves the access adapter has a real reliability boundary. Fail-closed circuit behavior is correct, but reliability work should focus on replaceable qualified access rather than evasion or retries.

### 5.2 Absolute-low is first-class output even when not a Deal

Google Flight Deals itself currently distinguishes unusually discounted trips from other lowest-priced matches. CFR should likewise preserve separate truth classes:

- `Deal`: anomaly-qualified, exact/reproducible current airfare.
- `absolute_low_non_deal`: exact/revalidated current low airfare without the required anomaly truth.
- `Signal`: weaker discovery/promotional evidence.

Do not make absolute-low a fake Deal and do not hide it as diagnostic-only when serving the FTR contract or Scoped Mode.

### 5.3 Geography should follow qualified substrate breadth, not legacy compute limits

Google, Trip.com, Skyscanner and Kiwi consumer discovery products are global. CFR therefore no longer has a product reason to make Asia/Oceania a permanent ceiling merely to avoid custom search explosion.

The correct target is substrate-native worldwide discovery with truthful attempted coverage, while keeping Japan/Korea/China as priority markets. This is not a claim of exhaustive global fare coverage, and it does not authorize a worldwide city/date brute-force matrix.

## 6. Target architecture

Use the smallest stable architecture that preserves differentiated CFR truth.

### Layer A — CFR product/truth core: BUILD/KEEP

CFR owns only the logic that is genuinely product-specific:

- normalized 1-adult economy probe policy;
- exact Taiwan origin/return gateway and destination route-shape identity;
- anomaly-first Deal qualification and ordering;
- separate absolute-low non-Deal selection;
- Signal isolation;
- exact/reproducible/fresh/trusted seller gates;
- access-blind-spot and attempted-coverage truth;
- immutable provenance/history/audit evidence;
- bounded Daily/Scoped orchestration and fail-closed provider-health semantics;
- versioned CFR→FTR handoff.

### Layer B — commodity search capabilities: BORROW

Borrow mature substrate capabilities instead of recreating them:

- destination-free discovery;
- typical-price/anomaly intelligence;
- worldwide broad discovery;
- flexible-date/fare-calendar search;
- exact fare search;
- multi-city/open-jaw search;
- seller/deeplink handoff.

Google Flights / Flight Deals remains the best currently qualified combined semantic substrate because the existing CFR live bakeoff proved all of those capabilities except unrestricted access stability.

### Layer C — replaceable access adapters: ADAPT

Keep a thin provider-capability interface rather than a large source-specific search engine. The interface should express capabilities, not brand assumptions, for example:

- `discover_destination_free(origin, policy)`
- `discover_scoped(origin, availability_window, policy)`
- `search_exact(itinerary_query)`
- `search_flexible(route_query)`
- `search_multi_city(legs)`
- `get_anomaly_context(candidate)`
- `get_booking_offers(candidate)`

Current `gflights` can implement qualified calls behind this boundary, with fixed project identity, no proxy, no session/UA rotation, bounded calls and sticky-429 fail-closed handling. It must remain replaceable.

Do not automatically upgrade to upstream `gflights` 0.3.1 merely because it is newer. A small isolated qualification package should compare the pinned client with the current upstream release using the fixed CFR basket and existing guardrails before any dependency change.

### Layer D — Web/agent recall and verification lane: VERIFY-ONLY by default

A Web/agent lane is legitimate, but its evidence must be typed.

Use public Google/Trip.com/Skyscanner/Kiwi/Expedia/airline surfaces for:

- independent recall seeds;
- current source capability checks;
- final seller/cross-check evidence;
- access-blind-spot reporting.

A Web/agent observation does not automatically satisfy canonical backend coverage or formal Deal truth. It may do so only if a later implementation proves exact query identity, current complete price, trusted seller/provenance and repeatable automated observation under the same CFR gates.

Kiwi's official MCP is worth a bounded follow-up because it is an explicit agent interface with current search results and booking links. Today it is not a Daily Radar replacement: the current exposed contract is narrower than consumer Anywhere/Nomad, and the current Chat environment does not have it installed as an available connector.

## 7. Daily Radar conclusion

Target Daily Radar:

1. For each configured Taiwan origin, borrow destination-free Flight Deals/Explore-style discovery rather than enumerate destinations.
2. Preserve route-relative anomaly as the formal Deal authority when qualified typical-price evidence is present.
3. Preserve low-price candidates separately even without anomaly truth.
4. Revalidate serious candidates on exact route/date/current fare.
5. Delegate flexible-date and multi-city/open-jaw search to mature substrate primitives for competitive endpoints.
6. Expand geography using substrate-native worldwide results; keep JP/KR/CN as priority slices rather than hard scope boundaries.
7. Fail closed when the automatic access adapter degrades. External Web recall may surface additional Signals but must not silently convert a failed canonical provider slice into succeeded coverage.

No custom fare engine or global brute-force matrix is justified.

## 8. Query / Scoped Mode conclusion

The smallest stable product interface remains:

`availability_windows -> cheap airfare opportunities`

with both `Deal` and `absolute_low_non_deal` outputs preserved.

Current RP-03 is a useful bounded interim implementation because it:

- binds provider calls to supplied windows instead of running the canonical horizon then post-filtering;
- keeps deterministic per-window coverage;
- fails closed when a supplied window was not actually attempted;
- reuses CFR exact revalidation and truth classes.

However it is not the final ideal substrate architecture. The current adapter cannot truthfully claim arbitrary-window coverage from Explore/cheapest-date/open-jaw surfaces, so those surfaces are explicitly `not_attempted`.

Phase-1 target:

- retain the current bounded planner as `ADAPT` interim;
- define a capability-based `discover_scoped()` contract;
- run a bounded qualification specifically for native destination-free supplied-window capability across Google current surfaces, Trip.com Anywhere/date-range, Skyscanner Everywhere/date controls, Kiwi Anywhere/date range/agent surface, and Expedia current Deal discovery;
- prefer `BORROW` if any candidate is automatable/repeatable/TWD-0;
- do not build a city×date×destination brute-force engine unless that focused qualification proves external substrates insufficient.

Open-jaw in Scoped Mode should be a delegated completion of selected endpoints when the chosen substrate supports it. It is not a reason to brute-force city pairs.

## 9. Access blind spots

Known examples prove that `Radar cannot access -> fare does not exist` is invalid.

Examples:

- Trip.com explicitly promotes member/app-only discounts and offers.
- Kiwi promotes app-exclusive offers/features.
- airline programs can expose subscription/member fares; Tigerair Taiwan's member/subscription products are an example of a Taiwan-LCC restricted fare class.
- OTA/airline seller inventory can differ by logged-in state, market, payment method, loyalty status or app channel.

Target semantics:

- CFR may publish a formal Deal only from an observable and reproducible fare under its current trust contract.
- A known restricted fare class should be recorded as `restricted_known` / coverage blind spot with source identity when useful.
- CFR must not invent the restricted price if it cannot observe it.
- CFR must not report the public fare as `the cheapest fare that exists`; it may only report the cheapest fare observed/revalidated in the attempted public/authorized coverage.
- Restricted-channel hints may become Signals, but not formal Deals or exact absolute-low candidates without exact authorized evidence.

## 10. Keep / retire / simplify map

### KEEP

- anomaly-first Deal semantics and destination-airport normalization;
- exact/revalidated complete-airfare gate;
- separate bounded absolute-low non-Deal producer;
- open-jaw/different Taiwan gateway route-shape semantics;
- immutable Git-backed price/run/provenance evidence;
- provider health and slice-faithful attempted coverage;
- sticky-429 fail-closed circuit semantics;
- canonical/scoped/recovery identity isolation;
- CFR→FTR schema/checksum/freshness/repair contract.

### KEEP BUT DEMOTE / ADAPT

- `gflights`: keep as current machine adapter, not as sacred architecture or sole durable substrate; qualify current upstream separately.
- own price history: keep for provenance, rolling lows, supplemental/fallback anomaly; do not expand into a primary custom normal-price engine.
- public Web intelligence: keep only as typed Signal/seed/cross-check evidence.
- source router: keep as a thin capability router; remove brand/legacy pipeline assumptions over time.

### SIMPLIFY

- market-specific search algorithms: JP/KR/CN remain priority slices, not separate mandatory fare engines.
- fixed-watch crawler program: retain only low-maintenance high-signal public sources; failures do not define airfare coverage.
- legacy near-term/absolute presentation machinery: preserve useful absolute-low views where they serve users/FTR, but do not mix them into anomaly Deal ranking.
- open-jaw construction: delegate to substrate multi-city where available instead of custom combinatorial construction.

### RETIRE / DO NOT REVIVE

- mandatory outbound-one-way-first architecture;
- unbounded city×date×city brute force;
- `trvl` as production core;
- silent/executable fallback claims for providers not actually invokable;
- any anti-bot path requiring CAPTCHA bypass, stealth fingerprinting, proxy rotation, residential proxy, rotating identity or session evasion;
- assumption that Asia/Oceania is the desired permanent product ceiling;
- assumption that inaccessible app/member fares do not exist.

### VERIFY-ONLY / CANDIDATES, NOT COMMITMENTS

- Expedia public Flight Deals as a possible second anomaly/recall surface: current public cards now expose typical-price discount language, but Taiwan-origin repeatability must be measured before promotion.
- `fli` as an exact/flexible comparator.
- Trip.com / Skyscanner / Kiwi consumer surfaces as recall/scoped/final cross-check lanes.
- Kiwi MCP as an agent-native bounded search candidate.
- Skyscanner Live only if an approved key ever becomes available without violating the owner-approved cost/credential policy.
- airline official pages as final seller/existence verification.

## 11. Sustainable cost conclusion

The target architecture can remain recurring TWD 0 only if production depends on public/free borrowed surfaces plus disposable compute already allowed by CFR.

Do not adopt as unattended Daily dependencies without owner approval:

- Skyscanner API: requires partnership/API-key approval and is not currently available as a guaranteed free production dependency.
- Kiwi Tequila: new partnerships are invitation-only under current official policy.
- Expedia partner flight connectivity: not a demonstrated self-service free daily Radar API.
- Duffel: requires credentials and explicitly charges excess search above a 1500:1 search-to-book ratio, which is structurally mismatched with an autonomous discovery radar.
- paid search-API wrappers/proxies: paid resource gate and do not solve product truth by themselves.

## 12. CFR -> FTR implications

The existing handoff architecture is largely correct and should be preserved:

- FTR consumes exact airfare opportunities, not CFR's internal search implementation.
- Formal Deals and bounded exact absolute-low non-Deals remain distinct candidate kinds.
- FTR must not promote generic Signals.
- exact dates, Taiwan gateways, destination route shape, complete airfare, observation time and evidence/provenance remain required.
- provider/surface/origin/market coverage remains execution truth, not candidate count.

Required future-compatible additions are small:

1. expose geographic/attempted coverage without assuming Asia/Oceania is exhaustive;
2. optionally expose typed access-blind-spot metadata so FTR knows a route/fare class may be restricted/unobservable;
3. keep provider identity abstract enough that replacing `gflights` or adding an agent lane does not change the consumer contract;
4. Scoped snapshots should retain the same window-level attempted/not-attempted truth when a new substrate is plugged in.

No FTR Phase-2 work is required or authorized by this conclusion.

## 13. BUILD / BORROW decision

### BORROW

- destination-free discovery
- worldwide broad discovery
- typical-price/anomaly context
- fare calendars/flexible dates
- exact airfare shopping
- open-jaw/multi-city search
- seller/deeplink handoff

### ADAPT

- thin capability router and normalized adapters
- current `gflights` adapter with strict no-evasion guardrails and reliability accounting
- current bounded Scoped planner until a native arbitrary-window substrate is qualified
- source-specific normalization into CFR evidence types

### VERIFY-ONLY

- public OTA/metasearch/airline Web surfaces
- Expedia's newly observed anomaly-like public deal cards pending Taiwan repeatability
- Trip.com / Skyscanner / Kiwi for cross-source recall and scoped research
- Kiwi MCP pending connector availability and capability qualification
- `fli` comparator
- airline seller surfaces

### BUILD

Only CFR-specific product truth and orchestration:

- anomaly Deal semantics
- absolute-low non-Deal semantics
- trust/freshness/reproducibility gates
- access/coverage truth
- durable evidence/history
- FTR handoff
- bounded fail-closed orchestration

A custom airfare search engine or brute-force fare floor does **not** pass the BUILD gate today.

## 14. Product Intent delta separated from implementation

Current Product Intent still encodes Asia/Oceania as a hard scope and does not make access-blind-spot semantics explicit enough for the clarified product direction.

A separate Product Intent-only change should:

1. make Daily Radar and Query/Scoped search explicit first-class CFR modes;
2. replace the permanent Asia/Oceania ceiling with worldwide discovery when qualified sustainable substrates make it practical, while retaining Japan/Korea/China priority;
3. state that broader capability never implies exhaustive global fare coverage;
4. explicitly state the access-blind-spot rule: restricted/member/app/login fare classes may exist even when CFR cannot automatically observe or reproduce them;
5. preserve anomaly-first Deal truth, separate absolute-low non-Deals, open-jaw, 1-adult economy normalization, exact/reproducible trust, and TWD-0 default production.

Runtime/source-routing changes must follow as separate atomic implementation packages after the Product Intent change is merged.

## 15. Issue #51 disposition

Issue #51 should be closed as **superseded by #56 / this Phase-1 conclusion**, not retained as the architecture contract.

Its surviving ideas are redistributed as follows:

- SR-01 source census: absorbed and superseded by Phase-1 evidence.
- SR-02 custom brute-force producer: rejected for now under BUILD-vs-BORROW; reopen only if focused scoped/recall qualification proves mature borrowed substrates insufficient.
- SR-03 curated intelligence: retained only as a simplified optional Signal/seed lane.
- SR-04 executable redundancy: survives as a narrow future access-adapter qualification/integration package, not as permission to add an arbitrary second provider.

## 16. Remaining blockers and gates

### Technical / researchable

- qualify current upstream `gflights` release versus pinned 0.3.0 under the fixed CFR basket and no-evasion rules;
- qualify whether Expedia's current public Flight Deals anomaly cards are repeatable for Taiwan-origin discovery;
- focused Scoped native-window bakeoff across Google/Trip/Skyscanner/Kiwi/Expedia access paths;
- determine whether any agent-native path can produce repeatable exact evidence that should count as an execution plane rather than seed-only evidence.

### Inaccessible substrate

- app-only/member-only/login-only fare classes where no authorized automated public observation exists.

### Credential / human-action gate

- Skyscanner API partnership/key;
- Kiwi custom MCP/connector installation in the current Chat environment if later chosen for qualification;
- any airline/OTA member login needed to observe restricted inventory.

These are not required to accept the Phase-1 architecture.

### Paid-resource gate

- Duffel at radar-scale search ratios;
- paid search wrappers/proxies/APIs;
- any production API without a proven sustainable free quota.

### Product-intent decision

None remains after the 2026-08-21 owner clarifications. The required Product Intent edit is an explicit durability update, not a request for another owner decision.

## 17. Recommended atomic follow-ups

After the Product Intent-only change is independently audited and merged:

1. **CFR-SR-A — capability-router / scope convergence**
   - make machine SSOT geographic scope and provider-capability semantics match worldwide substrate-native discovery without claiming exhaustiveness;
   - keep current runtime behavior until each capability is qualified.
2. **CFR-SR-B — gflights current-release + access-reliability qualification**
   - compare pinned 0.3.0 with current upstream under fixed UA/no-proxy/no-evasion and fixed basket;
   - dependency change only if evidence justifies it.
3. **CFR-SR-C — Scoped native-window borrow bakeoff**
   - compare externally supplied-window primitives; no brute force implementation.
4. **CFR-SR-D — second anomaly/recall access qualification**
   - focus first on Expedia public Flight Deals and other surfaces that now expose typical-price context;
   - integrate only if repeatable/current/trusted and TWD-0.
5. **CFR-SR-E — access-blind-spot evidence/coverage schema**
   - add typed restricted/unobservable coverage metadata without fabricating prices or weakening Deal truth.
6. **CFR-SR-F — public-intelligence simplification**
   - remove low-value fixed-watch/crawler complexity that does not improve Deal truth or recall enough to justify maintenance.

Implementation must not be bundled into this research conclusion.
