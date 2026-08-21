# AGENTS.md

This file is the required first entry for any ChatGPT/Codex/agent session working on this repository.

## 1. Product intent and source of truth

- `PRODUCT_INTENT.md` is the durable human-level statement of **what the user wants Cheap Flight Radar to achieve and how results should be judged**.
- `flight-radar.yaml` is the **single machine-readable operational source of truth (SSOT)**. It records current implemented travel-search policy and may also record accepted qualified-future capability only when that capability is explicitly state-labelled. A target/future entry does not authorize runtime execution or broader coverage until its qualification gate is completed and the current-runtime state is changed.
- The operational SSOT must evolve to conform to `PRODUCT_INTENT.md`; implementation details must not silently redefine product intent.
- When `PRODUCT_INTENT.md` and current `flight-radar.yaml` conflict, treat that as an explicit policy inconsistency to reconcile in a policy-change branch/PR. Do not silently reinterpret the product intent to preserve legacy behavior, and do not silently bypass the current SSOT at runtime before the policy change is made.
- `docs/*.md` explains reasoning, evidence, and edge cases behind current policy.
- Code implements policy; code must not silently redefine policy.
- Chat history, prompts, and external notes are not authoritative when they conflict with the durable repository sources above.

## 2. Required read order

Before changing behavior:

1. Read this file.
2. Read `PRODUCT_INTENT.md` completely.
3. Read `flight-radar.yaml` completely.
4. Read the relevant design document(s):
   - search/discovery changes → `docs/search-strategy.md`
   - ranking/scoring changes → `docs/scoring.md`
   - China routing → `docs/china-routing.md`
5. Inspect current implementation and tests.

## 3. Product objective

The compact objective is:

> Find **real, abnormally cheap airfare Deals from Taiwan** that are cheap enough to make the user consider destinations they had not already planned to visit.

Do not substitute generic trip-planning quality, absolute-low-fare leaderboards, crawler completeness, historical-model sophistication, or infrastructure elegance for that objective. See `PRODUCT_INTENT.md` for the durable decisions behind this statement.

## 4. Search behavior

Current executable behavior is defined by the current-runtime state in `flight-radar.yaml`; do not rely on a duplicated summary in this file when details matter. Accepted target capability in the SSOT is not executable merely because the product permits or desires it.

General invariants:

- discovery evidence and formal/current Deal evidence are distinct;
- a cheap one-way observation may seed investigation, but a formal Deal requires a concrete complete airfare itinerary under the current policy;
- outbound-first and direct round-trip discovery may coexist;
- open-jaw is a first-class airfare possibility;
- search paths and provider/access adapters are replaceable implementation details, not product intent;
- do not assume a cached/search-result fare is currently purchasable;
- do not turn temporary search horizon, source coverage, compute budget, crawler limitations, or current geographic runtime filters into durable product preferences.

## 5. Evidence rules

For live fare research:

- Prefer reproducible current fare/search evidence and trusted selling channels for formal Deal validation.
- Record source, observed timestamp, currency, fare scope, and enough itinerary identity to distinguish the actual fare being claimed.
- Never invent unavailable fares, schedules, connections, fees, or transport costs.
- When a source exposes only an incomplete or lagged signal, preserve it as signal evidence rather than promoting it to a formal Deal.

## 6. Change workflow

For meaningful repository changes:

1. Create/use a branch; do not develop directly on `main`.
2. If durable user intent changes, update `PRODUCT_INTENT.md` first.
3. If operational policy changes, update `flight-radar.yaml` to conform to the product intent.
4. Update relevant docs.
5. Update implementation.
6. Add/update tests.
7. Run required gates.
8. Open a PR with the exact head commit and a concise explanation of behavioral impact.
9. Do not merge unless explicitly requested by the user.

Exception: the repository's very first initialization commit may exist on `main` solely to create a branchable base.

## 7. Gates

Current minimum gate:

```bash
python -m unittest discover -s tests -v
```

As collectors/data pipelines are added, add deterministic fixture-based tests before relying on live-network tests.

## 8. Design discipline

- Keep discovery, itinerary construction, anomaly/truth evaluation, Deal validation, presentation, and notification policy separable.
- Do not build provider-independent abstractions merely for elegance; prefer the smallest architecture that supports qualified stable sources and required fallback.
- Treat provider/access adapters as replaceable after bounded qualification; provider identity must not redefine Deal, coverage, or CFR→FTR semantics.
- Prefer deterministic normalized records over scraping-page-specific structures when persistence or cross-source comparison requires them.
- Reuse stable external typical-price/anomaly capabilities when qualified instead of rebuilding expensive historical machinery by default.
- Historical price data is supplemental evidence/fallback unless current policy explicitly gives it a stronger role.
- Scoring/ranking must remain explainable and must not hide the underlying anomaly and current airfare evidence.
- Do not ask the user to decide implementation questions that can only be answered by source/tool experiments; measure them first.

## 9. Current non-goals

Current product intent does not require automated booking, exhaustive global fare-matrix coverage, detailed destination itinerary planning, lodging/visa optimization, or guaranteed checkout prices. Worldwide substrate-native discovery is an accepted qualified-future direction, not a claim of current worldwide runtime coverage: Europe, the Americas, Africa, or any other geography may enter production only through separately qualified sustainable TWD-0 capability, while current runtime remains bounded by the implemented scope recorded in `flight-radar.yaml`.
