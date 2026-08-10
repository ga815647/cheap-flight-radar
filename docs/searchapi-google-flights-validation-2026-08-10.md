# SearchAPI Google Flights validation — 2026-08-10

Status: Issue #2 credentialed reference evidence; not a production Google Flights collector decision.

## Purpose

Use SearchAPI.io's structured Google Flights API as a limited independent benchmark/revalidation reference while the project lacks a zero-cost Skyscanner/Duffel live credential. This does not promote a Google Flights scraper or SearchAPI itself into the production source router.

## Credential and safety

- GitHub Actions secret: `SEARCHAPI_API_KEY`.
- Secret is passed through the Authorization bearer header and is not written to repository files or artifacts.
- Research artifacts omit API keys, `departure_token`, `booking_token`, and booking POST data.
- Focused China run used 8 requests.
- Full fixed-basket expanded run is separately budget-capped at 60 requests; no automatic paid fallback is configured by this repository.

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

## Decision unlocked for Issue #3

The evidence is sufficient to select **FlyAI as the first production adapter for China `deep_search`**, with strict limits:

- it is a primary China deep-search source, not a universal collector;
- exact returned airport/date validation is mandatory;
- missing currency/tax/baggage/fare-family semantics stay unknown;
- FlyAI is **not** selected as a true revalidation source from current evidence;
- combined open-jaw remains unsupported by the tested FlyAI CLI;
- source-router coverage state must expose provider gaps and must not claim full China fare coverage from FlyAI alone;
- the C2 reference proves a secondary/final-cross-check layer remains necessary.

This is enough to begin the Issue #3 China-deep router slice and FlyAI adapter while broader World/Japan/Korea source selection and true production revalidation remain open in Issue #2.

## Metrics that remain unknown

- FlyAI cross-source numeric price gap: unknown because FlyAI `ticketPrice` response observed in the formal run has no verified currency/tax/baggage semantics.
- true FlyAI LCC miss rate: unknown; this focused reference is not an exhaustive inventory denominator.
- true FlyAI revalidation success/staleness: unknown; repeat search remains only a stability proxy.
- exact combined-itinerary lowest-verifiable hit rate across the whole basket: pending the full SearchAPI reference run and still constrained by the FlyAI formal artifact's lack of per-offer grouping.
