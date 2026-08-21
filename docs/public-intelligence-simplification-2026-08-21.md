# CFR-SR-F — public-intelligence simplification (2026-08-21)

## Decision

SR-F retires CFR's fixed-watch crawler/cadence/state subsystem. Fixed watches were always optional Signal context rather than Deal/anomaly authority; after substrate reassessment, their marginal recall value does not justify a separate Scrapy/Playwright execution plane, freshness state machine, parser registry, artifacts, and browser plumbing. Public intelligence remains a best-effort opportunistic/verification-only lane controlled by the ChatGPT orchestrator.

## Base-main inventory before SR-F

The fresh pre-SR-F main contained all of the following current executable or policy surfaces:

- `.github/workflows/fixed-watch-run.yml` — on-demand fixed-watch crawler execution and artifact upload.
- `src/cheap_flight_radar/fixed_watch_runner.py` — Scrapy crawler plus optional Playwright path.
- `src/cheap_flight_radar/fixed_watch_state.py` — cadence, prior-success reuse, and manifest state.
- `src/cheap_flight_radar/public_sources.py` — fixed-source parser dispatch/contracts.
- `src/cheap_flight_radar/public_intelligence.py` — fixed-watch registry/planning types mixed with generic provenance/dedupe primitives.
- fixed-watch-only tests and `tests/fixtures/public_sources/`.
- `pyproject.toml` dependencies on Scrapy and optional `scrapy-playwright`.
- `flight-radar.yaml` fixed-watch registry/runtime/cadence policy plus publication requirement `fixed_watch_coverage_and_freshness`.
- `src/cheap_flight_radar/publication.py` dependence on the current fixed-watch registry to render cadence labels.

## KEEP

- `src/cheap_flight_radar/public_intelligence.py` as a small source-agnostic module for `DiscoverySighting`, campaign identity/dedupe, exact-itinerary identity, and observation provenance.
- `src/cheap_flight_radar/secondary_recall.py` and current opportunistic one-way Web-seed expansion.
- Public Web/search/social/news/airline-promotion observations as opportunistic Signal/seed context when useful.
- Candidate-triggered airline/OTA/metasearch verification surfaces.
- Historical immutable manifests: if they contain fixed-watch evidence, publication may render it explicitly as historical evidence.
- All Daily/Scoped provider routing, gflights/Kiwi SR-D behavior, SR-E blind spots, Deal/absolute-low/open-jaw/fail-closed/TWD-0 semantics, and CFR→FTR contract.

## RETIRE

- `.github/workflows/fixed-watch-run.yml`.
- `fixed_watch_runner.py`, `fixed_watch_state.py`, and `public_sources.py`.
- fixed-watch cadence/reuse/manifest/parser contracts and their dedicated tests/fixtures.
- Scrapy and `scrapy-playwright` project dependencies and browser-install path.
- current fixed-watch registry/runtime/cadence policy and the fixed-watch publication coverage requirement.
- publication's dependency on current fixed-watch registry/cadence configuration.

## Final runtime truth

`flight-radar.yaml` now defines public intelligence as `simplified_opportunistic_signal_lane_v2`: only opportunistic and verification-only roles remain. Public-intelligence absence or source failure does not change provider health, does not establish market absence, and cannot become Deal/anomaly/backend coverage authority. Generic provenance/dedupe remains available. Historical docs may describe the retired design but do not override current Product Intent or machine SSOT.

No live airfare/provider acquisition was performed for SR-F. No FTR code/schema/consumer behavior was changed.
