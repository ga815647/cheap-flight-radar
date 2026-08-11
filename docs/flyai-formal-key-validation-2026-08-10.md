# FlyAI formal-key validation — 2026-08-10

Status: credentialed Issue #2 evidence; not a production-collector selection.

This checkpoint compares the formal FlyAI API-key run against the previously recorded keyless trial without rerunning the keyless baseline. It does not change `flight-radar.yaml` policy.

## Durable evidence

- Provider: FlyAI `search-flight`
- CLI: pinned `@fly-ai/flyai-cli@1.0.16`
- Credential mode: formal API key supplied through GitHub Actions secret `FLYAI_API_KEY`
- Exact head: `e2a051a3e845bd160412d89681f87f9e9d8d8809`
- Workflow run: `31401256604` — success
- Artifact: `flyai-formal-key-fixed-basket` (`9067758804`)
- Observation timestamp: `2026-08-10T23:00:43.686709+08:00`

The workflow only confirms secret presence and configures the key in the ephemeral runner. The secret value is not printed or stored in the artifact.

## Fixed-basket result

Applicable structured round-trip cases J1–J4, K1–K2, C1–C2, S1, L1 all returned at least one exact-airport/date itinerary:

- exact case coverage: **10/10 = 100%**
- returned items: **92**
- exact-airport/date items: **85/92 = 92.4%**
- airport-integrity rejects: **7/92 = 7.6%**
- cases containing at least one airport substitution: **3/10**

The prior keyless checkpoint was 10/10 exact cases, 81/89 exact items, 8/89 rejects and substitutions in 4/10 cases. The formal-key snapshot therefore improved first-snapshot item integrity slightly, but did not eliminate substitution.

Notable exact carrier names include both full-service and low-cost inventory, including Peach, Jetstar Japan, Tigerair Taiwan, T'way, Eastar Jet, Jeju Air, Jin Air, VietJet, Scoot and Spring Airlines. This establishes that the formal-key result set is not full-service-only. It does **not** establish LCC completeness because there is still no independent exact-date reference inventory denominator.

## Airport-integrity observations

Exact returned-segment gating remains mandatory.

- C1 `TSA-SHA`: 10 returned, 7 exact; 3 substituted airports.
- C2 `TPE-XMN`: 10 returned, 9 exact; 1 substitution.
- L1 `TPE-LAX`: 10 returned, 7 exact; 3 substitutions.
- J1 `TPE-NRT`: all 10 returned items were exact in this formal-key snapshot, unlike the earlier keyless snapshot that contained an HND substitution.

The provider result set must therefore never be trusted solely because the requested route was airport-specific.

## Fare semantics

A recursive scan of the formal-key responses found no keys containing:

- `currency`
- `tax`
- `baggage`
- `fare`

`ticketPrice` remains a provider-returned raw numeric observation only. Its currency, tax inclusion, baggage normalization and fare-family semantics are not inferred.

Consequently these Issue #2 metrics remain **unknown** from FlyAI alone:

- lowest-verifiable fare hit rate
- cross-source price gap / gap to lowest revalidated fare
- LCC miss rate

Raw `ticketPrice` values must not be interpreted as TWD, CNY or another currency without explicit provider evidence.

## Repeat-query stability

The formal-key run repeated each identical exact query immediately and compared the first query's selected lowest raw-price exact itinerary signature.

- repeat provider success: **10/10 = 100%**
- same selected itinerary found: **8/10 = 80%**
- same selected itinerary and identical raw `ticketPrice`: **5/10 = 50%**

The prior keyless repeat-query checkpoint was 90% / 90% on those last two measures. The formal key therefore did not demonstrate improved immediate result stability in this observation.

This procedure is only a **repeat-query stability proxy**. It is not an offer refresh, fare confirmation, checkout revalidation or stale-rate measurement. Therefore:

- true `revalidation_success` = **unknown**
- true `staleness_rate` = **unknown**

The previously discarded experiment that appended multiple flight numbers to one `--transport-no` parameter remains invalid and was not repeated.

## J5 open-jaw

The tested `search-flight` CLI still does not expose a structured combined multi-city/open-jaw query for J5.

- J5A `TPE-NRT 2026-10-13`: 10 returned, 9 exact.
- J5B `KIX-TPE 2026-10-18`: 10 returned, 10 exact.

These two successful one-way legs must not be represented as one open-jaw fare.

## Issue #2 decision

The formal key materially strengthens FlyAI as a **China specialist deep-search candidate** because exact case coverage is strong, China airport-pair searches work, and LCC inventory is present. It is not yet sufficient to select FlyAI as a production revalidation source or to close the provider-stack decision.

Remaining blockers are evidence blockers, not implementation guesses:

1. no explicit currency/tax/baggage/fare semantics in the tested FlyAI response;
2. no documented/tested true offer-refresh result in the CLI path used here;
3. no independent credentialed exact-date provider or purchase-surface denominator for LCC miss, lowest-verifiable hit and price gap;
4. World/Japan/Korea broad-discovery selection still depends primarily on Skyscanner access or another measured broad-discovery source.

Issue #3 production source-router/adapter work should therefore not be started from this FlyAI-only evidence yet. The reusable validation harness added with this checkpoint exists so the next credentialed provider can be measured against the same exact-airport/date and evidence semantics instead of inventing provider-specific metrics.
