# CFR-SR-B — gflights current-release qualification (2026-08-21)

## Decision

Upgrade the current CFR machine access adapter from `gflights==0.3.0` to `gflights==0.3.1`.

This is an adapter maintenance decision, not an architecture promotion. `gflights` remains an unofficial, replaceable access adapter behind CFR truth/orchestration semantics and remains subject to provider-health, coverage, sticky-429, and fail-closed rules.

## Upstream delta

Current upstream/PyPI release is `0.3.1` (2026-07-23). Upstream describes it as a patch release with no public API change. It repairs request/session fields that had caused live search/offer `ErrorResponse` failures, replays the main-page session cookies used for offer results, and includes dependency security updates.

Upstream release commit: `nas-/google-flights-rs@2b86b0593871ae7d1049c13a809ed72373ac201d`.

## CFR bounded live comparison

Experiment PR: #63 (closed without merge)

Exact experiment head: `f700a3345fda0e191829364d62647d75140db568`

CI run: `32489872400`

Rules held for both versions:

- fixed `CheapFlightRadar/0.1 (+public-research; no-proxy)` user agent;
- `proxy=None`;
- TWD currency / TW country locale;
- no retry;
- no proxy, UA, session, or identity rotation;
- same bounded five-surface basket;
- no canonical/operator/scoped/recovery claim consumption.

### `gflights==0.3.0`

- Flight Deals: complete, 30 rows, first normalized fare TWD 10,067.
- Explore: complete, 110 rows.
- exact + offer: complete, one revalidated result, TWD 9,028.
- cheapest-dates: complete, 28 rows, first normalized fare TWD 7,399.
- open-jaw/multi-city: complete, one revalidated result, TWD 17,283.

### `gflights==0.3.1`

- Flight Deals: complete, 30 rows, first normalized fare TWD 10,067.
- Explore: complete, 87 rows; the separate live runner observed a different current set, which is not treated as a version regression.
- exact + offer: complete, one revalidated result, TWD 9,028.
- cheapest-dates: complete, 28 rows, first normalized fare TWD 7,399.
- open-jaw/multi-city: complete, one revalidated result, TWD 17,283.

No CFR adapter shim was required for `0.3.1`.

## Qualification conclusion

`0.3.1` preserves the CFR adapter contract on the bounded live basket while carrying upstream live-request repair and security maintenance. It is therefore the selected current adapter version.

This evidence does **not** prove permanent provider reliability, worldwide coverage, or a second executable access path. Sticky-rate-limit circuit behavior and fail-closed acquisition semantics remain unchanged. SR-C and SR-D remain separate qualification packages.
