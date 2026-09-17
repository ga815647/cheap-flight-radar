# Multi-city / open-jaw redundancy qualification — 2026-08-23

Status: **NO QUALIFIED ZERO-RECURRING-COST REDUNDANCY FOUND**

This document records the bounded qualification package for the remaining
GFlights single-point failure on CFR multi-city / open-jaw execution. It extends
SR-D; it does not replace `flight-radar.yaml` as the execution-policy SSOT.

## Authority and scope

- Repository: `ga815647/cheap-flight-radar`
- Qualification base: `96b8a0df824cbf1e44a3db38fe9b63b0d3c0267d`
- Canonical production evidence date: 2026-08-23
- Prior authority: `docs/executable-redundancy-qualification-2026-08-21.md`
- Experiment PR: #77, closed without merge

The package was limited to executable redundancy for:

- combined multi-city / destination-side open-jaw searches;
- mixed Taiwan outbound/return gateway variants used by CFR/FTR.

A candidate could qualify only if it was runnable from a disposable
GitHub-hosted Ubuntu runner, required TWD 0 recurring provider/API/proxy cost,
used no CAPTCHA bypass, proxy rotation, residential IP, stealth/fingerprint
impersonation, UA/session rotation, or rate-limit-reset tricks, and produced an
exact requested multi-leg itinerary with one complete current airfare result.
Documentation or schema capability without a live complete fare was not enough.

## Starting production evidence

The 2026-08-23 canonical Radar completed in a degraded state:

- normal GFlights exact/flexible calls encountered sticky HTTP 429;
- the already-qualified Kiwi MCP known-route fallback recovered 40/40 fallback
  attempts;
- that fallback remains intentionally scoped to exact/flexible known-route
  execution and excludes open-jaw / multi-city;
- the multi-city lane therefore remained dependent on GFlights.

The real canonical open-jaw benchmark used below was:

1. KHH -> DRP on 2026-10-11
2. ILO -> KHH on 2026-10-19

GFlights produced a complete combined airfare of **TWD 55,591** for that shape in
2026-08-23 canonical evidence. The durable run is:

`data/run-evidence/2026/08/23/production-radar-20260823T081129+0800/run-result.json`

on `history/price-observations`.

## Candidate evaluation

| Candidate | Actual multi-city/open-jaw capability | TWD 0 recurring-cost requirement | Live executable qualification | Decision |
| --- | --- | --- | --- | --- |
| Existing Kiwi public MCP | Current tool contract covers known-route exact/flexible; no multi-city tool | Passes for already-qualified SR-D scope | Not applicable for multi-city | Keep existing scope; do not broaden |
| Kiwi consumer GraphQL (`api.skypicker.com/umbrella/v2/graphql`) | Live schema exposes `multicityItineraries`, `SearchMulticityInput`, `ItineraryMulticityInput` and Nomad types | Keyless direct calls succeeded in bounded runner probes | **Failed**: three live fare probes returned zero combined itineraries | Researched/live-probed candidate only; not an executable CFR backend |
| Skyscanner Flights Live Prices API | Official API supports multi-city using multiple `queryLegs`, up to six legs, with the normal Live Prices response | Partner/API access and a durable TWD 0 production allowance are not established for CFR | Not live executable in current CFR environment | Researched candidate only |
| Duffel Flights API | Multi-slice offer model can represent multi-leg itineraries | Fails CFR cost invariant: current pricing charges an excess-search fee above a 1500:1 search-to-book ratio | Not eligible for CFR search-only fallback | Reject for recurring-cost risk |
| Amadeus Self-Service | Flight Offers Search is a real flight-offer substrate, but current Self-Service access requires credentials and its dataset has documented carrier/content limitations | No existing CFR credential/execution path and no durable proof that the required production usage is permanently TWD 0 | Not live executable in current CFR environment | Researched candidate only |
| fli / other Google-derived wrappers | Prior SR-D evidence already established shared Google upstream and/or non-compliant transport behavior | Not independent redundancy | Do not retest | Reject |
| Browser/stealth/proxy scraping variants | Some can expose consumer multi-city UI data | Violates this package's transport/safety contract | Forbidden | Reject |

Current external references used for the qualification boundary:

- Skyscanner multi-city: https://developers.skyscanner.net/docs/flights-live-prices/multiCity
- Skyscanner Live Prices: https://developers.skyscanner.net/docs/category/flights-live-prices-api
- Duffel pricing: https://duffel.com/pricing
- Amadeus Self-Service FAQ: https://admin.developers.amadeus.com/self-service/apis-docs/guides/developer-guides/faq/

## Kiwi consumer GraphQL live evidence

All Kiwi GraphQL probes ran on disposable GitHub-hosted Ubuntu runners. Each
fare/capability probe used one direct HTTP request, a fixed CFR user agent, no
credential or cookie, no proxy, no retry, no browser impersonation, no session
mutation, and no rate-limit reset.

### 1. Schema capability

Exact head: `93fec2ead77528cb4c800065a670d123319fa1e9`

- Actions run: `32616285112`
- Job: `97137460179`
- HTTP: 200
- GraphQL errors: none
- Observed query/type contract included `multicityItineraries`,
  `SearchMulticityInput`, `ItineraryMulticityInput`, `SearchNomadInput`, and
  `nomadItineraries`.

This proved a machine-reachable multi-city schema. It did **not** qualify fare
execution by itself.

### 2. Combined-fare output contract

Exact head: `597f7386067e7348ece725f95c1ac65f03da6c1d`

- Actions run: `32616332143`
- Job: `97137583598`
- HTTP: 200
- GraphQL errors: none
- `SearchMulticityInput.itinerary` was observed as
  `[ItineraryMulticityInput]`.
- `ItineraryMulticity` exposed sectors, combined price fields, and booking
  options.

This matched the semantic shape CFR needs from `open_jaw(legs[])`: one combined
multi-leg result rather than a synthetic sum of unrelated one-way tickets.
Again, the type contract alone was insufficient for qualification.

### 3. Real 2026-08-23 CFR open-jaw benchmark

Exact head: `0fed667751c9f08834106088abc9f6d884dcc4e9`

- Actions run: `32616378220`
- Job: `97137697574`
- Requested legs:
  - KHH -> DRP, 2026-10-11
  - ILO -> KHH, 2026-10-19
- HTTP: 200
- GraphQL errors: none
- Provider error: none
- Response type: `Itineraries`
- Returned `ItineraryMulticity` rows: **0**
- Exact combined airfare evidence: **none**

GFlights had a complete TWD 55,591 combined fare for the same canonical route
shape. Kiwi therefore did not recover the actual 2026-08-23 blind spot.

### 4. Real mixed-Taiwan-return variant

Exact head: `3c233d97571d57302667dcc0e5b8e19f253e790f`

- Actions run: `32616427888`
- Job: `97137826099`
- Requested legs:
  - KHH -> DRP, 2026-10-11
  - DRP -> TPE, 2026-10-19
- HTTP: 200
- GraphQL/provider errors: none
- Returned `ItineraryMulticity` rows: **0**
- Exact combined airfare evidence: **none**

### 5. Broader mixed-Taiwan-gateway control

A final bounded control used a different market to test whether the candidate
could produce any positive combined fare evidence outside the DRP shapes.

Exact head: `4a0fd6890fdbb6da9662bbfdf6e0b998651bc7f5`

- Actions run: `32616459083`
- Job: `97137904424`
- Requested legs:
  - TPE -> NRT, 2026-10-05
  - NRT -> KHH, 2026-10-09
- HTTP: 200
- GraphQL/provider errors: none
- Returned `ItineraryMulticity` rows: **0**
- Exact combined airfare evidence: **none**
- Exact-head repository CI run `32616459090`: success

This broader control also returned zero. It supplied no positive multi-city fare
execution evidence beyond the DRP shapes; it does not establish why the endpoint
returned zero. No additional probing was justified under the bounded
qualification contract.

## Durable decision

**Do not add an automatic multi-city/open-jaw fallback.**

No candidate demonstrated all required properties at once. In particular,
Kiwi consumer GraphQL is now known to expose a machine-reachable multi-city
schema, but it produced no exact combined fare on any of the three bounded fare
proofs. Treating that as an executable backend would turn a researched
capability into false coverage.

The current `flight-radar.yaml` behavior is therefore intentionally unchanged:

- GFlights remains the executable multi-city/open-jaw backend;
- `kiwi_mcp_exact` remains a known-route exact/flexible fallback only;
- no provider may be silently routed into open-jaw merely because its docs,
  website, or GraphQL schema mention multi-city;
- if the GFlights multi-city lane is technically unavailable and no future
  provider has a fresh qualified execution contract, CFR must expose the
  multi-city/open-jaw coverage blind spot and fail closed;
- separate one-way prices must not be added together and mislabeled as one
  complete open-jaw airfare.

This is a provider/search coverage blind spot, not an FTR repair incident.
Future qualification should start from this evidence and test only materially
new zero-recurring-cost substrates or a materially changed version of a prior
candidate.
