# Isolated canonical operational TEST — 2026-08-14

## Purpose

The normal daily canonical workflow cannot safely reacquire on 2026-08-14 because a production-soak snapshot already exists on `history/price-observations`. That production state must remain untouched. This harness exists only to perform an explicit end-to-end operational verification without weakening the production one-attempt-per-day guard.

## Isolation contract

The TEST control path is `.github/workflows/canonical-production-radar-test.yml` and is triggered only by a push to `ops/radar-test-request` changing `requests/test-daily.json`.

The request must use schema version 1, mode `isolated_canonical_test`, the current Asia/Taipei date, and refs under both of these prefixes:

- `test/radar-evidence/`
- `test/radar-publication/`

The workflow refuses other refs. In particular, it never writes the TEST claim, snapshot, or recovery bundle to `history/price-observations`, never writes the TEST manifest to `publication/radar-reports`, and never uses `ops/radar-request`.

The isolated evidence ref should start from a real prior history commit so ordinary historical comparison code remains exercised while the current production day's state is absent. The isolated publication ref must be based on a matching presentation state: every inherited publication manifest must reference a snapshot that exists on the isolated evidence ref. Do not copy a newer production publication head onto an older evidence baseline merely because manifests are append-only.

Before inspecting or claiming the day, the TEST workflow builds the inherited publication baseline against the isolated evidence ref. Any presentation/evidence mismatch therefore fails closed before a live acquisition claim is written.

## Code-path fidelity

Isolation is outside the acquisition/runtime boundary. The TEST workflow deliberately reuses the same merged code used by normal canonical production:

1. `cheap_flight_radar.production_publication` baseline preflight
2. `cheap_flight_radar.production_operations inspect`
3. `cheap_flight_radar.production_operations claim`
4. `cheap_flight_radar.production_runtime`
5. `cheap_flight_radar.production_operations stage-success`
6. `cheap_flight_radar.production_operations restore-publication`
7. `cheap_flight_radar.production_publication` recovered-manifest smoke build

The live provider/search/runtime code is not mocked or replaced. A claim is committed before the live provider call. Once acquisition has occurred, any retry sees the same isolated durable guard state and may only recover publication or no-op; it may not perform another acquisition.

## Pages verification without live-page contamination

The TEST workflow explicitly dispatches `.github/workflows/radar-pages-isolated-test.yml` after the isolated active manifest is pushed. That workflow accepts only the two `test/*` ref families above, checks out the current generator from `main`, builds the deterministic Radar site from the isolated evidence and presentation state, and uploads the resulting site artifact.

It has no `pages: write` permission and no `actions/deploy-pages` step. Therefore it verifies the explicit dispatch and Pages-generation boundary without replacing the live GitHub Pages site. The production `radar-pages.yml` workflow is unchanged.

## Verification standard

A TEST is complete only after checking concrete repository and Actions evidence, not merely workflow conclusion:

- control request commit/ref;
- isolated acquisition claim and workflow-run identity;
- exactly one new isolated immutable price-history snapshot;
- matching immutable recovery `run-result.json` and `publication-manifest.json`;
- byte-identical active manifest on the isolated publication ref;
- explicit isolated Radar Pages workflow run and generated site artifact.

The production `ops/radar-request`, `history/price-observations`, `publication/radar-reports`, and live Pages deployment must remain unchanged by this TEST.
