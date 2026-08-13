# Destination-airport anomaly normalization correction — 2026-08-13

## Why this correction exists

The first formal production publication exposed a concrete false-positive risk in origin-specific Google Flight Deals typical prices.

For the same destination airport `CJU` in the same Radar run, retained evidence included:

- `TSA → CJU`: exact revalidated complete airfare TWD 17,639; Flight Deals typical TWD 63,237; provider discount about 72%.
- `RMQ → CJU`: Flight Deals complete airfare TWD 9,023; Flight Deals typical TWD 11,576; provider discount about 22%; retained as a pending exact Signal because the old exact budget prioritized the larger origin-specific percentage anomaly.

The old runtime therefore selected the **more expensive** TSA itinerary and treated TWD 63,237 as the comparison normal, producing a misleading #2 Deal. This was not repository historical price evidence; it was an origin-specific provider typical that was inappropriate for the user's destination-first question.

## Corrected semantics

For airfare anomaly interpretation, the primary unit is now the **exact destination airport**, pooled across the configured Taiwan origins `TPE`, `TSA`, `RMQ`, and `KHH`.

- Every fare observation and published ticket retains its actual Taiwan origin.
- Before exact revalidation, Radar keeps the lowest current complete airfare found for each exact destination airport across the configured Taiwan origins.
- Google Flight Deals typical-price evidence for that destination is pooled conservatively by taking the **lowest qualified typical price** seen for the same destination airport across those Taiwan origins in the current sweep.
- An expensive origin-specific typical must not override a lower same-destination typical and manufacture a false anomaly.
- Repository history uses the same destination-airport comparison scope: origin remains provenance, while each Radar run contributes at most one comparable sample per destination airport + trip type + lead-time bucket, using that run's lowest available complete airfare across the accepted Taiwan origins.
- City/metro grouping remains a presentation layer above this airport-level truth; it does not replace exact destination-airport fare identity.

Under the corrected CJU regression fixture, Radar selects `RMQ → CJU` at TWD 9,023 and uses TWD 11,576 as the destination baseline instead of promoting `TSA → CJU` from the TWD 63,237 origin-specific typical.

## Historical evidence note

Earlier immutable run artifacts and documentation retain the original provider values as evidence of what the system observed. They are not rewritten. New schema-v2 items expose the selected anomaly baseline and anomaly scope explicitly; older v2 manifests without those fields are rendered as `Provider typical (legacy)` rather than being mislabeled as a destination baseline.
