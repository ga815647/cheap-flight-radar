# Cheap Flight Radar

A price-first travel discovery project for finding unusually cheap, actually usable trips from Taiwan.

The project does **not** start with a fixed destination or fixed trip length. It discovers cheap outbound opportunities first, then constructs viable return/open-jaw itineraries and ranks complete trips by price, travel-time value, usable trip days, and transport efficiency.

## Project entry

1. Read [`AGENTS.md`](AGENTS.md).
2. Treat [`flight-radar.yaml`](flight-radar.yaml) as the machine-readable SSOT for current search policy.
3. Read the focused design notes under [`docs/`](docs/) when changing search, scoring, or China routing behavior.

## Current v0.1 scope

- Rolling 120-day horizon.
- Taiwan origins; global destinations.
- No weekday restriction.
- Outbound one-way discovery first.
- Return search window expands with route duration/distance.
- Round-trip benchmark is retained so split tickets do not hide a cheaper conventional fare.
- Open-jaw itineraries are allowed.
- Domestic flights, rail, bus, and ferries may be used as positioning segments when worthwhile.
- China routing includes direct air plus Kinmen/Matsu ferry gateways when feasible.
- Ranking uses effective total transport price, route value, usable trip days, and transport efficiency.

## Repository layout

```text
.
├── AGENTS.md
├── flight-radar.yaml
├── docs/
│   ├── search-strategy.md
│   ├── scoring.md
│   └── china-routing.md
├── src/cheap_flight_radar/
│   └── scoring.py
├── tests/
│   └── test_scoring.py
└── .github/workflows/
    └── ci.yml
```

## Development rule

Do not silently change travel policy in code. Policy changes land in `flight-radar.yaml` first (and the relevant design note when explanation is needed), then implementation/tests follow.

The first implementation milestone is intentionally small: establish stable policy, scoring primitives, and a test gate before choosing or building fare collectors.
