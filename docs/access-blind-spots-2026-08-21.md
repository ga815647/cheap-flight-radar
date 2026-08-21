# CFR-SR-E — typed access-blind-spot evidence (2026-08-21)

## Purpose

CFR must never convert an access limitation into a market claim. `Radar cannot access a fare` does not mean `the fare does not exist`, and a known restricted surface does not prove that a particular hidden fare currently exists.

SR-E adds a small CFR-side coverage schema that keeps those propositions separate without creating prices or candidates.

## Typed distinctions

Each registered blind spot records independently:

- `surface_class_existence`: whether the restricted surface/source class itself is known;
- `specific_fare_existence`: whether a particular fare is actually known to exist, or remains unknown;
- `visibility`: public/restricted/unknown;
- `access_gate`: the restriction class such as app-only or member login;
- `automatic_observation`: whether CFR can automatically observe the fare class;
- `exact_reproducibility`: whether CFR can reproduce an exact fare;
- `formal_truth_eligibility`: whether the evidence may become Deal/exact absolute-low truth;
- `price_observability`: whether a current price is observable;
- `evidence_reference`: durable provenance for why the blind spot is known.

Hidden price fields are forbidden in blind-spot registry entries. If the price is inaccessible, the schema carries no amount.

## Initial evidence-backed registry entry

Phase-1 Travel Stack Reassessment established Expedia's app-only Flight Deals surface as a restricted benchmark/blind spot rather than a public automatic fallback. SR-E therefore registers only the **surface class**, with:

- surface class: known;
- specific current fare existence: unknown;
- visibility: restricted;
- access gate: app-only;
- automatic observation: unavailable;
- exact reproducibility: unavailable;
- formal truth eligibility: ineligible;
- price observability: unavailable.

This entry does not claim any Expedia app fare exists for a specific route/date and contains no hidden price.

## Runtime behavior

Canonical runs serialize the normalized registry under `coverage.access_blind_spots`. Because the current registry is informational and no restricted surface is a required coverage slice, it does not change provider health, Deal count, candidate selection, or acquisition behavior.

The immutable publication/run evidence already serializes `coverage`, so no parallel artifact or new FTR schema is required. SR-E changes no FTR code and does not promote blind spots into Signals, Deals or exact absolute-low candidates.
