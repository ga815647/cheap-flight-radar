# CFR-SR-C — Scoped native-window BORROW bakeoff (2026-08-21)

## Decision

**KEEP the current bounded CFR Scoped planner for now. No candidate qualified as a TWD-0 executable destination-free native availability-window substrate.**

This is a negative qualification, not an endorsement of custom search as product architecture. Query/Scoped Mode remains first-class Product Intent; the current date-pair planner stays an implementation fallback only until a mature substrate can actually accept the required window contract under CFR's access and truth gates.

## Required contract

A BORROW candidate had to satisfy all of the following at once:

1. accept a supplied availability window (plus optional duration) as query input;
2. remain destination-free at discovery time;
3. return machine-observable airfare candidates rather than only a consumer UI;
4. be executable from the current ChatGPT/GitHub CFR environment with authorized ongoing TWD-0 access;
5. avoid broad-horizon post-filtering and avoid CFR enumerating the city/date matrix itself;
6. preserve explicit provider/surface/window coverage and provenance so unqueried slices cannot become success;
7. support CFR exact revalidation before Deal or exact absolute-low truth.

## Candidate results

### gflights 0.3.1 / Google Flights surfaces — **ADAPT/KEEP, not native-window BORROW**

Qualified in SR-B as the current replaceable machine adapter. It supplies the primitives CFR needs, but not the full Scoped discovery contract in one native call:

- `deals` / Flight Deals is destination-free but is anchored by outbound/return dates rather than an arbitrary supplied availability interval;
- `explore` supports destination-free discovery with month/duration-style inputs, not the arbitrary start/end window contract CFR exposes;
- `cheapest_dates` and the departure/return grid are flexible-date capabilities but require a known destination;
- exact and multi-city remain excellent completion/revalidation surfaces after a destination exists.

Current gflights documentation: https://docs.rs/crate/gflights/latest

Therefore the current RP-03 planner still has to translate each supplied window into a bounded set of destination-free Deal anchors, then exact-revalidate competitive endpoints. That is ADAPT, not native-window BORROW.

### Skyscanner — **consumer capability exists; executable gate fails**

Skyscanner's public product exposes Everywhere plus flexible/whole-month search. That proves the commodity capability exists at the product layer.

Official help:
https://help.skyscanner.net/hc/en-us/articles/201150942-How-do-I-find-the-best-prices

Its machine Travel APIs require an API key obtained only after Partnerships review. The live-prices API also requires explicit origin + destination + date legs, so it is not the destination-free arbitrary-window live interface CFR needs.

Official API authentication / live-price contract:
https://developers.skyscanner.net/docs/getting-started/authentication
https://developers.skyscanner.net/docs/flights-live-prices/overview

Result: VERIFY-ONLY/public consumer substrate under current access. No existing authorized TWD-0 executable lane.

### Kiwi.com — **consumer capability exists; executable gate fails**

Kiwi's public Search to Anywhere supports flexible time-of-stay, calendar, price range and other useful filters. This is close to the desired user-facing capability.

Public description:
https://www.kiwi.com/en/cheap-flights/travel-hacks/flight-price-alerts/

Kiwi states that Tequila previously offered public B2B API/white-label/affiliate access, but new Tequila partnerships are invitation-only.

Partnership policy:
https://media.kiwi.com/articles-and-interviews/better-for-business-kiwi-com-takes-a-new-approach-to-partnerships/

Result: no currently authorized, ongoing TWD-0 executable API path for CFR. Public UI remains a verification/seed surface, not Scoped execution coverage.

### Trip.com — **consumer capability exists; executable gate fails**

Trip.com publicly advertises Anywhere and flexible-date/month fare discovery.

Public product evidence:
https://www.trip.com/newsroom/
https://www.trip.com/guide/info/how-do-i-search-for-flights-with-flexible-dates.html

The developer/partner surface is account/partner oriented; authenticated integration material requires partner credentials. The public affiliate tooling does not provide CFR a destination-free native-window machine fare query.

Developer/partner evidence:
https://developers.trip.com/
https://developers.trip.com/signIn/
https://www.trip.com/partners/help/faq/integration

Result: VERIFY-ONLY under current access, not a qualified BORROW execution lane.

### Expedia — **machine flight path not qualified/currently available**

Ordinary Expedia Web remains useful as public recall/verification evidence, but current executable API options do not satisfy the gate. Expedia's current Rapid Flight API is documented as coming soon, while legacy Flight Listings requires Expedia API key/authorization and explicit date/origin/destination parameters.

Developer evidence:
https://developers.expediagroup.com/rapid/
https://developers.expediagroup.com/xap-apis/api/shopping-apis/flight-listings

Result: no qualified destination-free native-window TWD-0 execution path.

## Why not replace the current planner with consumer Web automation?

A visible Everywhere/Anywhere/flexible-date UI is not equivalent to an authorized deterministic machine contract. Automating private app surfaces, requiring login/session state, or relying on anti-bot workarounds would violate the accepted access architecture. Indexed Web observations can still seed or verify candidates, but they cannot make an unqueried Scoped window look covered.

## Current bounded implementation retained

The existing `cheap_flight_radar.scoped_search` implementation remains in force:

- supplied windows are terminal coverage dimensions;
- complete trips must fit one supplied window;
- broad-horizon-then-post-filter is forbidden;
- destination-free discovery is bounded and deterministic;
- unconstrainable surfaces are `not_attempted`;
- exact completion/revalidation remains CFR truth;
- zero candidates is not failure, but an unqueried window cannot be success;
- Scoped identity remains isolated from canonical/operator/recovery state.

## Revisit trigger

Re-open native-window BORROW only when at least one candidate offers an actually executable TWD-0 contract satisfying both destination-free discovery and arbitrary supplied-window constraints. A new consumer UI feature alone is insufficient.

SR-C therefore closes as **KEEP/ADAPT current bounded planner; no qualified native-window BORROW substrate as of 2026-08-21**.
