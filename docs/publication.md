# Radar Publication

## Purpose

Radar publication turns a completed ChatGPT-orchestrated Radar run into a durable, readable static report without turning GitHub Actions into the scheduler or making every daily report a policy/code PR.

The publication layer has three deliberately separate states:

1. **policy/code** on `main` — the generator, templates, SSOT, docs, tests, and deployment workflow;
2. **fare evidence** on `history/price-observations` — immutable per-run exact/current observations used for historical metrics;
3. **presentation manifests** on `publication/radar-reports` — append-only per-run Deals, Signals, coverage/provider failures, and other report-only metadata.

A presentation manifest is not fare evidence. Current fares and comparable historical metrics come from persisted observations; provider-relative anomaly evidence and Signal/Deal classification are preserved explicitly in the run manifest.

## Schema-v2 user-facing model

New production runs are anomaly-first.

The primary user-facing classes are:

- **Deal** — qualified anomaly truth plus a current exact complete airfare;
- **Signal** — useful evidence that has not satisfied the full Deal contract, including weak seeds, qualified anomalies pending exact completion, exact candidates without usable anomaly truth, stale anomalies, and fail-closed provider outcomes.

Formal Deals are ordered only by:

1. relative anomaly strength descending;
2. current complete airfare in TWD ascending.

Trip length, stops, self-transfer, airline, red-eye, lodging, ground transport, and similar preference/friction dimensions do not change formal Deal order.

Google Flight Deals is the first anomaly authority, followed by Google Flights exact price insight, then own immutable price history. Authorities are selected by priority and are never averaged. Own history being sparse does not block a Deal already qualified by a higher-priority external anomaly authority.

The public report does **not** publish a `Best Value` winner.

Legacy `Absolute Cheapest`, `Near-Term Cheapest`, `Best Short Break`, `Unusual Long-Haul Deal`, and similar views may remain available for old schema-v1 runs or as transition/diagnostic material. They do not determine Deal status and may not reorder schema-v2 Deals.

Japan, Korea, China, and other Asia/Oceania remain priority slices of the same shared pipeline rather than independent publication methodologies.

## Run publication sequence

A ChatGPT-orchestrated production Radar run follows this order after current fares have been normalized and revalidated:

1. validate and write exactly one immutable snapshot to `history/price-observations`;
2. read the history snapshots needed for comparison, including the just-persisted current run;
3. derive current-run comparable historical metrics from immutable evidence where enough evidence exists;
4. write one append-only schema-v2 publication manifest to `publication/radar-reports`;
5. the manifest push invokes the disposable Pages build/deploy workflow;
6. the workflow checks out the current generator from `main`, the evidence ref from `history/price-observations`, and the publication manifests from the triggering ref;
7. build the permanent per-run pages plus mutable `latest/` and root index views;
8. upload and deploy the static artifact to GitHub Pages.

The snapshot write comes before the publication manifest. A failed Pages deployment therefore cannot cause a report to exist without its durable fare evidence.

The generator on `main` must already understand the manifest schema before that schema is appended to the live publication ref. During a code/schema rollout, live history may safely be persisted first; publication waits until the compatible generator has merged.

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

Schema-v1 and schema-v2 manifests remain readable so older permanent run pages can be rebuilt after the anomaly-first migration.

Every full build may reconstruct all HTML from scratch. Historical comparison code accepts only observations whose observation time is earlier than the run being rendered, so later market data cannot rewrite an older run's rolling low, baseline, percentile, confidence, or anomaly interpretation. A later template/code change can intentionally change presentation after the normal PR/Gate process.

## Historical evidence shown on pages

For each displayed candidate, show historical evidence only when supported by the SSOT:

- prior all-time comparable low when at least one prior sample exists;
- configured rolling lows with their sample counts when observations exist in those windows;
- selected recent median baseline and the actual baseline window when a configured window has enough samples;
- percent below that selected historical baseline only when the baseline exists;
- historical percentile only when the configured minimum sample threshold is met;
- comparable sample count and confidence on every candidate;
- an explicit sparse-history note when evidence density is none/sparse/low.

Do not synthesize history, impute a missing median window, or display a percentile placeholder that looks numeric when the sample threshold is not met.

These historical fields are supplemental evidence. They do not override a higher-priority provider anomaly authority and do not become a hidden prerequisite for externally qualified Deals.

## Coverage and failure presentation

Every schema-v2 run manifest records operational context that is not naturally part of a fare observation:

- TPE/TSA/RMQ/KHH origin-attempt state;
- Japan / Korea / China / other Asia-Oceania discovery, qualification, exact-revalidation, and Deal counts;
- provider failures;
- weak seeds;
- qualified Flight Deals anomalies that were retained but not selected for exact completion under the current run compute budget;
- exact-revalidated candidates that failed Deal qualification.

A failed or pending seed is not copied into fare history merely so it can be shown on the page. Fare history contains actually observed current fare evidence; presentation/provenance state remains in the manifest.

Fixed-watch observations are Signals only and are not a Deal-coverage authority or publication gate.

## Daily publication versus code changes

Adding a validated history snapshot and a publication manifest is data/report publication. It does not require a PR or merge to `main` once the manifest schema is supported by the merged generator.

Changes to methodology, SSOT, generator code, workflow behavior, templates, or tests remain normal code/spec changes and follow branch → Gate/CI → PR → merge.

## Historical schema-v1 publication

The corrected Radar v1 run from 2026-08-12 remains the first publication fixture and historical live-page format. Its fare observations remain on `history/price-observations`; the repo fixture copies those already-observed values only for deterministic tests and does not create synthetic historical observations.

Schema-v1 pages may still render their original Absolute Cheapest / Near-Term / market-section presentation for historical compatibility. That legacy presentation does not define the schema-v2 Deal model.
