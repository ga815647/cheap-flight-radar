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

## Executed verification closeout

Final verdict: **PASS after one fail-closed publication recovery; exactly one live airfare acquisition occurred.**

The first control request was commit `efd96a759cbfd1557e9aa8faafc88b14b33888fb` on `ops/radar-test-request`, targeting `test/radar-evidence/opverify-20260814-2210` and `test/radar-publication/opverify-20260814-2210`. It triggered workflow run `31808298502`.

The claim was committed before the provider call as `f4d3f5afe108973c24e84a32414e1893bafac49d`. Its `canonical.json` records Asia/Taipei date `2026-08-14`, trigger SHA `efd96a759cbfd1557e9aa8faafc88b14b33888fb`, and workflow run `31808298502`.

That run invoked the real merged `cheap_flight_radar.production_runtime` once. The live acquisition completed successfully as `production-radar-20260814T221158+0800`; the TEST evidence ref then advanced to `80cd27280b4dc46e24193b77177d4533ece42e59` and remained there for the rest of the verification. The 2026-08-14 TEST price-history directory contains exactly one snapshot:

`data/price-history/2026/08/14/production-radar-20260814T221158-0800.json`

Its Git blob is `163ac072f43ca158c693d0cfd55f39b1a291df08`.

The same evidence commit persisted the immutable recovery bundle:

- `data/run-evidence/2026/08/14/production-radar-20260814T221158+0800/run-result.json`, blob `da33a9270f6cc8567183570991485b0e4511cc77`;
- `data/run-evidence/2026/08/14/production-radar-20260814T221158+0800/publication-manifest.json`, blob `265019ae68d9d28a67830c15ac6306e1b39bb32e`.

The first post-acquisition publication smoke build failed closed because the isolated publication ref had inherited a newer 2026-08-14 production manifest while its evidence baseline deliberately stopped before the production-soak snapshot. No second acquisition was attempted. PR #32 added a publication/evidence baseline preflight before inspect/claim so this class of mismatch is rejected before a future live TEST call.

After aligning only the TEST publication baseline, recovery request commit `fe83c19cd480d78544847173b745e4169add5945` triggered run `31813000840`. Its state was `recover_publication`; the claim, production acquisition, success staging, and history refresh steps were all skipped. It restored the active manifest from immutable recovery evidence, smoke-built successfully, and pushed TEST publication commit `d46daecffff8fc649dd2e002172019190e013d2b`.

The active TEST manifest `publication/runs/production-radar-20260814T221158+0800.json` has Git blob `265019ae68d9d28a67830c15ac6306e1b39bb32e`, exactly matching the immutable recovery `publication-manifest.json` blob. This proves recovery produced a byte-identical active manifest rather than regenerating or reacquiring data.

The recovery workflow explicitly dispatched isolated Radar Pages run `31813027926` at main `71b0dcc5b1e954181da15bbdb3f49da016caf511`. The deterministic site build and artifact upload succeeded. Artifact `9223878409` (`radar-pages-isolated-test-31813027926`) is 55,506 bytes with digest `sha256:55047049e91d31843dabd40a05804b76653007c8083a7feb3e00473bb59f5256`.

Production isolation was rechecked after completion. The formal refs were unchanged from their pre-TEST heads:

- `ops/radar-request` = `977b9b30f0589273408fb73ebba551541e0b7e99`;
- `history/price-observations` = `17de2a23e5eab5fee975becf61746684f790ce42`;
- `publication/radar-reports` = `12126577d6fcb7957d8151c76a291161254bd460`.

The production `radar-pages.yml` workflow received no TEST-time deployment. Its latest run remained `31806010060`, created before this isolated verification. A later control-branch-only workflow-definition sync commit `92050faafd01d610b1972cae1ecb302867f97db3` also triggered zero Actions runs because it did not modify `requests/test-daily.json`.

Therefore the requested chain is verified end to end in isolated state:

`ChatGPT-style control request → durable one-attempt claim → one canonical production acquisition → immutable price-history snapshot → immutable recovery evidence → byte-identical active publication manifest → explicit isolated Radar Pages dispatch/build`

No production daily state or live Pages deployment was polluted, and publication recovery did not cause a second airfare query.
