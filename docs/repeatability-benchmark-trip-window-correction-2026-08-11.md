# Repeatability benchmark trip-window correction — 2026-08-11

## Why this correction exists

The four-market direct-Web repeatability benchmark applied `return_windows.max_nights` as though it were a hard eligibility gate. That interpretation conflicts with the existing SSOT and scoring design.

`flight-radar.yaml` explicitly says the route-time return windows are **search windows, not mandatory trip lengths**. The scoring contract says trips below the minimum useful length receive a heavy penalty, trips in the ideal range receive full/near-full credit, and extra days beyond the ideal should not be endlessly rewarded. It does **not** authorize automatic rejection merely because a trip exceeds `max_nights`.

Therefore the benchmark's duration-only exclusions are corrected as follows.

## Correct semantics

- `min_nights`: strong usability guidance; materially too-short trips may be heavily penalized.
- `ideal_nights`: preferred trip-length range for trip-fit scoring.
- `max_nights`: search/budget guidance, **not a hard rejection threshold**.
- A trip longer than the configured search window may still be a usable complete trip and may remain eligible for pure price views; it should receive appropriate trip-fit/efficiency treatment instead of being discarded solely for duration.
- Exact airport, exact dates, complete-trip scope, current price revalidation, required transport components, and verification state remain hard evidence requirements where configured.

## Impact on the 2026-08-11 benchmark

The following prior exclusions must not be justified by trip duration alone:

- **TPE-OKA ~TWD 4,575, 7 nights** — 7 nights is not itself disqualifying. The value still remains a seed because the indexed low did not converge to the reopened current exact route surface.
- **KHH-PVG ~TWD 4,755, 7 nights** — the prior `7 nights > 2–6` rejection was invalid. This becomes a high-priority revalidation seed. It is not retroactively promoted to a current floor because the current exact price must be re-established.
- **KHH-GMP ~TWD 5,175, 16 nights** — duration alone cannot reject it; it requires current exact revalidation and trip-fit/efficiency evaluation.
- **TSA-FOC surfaced 16+ night pairs** — duration alone cannot keep the cell `unknown`; those pairs require proper current revalidation and complete-trip evaluation.
- **TSA-HKG ~TWD 9,349, 8 nights** — an 8-night pair cannot be rejected merely for exceeding a short-haul search window; evidence/usability must be evaluated independently.
- **KHH-DMK ~TWD 5,680, 14 nights** — duration alone cannot reject it; it requires current exact revalidation and trip-fit/efficiency evaluation.

Because several cells/floors were filtered with the wrong hard-window interpretation, the benchmark's reported **11/16 usable-observation yield and affected market floors are provisional** until a corrected revalidation pass is run. The original benchmark remains useful for exact-airport substitution, price divergence, staleness/non-convergence, and acquisition-repeatability evidence.

## China gateway implication

A cheap mainland arrival airport is not limited to a same-city round trip. Under the existing China specialist policy, a low fare into **PVG** may be treated as a gateway and expanded through verified mainland transport, including:

- high-speed rail / rail to another mainland city;
- mainland domestic flight where practical;
- open-jaw exit from another mainland airport back to Taiwan.

For example, a 7-night PVG entry can support Shanghai plus nearby HSR cities, or a wider mainland open-jaw itinerary. The candidate must be normalized using the complete required transport price, total transport time, usable destination time, and verified onward/return components.

## Price-history handling

Do not mutate the already-written immutable benchmark snapshot or manufacture a backfill. The KHH-PVG ~TWD 4,755 observation is retained here as benchmark provenance, but it becomes a current/history observation only after a new radar run re-establishes the exact airport/date/complete-trip/current-price evidence under the corrected semantics.

## Required follow-up

The next targeted repeat-validation pass must:

1. stop using `max_nights` as a hard eligibility gate;
2. re-probe the duration-only rejected cells/seeds above;
3. separately apply current exact-airport/date/complete-trip/revalidation gates;
4. expand serious China gateway seeds into HSR/domestic-flight/open-jaw alternatives;
5. recompute cell yield and market floors from the corrected semantics;
6. preserve the existing ChatGPT-orchestrated architecture; no GitHub cron, persistent crawler, daemon, or queue is introduced by this correction.
