# AGENTS.md

This file is the required first entry for any ChatGPT/Codex/agent session working on this repository.

## 1. Source of truth

- `flight-radar.yaml` is the **single machine-readable source of truth (SSOT)** for current travel-search policy.
- `docs/*.md` explains the reasoning and edge cases behind that policy.
- Code implements policy; code must not silently redefine policy.
- Chat history, prompts, and external notes are not authoritative when they conflict with the repository.

## 2. Required read order

Before changing behavior:

1. Read this file.
2. Read the complete `flight-radar.yaml`.
3. Read the relevant design document(s):
   - search/discovery changes → `docs/search-strategy.md`
   - ranking/scoring changes → `docs/scoring.md`
   - China / Kinmen / Matsu routing → `docs/china-routing.md`
4. Inspect current implementation and tests.

## 3. Product objective

Find unusually cheap **complete, usable trips from Taiwan**, rather than merely finding the lowest displayed airfare.

A good result balances:

- effective total transport price,
- travel time / distance value,
- usable destination time,
- transport efficiency,
- practical routing.

Absolute low price remains a first-class view. Long-haul deals must not crowd out excellent short-haul 2–3 day trips, and short-haul fares must not hide unusually cheap long-haul opportunities.

## 4. Search behavior

- Default horizon: rolling 120 days.
- Default origin scope: Taiwan airports defined in `flight-radar.yaml`.
- Destination scope: global.
- No weekday restriction unless the SSOT explicitly changes.
- Discovery is outbound-one-way-first.
- Deep search is conditional: cheap outbound candidates are expanded into returns/open-jaw alternatives.
- Always retain a conventional round-trip benchmark when possible.
- Mixed transport is allowed where policy permits: air, rail, bus, ferry.
- Do not assume a cached/search-result fare is bookable. Mark discovery prices separately from verified/bookable prices.

## 5. Evidence rules

For live fare research:

- Prefer current public fare/search sources and official carrier/transport sources for final validation.
- Record source, observed timestamp, currency, fare scope, baggage assumptions, and whether the price was discovery-only or revalidated.
- Never invent unavailable fares, schedules, connections, or transport costs.
- If a route component cannot be verified, mark it unknown rather than filling a plausible value.

## 6. Change workflow

For meaningful repository changes:

1. Create/use a branch; do not develop directly on `main`.
2. Change `flight-radar.yaml` first when policy changes.
3. Update relevant docs.
4. Update implementation.
5. Add/update tests.
6. Run required gates.
7. Open a PR with the exact head commit and a concise explanation of behavioral impact.
8. Do not merge unless explicitly requested by the user.

Exception: the repository's very first initialization commit may exist on `main` solely to create a branchable base.

## 7. Gates

Current minimum gate:

```bash
python -m unittest discover -s tests -v
```

As collectors/data pipelines are added, add deterministic fixture-based tests before relying on live-network tests.

## 8. Design discipline

- Keep discovery, itinerary construction, scoring, and notification policy separable.
- Avoid provider-specific assumptions in the core scoring model.
- Prefer deterministic normalized records over scraping-page-specific structures.
- Historical price data is valuable evidence but does not overwrite the current SSOT.
- Treat scoring weights as calibratable parameters; preserve raw component scores so rankings are explainable.

## 9. Current non-goals

v0.1 does not promise exhaustive fare-matrix coverage, automated booking, CAPTCHA bypass, or guaranteed checkout prices.
