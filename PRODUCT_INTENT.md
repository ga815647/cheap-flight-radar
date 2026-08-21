# Cheap Flight Radar — Product Intent

This document captures the user's durable product intent: **what Cheap Flight Radar is supposed to find and how the user wants to judge the results**.

It is intentionally above implementation details. `flight-radar.yaml` remains the single machine-readable operational SSOT, but it should be changed to conform to this intent when the two conflict. Do not reinterpret this document merely to preserve legacy implementation choices.

## 1. Core use case

Cheap Flight Radar exists to find airfare that is unusually cheap enough to make the user consider traveling somewhere they had not planned to visit.

The user does **not** start with a destination preference. The airfare opportunity comes first; the destination decision follows.

CFR has two legitimate product modes:

- **Daily Radar** — autonomously discover unusually cheap airfare from Taiwan, roughly once per day, without requiring the user to supply a destination or manually search.
- **Query / Scoped Mode** — given one or more user-supplied availability windows, autonomously find where airfare is cheap within those windows.

The primary product is a set of current, concrete airfare Deals plus a separate daily Signal journal. Exact absolute-low airfare may also be retained as a separate non-Deal result class where useful, including for downstream FTR. It is not a generic trip planner and it is not a project for building airfare infrastructure for its own sake.

## 2. Geographic scope

- Japan, Korea, and China are the most important priority markets to the user.
- **Asia + Oceania is not a permanent product ceiling.** It reflects earlier implementation/resource constraints.
- Broader worldwide destination-free discovery is desired when qualified, stable, sustainable TWD-0 substrates make it practical without a custom combinatorial search explosion.
- Broad substrate capability does not imply exhaustive global fare coverage. Radar must report the origins/surfaces/geographic slices it actually attempted and must not imply that unobserved markets or fare classes contain no cheaper fare.
- Taiwan departure airports are treated equally for Deal ranking. Do not penalize a Deal because it departs from TPE, TSA, RMQ, or KHH.

## 3. What counts as cheap

The project is primarily looking for **abnormally cheap airfare**, not merely the lowest absolute ticket price.

- Compare a destination against its own normal price level rather than comparing unrelated destinations by raw fare alone.
- The primary airfare-anomaly normalization unit is the **exact destination airport**, pooled across the accepted Taiwan origins TPE, TSA, RMQ, and KHH. The ticket itself always retains its actual origin, but an origin-specific normal price must not make an otherwise ordinary destination look exceptionally cheap when another accepted Taiwan origin has a materially lower normal price to the same destination airport.
- For the same destination airport, prefer the **lowest current complete airfare across accepted Taiwan origins** before deciding which concrete origin/date itinerary deserves scarce exact revalidation and publication.
- City-level Deals are the primary actionable unit because tickets are actually bought to/from cities. Country-level cheapness may be shown as a useful parallel/background view.
- Airports serving the same city may be treated as one city Deal for anomaly interpretation.
- When anomaly strength is similar, lower actual total airfare is preferred.
- A large percentage drop is more important than a merely low absolute fare. A normally cheap route that is only slightly cheaper than usual is less interesting than a materially discounted route.
- **Absolute-low current airfare remains useful even when it is not anomaly-qualified.** Keep it semantically separate from a formal Deal rather than weakening Deal truth; bounded exact/revalidated absolute-low non-Deals may be surfaced where useful and may be handed to FTR.
- Do not invent a universal fixed percentage threshold before evidence supports one.
- Seasonal/month-specific normalization is not a current product requirement; do not create fake precision while data is sparse.

## 4. Truth for normal price and anomaly

Prefer reusing qualified external sources that already provide reliable typical-price, discount, or Deal/anomaly judgments.

- A source must be qualified before its anomaly judgment becomes Radar truth.
- Stability and repeatability matter more than theoretical maximum coverage.
- The ability to provide typical price / discount percentage / Deal classification is a high-value source capability.
- Different markets may use different qualified truth sources.
- If qualified sources disagree, use an explicit source priority rather than averaging incompatible judgments.
- If the primary qualified source fails, fall back to the next qualified **and currently executable** source when one exists; otherwise fail closed and expose the missing/degraded coverage.
- Radar's own accumulated history is useful as supplemental evidence and fallback; the product does not need to reinvent a complete airfare-history business when a reliable external truth source already exists.

## 5. Deal versus Signal

### Deal

A formal Deal must converge to a concrete, currently reproducible airfare itinerary:

- 1 adult;
- economy class;
- exact travel dates;
- identifiable itinerary with sufficient flight/airport/time identity to show that a real itinerary exists;
- current complete outbound + return airfare total;
- fare obtained from a public/reproducible surface available to Radar;
- seller is an airline official channel or a trusted OTA; a metasearch result is acceptable when the final selling source is trusted and the price matches.

A Deal is about **airfare**. Visa difficulty, lodging cost, destination cost of living, airline brand, red-eye timing, number of connections, and self-transfer do not determine whether the airfare is a Deal.

Baggage matters to the user but should not complicate Deal ranking for now; show the observed baggage condition when available instead of scoring it.

### Signal

Promotions, social posts, cached/lagged fare hints, suspiciously low one-way prices, incomplete returns, or other promising but unconverged evidence belong in a separate **daily Signal journal**.

Signals do not participate in Deal ranking. Their purpose is to preserve useful intelligence and future follow-up without pretending that an airfare has already been proven.

## 6. Complete airfare and search paths

A very cheap one-way fare may trigger investigation, but a formal Deal is judged on the **complete outbound + return airfare** relative to the destination's normal complete-trip price.

- The return leg does not itself need to be anomalously cheap.
- Outbound-first, direct round-trip, flexible-date, destination-free Deal discovery, external agent search, or other qualified paths are implementation choices. **No particular search path is product intent or must be preserved when a mature borrowed substrate performs the commodity search better.**
- Merge duplicate evidence when multiple paths find the same Deal.
- A strong round-trip Deal may still be expanded into open-jaw alternatives when doing so is practical.

## 7. Open-jaw intent

Open-jaw is a first-class airfare opportunity, not a niche exception.

- Search may pair a cheap arrival city with a cheap departure city across the currently supported/attempted geography.
- Same-city round trip and A-in/B-out alternatives may coexist.
- Large geographic span does **not** automatically disqualify an open-jaw Deal. Distance/span may be shown as context, but the user may still want an unusually cheap Okinawa-in / Hokkaido-out itinerary.
- Radar does not need to prove detailed ground transport between the two cities in order to show the airfare combination.
- Radar may add a coarse human-readable comment about whether a cross-city combination looks ordinary, unusual, or very spread out, but it is not responsible for planning the trip between cities.
- CFR should prefer borrowing mature multi-city/open-jaw capability when it is reliable rather than brute-forcing combinations merely because custom code can do so.
- Ferry gateway constructions are out of the current product direction. Non-air transport is not part of the definition of airfare cheapness; rail may be mentioned only as optional context, not required Deal pricing.

## 8. Trip duration and dates

- Minimum destination stay: **more than 24 hours**, measured simply from arrival to departure clock time.
- Do not reward shorter trips merely for being shorter.
- Use a destination-appropriate upper stay limit only as a practical filter; the limit is not a ranking factor.
- Extremely abnormal airfare may be shown even when it deserves an exception to the normal upper stay limit.
- China can be short or long; do not assume China trips should be long.
- Weekday/weekend/holiday and departure imminence are not ranking preferences. Show the Deal and let the user decide whether the dates work.
- A 120-day horizon is an implementation/search-budget choice, **not** a durable product boundary. Search farther when stable free sources/resources make that practical.

## 9. Ranking intent

Across different city Deals:

1. prioritize **degree of airfare abnormality** (primarily percentage discount / equivalent qualified anomaly signal);
2. when abnormality is comparable, prefer lower complete airfare;
3. do not let connection count, self-transfer, airline brand, red-eye timing, visa, lodging, or destination living costs alter the Deal ranking.

Pure long connection waiting may be called out negatively in commentary; a long connection that can be used as a stopover should not be penalized merely because it is long.

Do not force one opaque "Best Value" score to replace the underlying price/anomaly evidence.

## 10. Deal grouping and presentation intent

- A broad promotion may create many valid date combinations; that does not make it less of a Deal.
- Group many related date combinations into one Deal/campaign rather than exploding the dashboard into one Deal per date pair.
- Within one Deal, keep the cheapest price tier and list similar-priced valid date combinations in a table ordered by date.
- If materially different price tiers exist for the same city/campaign, the dashboard should normally keep the cheapest Deal rather than creating multiple near-duplicate Deal cards.
- Across different cities, order Deals by abnormality.
- A flexible geographic dashboard is useful (broad region → countries/cities), but geographic taxonomy is presentation, not the source of fare truth.
- Each Deal may include short Radar commentary explaining why it is interesting and, where useful, a simple airfare-oriented suggestion such as "Kyoto/Osaka area in, Kobe out is unusually cheap".
- Country/region daily commentary may summarize where the market is cheap, ordinary, or only showing Signals.
- The dashboard may be sparse or empty on a day with no meaningful Deals. Do not manufacture ordinary fares just to fill space.

## 11. Operational preferences that are genuinely product-level

- Routine automation should run the Daily Radar about **once per day** for now; no immediate-alert requirement. This is a scheduling preference, not a prohibition on an explicit same-day operator-requested reacquisition when the user wants refreshed evidence, diagnosis, or a provider-health comparison.
- Query / Scoped Mode is a first-class on-demand acquisition mode over supplied availability windows. It must retain separate provenance/coverage from the canonical Daily Radar and must not silently substitute a broad-horizon search followed only by result filtering when the supplied windows were not actually queried.
- An operator-requested same-day reacquisition must be explicitly identified and append immutable evidence. It must not weaken duplicate protection for the routine daily trigger, silently retry a failed automatic run, or overwrite the canonical daily observation.
- Provider/acquisition health is determined from technical execution and coverage evidence, **never from Deal count**. A partially degraded run may still publish already exact-revalidated valid Deals, but a broad provider/coverage collapse must be visibly distinct from a healthy zero-Deal market result.
- Scheduled notification decisions happen only after the workflow reaches a terminal state and ChatGPT reads the final immutable run evidence. Meaningful new Deals and operational/provider/coverage failures notify; a healthy routine run with no meaningful change may stay silent. A UI notification toggle is only a delivery mechanism, not product policy.
- Production should be sustainable at **ongoing TWD 0**: free public Web, free/open-source tooling, or APIs whose recurring free quota is actually sufficient for normal daily Radar use.
- Paid APIs, expiring trial credits, or unknown/inadequate free quotas are not production-core dependencies without explicit owner approval.
- Search should favor recall when free/stable resources permit: finding more legitimate possibilities is better than artificially optimizing for a very short runtime.
- Exact coverage depth, brute-force breadth, crawler design, API allocation, and execution budget are implementation questions to be decided after measuring available substrates. Do not turn temporary implementation limits into product intent.

## 12. Seller trust and access blind spots

- Airline official sales channels are trusted.
- OTAs used for formal Deals should come from a maintained trusted allowlist; an unfamiliar small OTA is not sufficient for a formal Deal even if its displayed fare is lower.
- Metasearch engines are valid discovery/verification surfaces when the final selling channel is trusted and the fare can be reproduced.
- Only use prices Radar can actually obtain/reproduce for formal Deal or exact absolute-low truth. Do not guess hidden app-only/member-only prices or checkout-only fees that the system cannot observe.
- **Never infer `Radar cannot access a fare -> the fare does not exist`.** App-only, member-only, logged-in, subscription, market-specific or other restricted fare classes may contain real lower fares outside Radar's authorized automatic observation path.
- Coverage must distinguish at least the concepts `fare exists`, `surface shows fare`, `Radar can automatically observe fare`, `Radar can reproduce exact fare`, and `Radar may treat the fare as formal Deal truth`.
- When a restricted fare class is known but its exact current price is inaccessible, record the access blind spot/source class when useful instead of treating the public observation as proof of the market's absolute cheapest fare.
- Restricted or inaccessible hints may remain Signals. They are not formal Deals or exact absolute-low candidates until Radar obtains authorized exact/reproducible evidence.
- If a mandatory fee is observable in the reproducible price path, include it; if it is not observable, do not invent it.

## 13. History and continuity

- A Deal that disappears from today's live dashboard may remain in historical records as evidence that the price existed.
- A Deal that remains available across multiple days is the same continuing Deal, not a brand-new Deal every day; record its price/status evolution.

## 14. Interpretation rule

When deciding future architecture or policy, ask first:

> Does this choice help Radar find more **real, abnormally cheap airfare Deals from Taiwan** with less long-term cost and unnecessary complexity?

Prefer mature external capability for commodity airfare search when it is reliable, sustainable, and compatible with CFR truth requirements. Build custom search capability only when qualified external substrates are insufficient/inaccessible or when the capability itself is part of CFR's differentiated product value.

If a crawler rule, scoring rule, transport model, source-coverage requirement, or historical-model requirement does not serve that product goal, it is a candidate for simplification or removal.

Do not ask the user to decide implementation questions that can only be answered after source/tool experimentation. Measure first, then propose the smallest policy necessary.

## 15. Downstream Family Trip Radar handoff

Cheap Flight Radar is the airfare producer for Family Trip Radar (FTR), but the two products keep separate ranking semantics. CFR continues to decide airfare Deal truth from airfare evidence; FTR decides whole-trip worth after adding home access, lodging, usable time, child fit and other travel factors.

- CFR should publish a compact, machine-readable downstream feed from terminal acquisition evidence instead of requiring FTR to scrape CFR presentation output or depend on chat/project memory.
- The downstream feed contains formal CFR Deals plus a **bounded, explicitly selected absolute-low non-Deal airfare set**. A generic Signal is never silently promoted into that absolute-low set merely because it has a low-looking price.
- Every downstream airfare variant retains exact dates, complete airfare, actual Taiwan outbound/return gateway, destination-side route shape, observed time, verification/evidence references and whether it came from Deal or absolute-low selection. CFR anomaly score/classification remains provenance; it is not FTR's travel-value score.
- Canonical handoff evidence is immutable and Git-backed. A mutable latest manifest may advance only after a terminal, schema-valid, consumable snapshot has been written and checksummed. Failed production must preserve the previous last-good manifest rather than synthesize or overwrite it.
- A truthfully partial run may publish degraded coverage when fresh usable evidence survives. Broad provider/coverage collapse must not masquerade as a healthy fresh snapshot.
- Explicit Search-mode/scoped acquisitions and same-day recovery acquisitions use separate provenance modes. Scoped search evidence never overwrites canonical daily latest; successful same-day recovery may advance canonical latest after proving fresh health.
- Geographic/provider coverage in the handoff is attempted execution truth, not a claim that all worldwide or restricted fare space was searched.
- GitHub Actions artifacts are **optional debug convenience only**, never a correctness or handoff dependency. Artifact quota exhaustion must not prevent acquisition evidence, canonical manifest publication, or downstream FTR consumption.
- The producer contract is versioned. Breaking field/meaning changes require a schema-major change; consumers fail closed on unsupported major versions, missing snapshots, checksum mismatch, or non-terminal producer state.
