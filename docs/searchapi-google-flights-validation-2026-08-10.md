# SearchAPI Google Flights validation — 2026-08-10

Status: Issue #2 credentialed reference evidence; not a production Google Flights collector decision.

## Purpose

Use SearchAPI.io's structured Google Flights API as a limited independent benchmark/revalidation reference while the project lacks a zero-cost Skyscanner/Duffel live credential. This does not promote a Google Flights scraper or SearchAPI itself into the production source router.

## Credential and safety

- GitHub Actions secret: `SEARCHAPI_API_KEY`.
- Secret is passed through the Authorization bearer header and is not written to repository files or artifacts.
- Research artifacts omit API keys, `departure_token`, `booking_token`, and booking POST data.
- Focused China run used 8 requests.
- Full fixed-basket expanded run used 54 requests before stopping at the J5 open-jaw probe.
- Total SearchAPI research usage in this checkpoint: 62 requests.
- No automatic paid fallback is configured by this repository.

## Focused China evidence

Workflow run: `31404748381` — success
Artifact: `searchapi-china-decision` (`9069132584`)
Observed: 2026-08-10 Asia/Taipei
Requests used: 8

### C1 — TSA ↔ SHA, 2026-10-13 / 2026-10-17

- exact outbound and exact return: yes
- selected Google Flights search price: TWD 16,207
- lowest booking option: China Airlines, CI201 / CI202, TWD 16,690
- baggage text: 1 free checked bag + 1 free carry-on
- immediate same-booking-token retry: booking options returned; same lowest option and same TWD 16,690 price
- FlyAI formal exact flight-number set contains both CI201 and CI202

The SearchAPI search-to-booking gap for this selected itinerary is TWD +483, or about +2.9% relative to the booking-option price. This is provider-layer revalidation evidence, not proof of completed airline checkout.

### C2 — TPE ↔ XMN, 2026-10-13 / 2026-10-17

- exact outbound and exact return: yes
- selected Google Flights search price: TWD 9,941
- lowest booking option: Cathay Pacific, TWD 9,941
- selected flights: CX495 TPE-HKG, CX978 HKG-XMN, CX973 XMN-HKG, CX402 HKG-TPE
- baggage text: 1 free checked bag + 1 free carry-on
- immediate same-booking-token retry: booking options returned; same lowest option and same TWD 9,941 price
- FlyAI formal exact flight-number set contains CX495 and CX978, but not CX973 or CX402

Therefore the focused reference exposes a real FlyAI coverage gap for at least one low-price C2 round-trip itinerary. The formal FlyAI artifact retained per-case flight-number sets rather than full offer grouping, so component overlap must not be called an exact combined-itinerary hit rate.

## Correction to the focused run's embedded comparison field

The executed focused script had a stale hard-coded C2 FlyAI flight-number set. Its SearchAPI booking/search evidence is valid, but the run-produced `flyai_formal_component_hits` and `all_selected_flight_components_seen_in_flyai_formal_set` fields for C2 are discarded. They were recomputed from FlyAI formal artifact `9067758804` as stated above. The script is corrected on this branch without rerunning the eight SearchAPI requests.

## Full round-trip basket partial evidence

Workflow run: `31403752768` — final workflow conclusion **failure** because the research runner reached `SearchAPI error: Google Flights didn't return any results.` at request 54.
Artifact: `searchapi-google-flights-fixed-basket` (`9069072917`).

The failure occurred only after all ten structured round-trip cases J1-J4, K1-K2, C1-C2, S1 and L1 had completed through the booking-option layer. The subsequent J5 multi-city/open-jaw probe did not produce a usable result, so J5 remains unknown and the 54-request run was not repeated.

### Round-trip coverage and booking-layer revalidation

- exact round-trip reference coverage: **10/10** cases produced exact-airport/date outbound and return candidates with a booking token.
- selected candidate booking-option hit: **10/10** cases returned booking options.
- same-booking-token retry returned booking options: **10/10**.
- same lowest booking option was still present: **10/10**.
- same lowest booking-option price: **9/10**.
- J1 was the only price-change case: Jetstar GK12/GK11 changed from TWD 7,822 to TWD 8,182 on immediate revalidation, so this reference's observed stale-by-price rate is **1/10 = 10%**.

This is a stronger reference-layer revalidation signal than repeating a fresh discovery search, but it still does not prove successful airline/OTA checkout.

### Search price to booking-option gap

Across the ten completed round-trip cases, the selected search result versus its first booking-option observation had a median gap of **TWD +441**, with a median relative gap of about **5.16%**. Individual cases varied substantially, including a large C1 expanded-search outlier. These values describe SearchAPI/Google search-to-booking movement only; they are not a FlyAI cross-source price gap.

### FlyAI lowest-reference itinerary coverage bound

For each of the ten Google reference selections, compare the selected itinerary's marketing flight numbers against the union of flight numbers present in FlyAI formal **exact** results for that same fixed-basket case:

- **8/10** selected Google reference itineraries have at least one flight-number component that is absent from the FlyAI formal exact result set, so those eight selected itineraries are definite FlyAI misses in the observed formal snapshot.
- only J2 and K1 have every selected Google flight-number component present somewhere in the FlyAI formal exact set.
- because the FlyAI artifact retained per-case flight-number unions rather than full offer grouping, J2 and K1 cannot be upgraded to proven combined-itinerary hits.

Therefore the exact combined `lowest_verifiable_fare_hit_rate` cannot be recovered from the retained FlyAI artifact, but the evidence places an **upper bound of 20%** on the hit rate for these ten selected Google reference itineraries. This is coverage evidence, not a numeric fare comparison: FlyAI `ticketPrice` still lacks verified currency/tax/baggage semantics.

### LCC evidence

The selected Google reference itineraries containing obvious LCC segments were J1, J3, J4, K1, K2 and S1. Five of those six selections had at least one selected flight-number component absent from the FlyAI formal exact set; K1 was the only selection whose component flight numbers were all present. This **5/6 selected-itinerary miss incidence is a diagnostic proxy, not a true LCC inventory miss rate**. A true LCC miss rate remains unknown because neither this selected-itinerary sample nor the retained FlyAI artifact defines an exhaustive LCC inventory denominator.

### J5

The full run reached a Google Flights no-results error at the J5 open-jaw phase. SearchAPI documents multi-city query support, but this exact fixed-basket observation did not yield a usable J5 combined fare. J5 SearchAPI combined-open-jaw coverage therefore remains **unknown**; do not treat the earlier two one-way FlyAI probes as one combined fare.

## Decision unlocked for Issue #3

The evidence is sufficient to select **FlyAI as the first production adapter for China `deep_search`**, with strict limits:

- it is a primary China deep-search source, not a universal collector;
- exact returned airport/date validation is mandatory;
- missing currency/tax/baggage/fare-family semantics stay unknown;
- FlyAI is **not** selected as a true revalidation source from current evidence;
- combined open-jaw remains unsupported by the tested FlyAI CLI;
- source-router coverage state must expose provider gaps and must not claim full China fare coverage from FlyAI alone;
- the independent reference proves a secondary/final-cross-check layer remains necessary.

This is enough to begin the Issue #3 China-deep router slice and FlyAI adapter while broader World/Japan/Korea source selection and true production revalidation remain open in Issue #2.

## Metrics that remain unknown

- FlyAI cross-source numeric price gap: unknown because FlyAI `ticketPrice` response observed in the formal run has no verified currency/tax/baggage semantics.
- true FlyAI LCC inventory miss rate: unknown; the 5/6 selected-itinerary LCC proxy is not an exhaustive denominator.
- true FlyAI revalidation success/staleness: unknown; repeat search remains only a stability proxy.
- exact FlyAI combined-itinerary lowest-verifiable hit rate: not recoverable from the retained artifact; observed upper bound across the ten selected Google references is 20%.
- J5 combined open-jaw reference result: unknown after the full SearchAPI run returned no result in that phase.
