# Radar Publication

## Purpose

Radar publication turns a completed ChatGPT-orchestrated Radar run into a durable, readable static report without turning GitHub Actions into the scheduler or making every daily report a policy/code PR.

The publication layer has three deliberately separate states:

1. **policy/code** on `main` — the generator, templates, SSOT, docs, tests, and deployment workflow;
2. **fare evidence** on `history/price-observations` — immutable per-run observation snapshots used for historical metrics;
3. **presentation manifests** on `publication/radar-reports` — append-only per-run selections, failed seeds, coverage/freshness state, and other report-only metadata.

A presentation manifest is not fare evidence. It may select which already-observed candidate appears in Best Short Break or a market section, but prices, baselines, rolling lows, percentiles, and confidence are derived from history snapshots.

## User-facing views

The public report does **not** publish a `Best Value` winner.

Required top-level live views are:

- Absolute Cheapest;
- Near-Term Cheapest;
- Best Short Break;
- Unusual Long-Haul Deal.

The existing composite score may remain as an internal candidate-ordering heuristic while search is deciding which candidates deserve deeper work. It must not be presented as a user-facing Best Value winner or as a hidden replacement for the explicit views above.

Dedicated Japan, Korea, China, and World notable-candidate sections remain visible. A section may explicitly say that no candidate converged; absence must not be filled with an inferred or stale fare.

## Run publication sequence

A scheduled ChatGPT Radar run follows this order after current fares have been normalized and revalidated:

1. validate and write exactly one immutable snapshot to `history/price-observations`;
2. read the history snapshots needed for comparison, including the just-persisted current run;
3. derive current-run floors and historical metrics from immutable evidence;
4. write one append-only publication manifest to `publication/radar-reports`;
5. the manifest push invokes the disposable Pages build/deploy workflow;
6. the workflow checks out the current generator from `main`, the evidence ref from `history/price-observations`, and the publication manifests from the triggering ref;
7. build the permanent per-run pages plus mutable `latest/` and root index views;
8. upload and deploy the static artifact to GitHub Pages.

The snapshot write comes before the publication manifest. A failed Pages deployment therefore cannot cause a report to exist without its durable fare evidence.

There is no GitHub cron. ChatGPT scheduling remains the primary scheduler/orchestrator. A push-triggered deployment after ChatGPT writes a publication manifest is an execution consequence of that run, not an independent Radar schedule.

## Static site contract

The generator is deterministic. Its inputs are:

- `flight-radar.yaml` from `main`;
- every immutable price-history snapshot needed for comparison;
- append-only publication manifests.

Output paths are:

- `/runs/{radar_run_id}/` — permanent run page;
- `/latest/` — copy of the latest generated run page;
- `/` — run index.

Every full build may reconstruct all HTML from scratch. Historical comparison code accepts only observations whose observation time is earlier than the run being rendered, so a fare discovered tomorrow cannot change yesterday's rolling low, baseline, percentile, confidence, or anomaly evidence. This is tested explicitly. A later template/code change can intentionally change presentation after the normal PR/Gate process, but later market data alone cannot rewrite an older run's historical meaning.

## Historical evidence shown on pages

For each displayed candidate, show evidence only when supported by the SSOT:

- prior all-time comparable low when at least one prior sample exists;
- configured rolling lows with their sample counts when observations exist in those windows;
- selected recent median baseline and the actual baseline window when a configured window has enough samples;
- percent below that selected baseline only when the baseline exists;
- historical percentile only when the configured minimum sample threshold is met;
- comparable sample count and confidence on every candidate;
- an explicit sparse-history note when evidence density is none/sparse/low.

Do not synthesize history, impute a missing median window, or display a percentile placeholder that looks numeric when the sample threshold is not met.

## Coverage and failure presentation

Every run manifest records presentation-only operational context that is not naturally part of a fare observation:

- TPE/TSA/RMQ/KHH origin-attempt state;
- fixed-watch run coverage and each source's freshness state;
- China-mode coverage for direct air, Kinmen, and Matsu when the China specialist was active;
- failed/non-converged cheap seeds and the reason they were not promoted.

The generator also reads fixed-watch cadence thresholds from the SSOT so the page can explain the configured freshness requirement without copying cadence policy into every manifest.

A failed seed is not copied into fare history merely so it can be shown on the page. It remains presentation/provenance evidence that a low signal was investigated and failed to converge.

## Daily publication versus code changes

Adding a validated history snapshot and a publication manifest is data/report publication. It does not require a PR or merge to `main`.

Changes to methodology, SSOT, generator code, workflow behavior, templates, or tests remain normal code/spec changes and follow branch → Gate/CI → PR → merge.

## First reproducible publication

The corrected Radar v1 run from 2026-08-12 is the first publication fixture and first intended live page. Its fare observations remain on `history/price-observations`; the repo fixture copies those already-observed values only for deterministic tests and does not create synthetic historical observations.

The run's publication manifest records the corrected report selections, failed low seeds, incomplete fixed-watch freshness, and partial China specialist coverage documented in Issue #10. Historical metrics for the live page are still derived from the durable history ref at build time.
