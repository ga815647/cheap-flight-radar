# Cheap Flight Radar — Product Intent

This document captures the user's durable product intent: **what Cheap Flight Radar is supposed to find and how the user wants to judge the results**.

It is intentionally above implementation details. `flight-radar.yaml` remains the single machine-readable operational SSOT, but it should be changed to conform to this intent when the two conflict. Do not reinterpret this document merely to preserve legacy implementation choices.

## 1. Core use case

Cheap Flight Radar exists to find airfare that is unusually cheap enough to make the user consider traveling somewhere they had not planned to visit.

The user does **not** start with a destination preference. The airfare opportunity comes first; the destination decision follows.

The primary product is a set of current, concrete airfare Deals plus a separate daily Signal journal. It is not a generic trip planner and it is not a project for building airfare infrastructure for its own sake.

## 2. Geographic scope

- Production focus: **Asia + Oceania**.
- Japan, Korea, and China are the most important markets to the user.
- Other Asia/Oceania markets are welcome whenever good Deals appear; exhaustive country-by-country coverage is not itself a goal.
- Europe, the Americas, and Africa are out of current scope and are future expansion only.
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
- Do not invent a universal fixed percentage threshold before evidence supports one.
- Seasonal/month-specific normalization is not a current product requirement; do not create fake precision while data is sparse.

## 4. Truth for normal price and anomaly

Prefer reusing qualified external sources that already provide reliable typical-price, discount, or Deal/anomaly judgments.

- A source must be qualified before its anomaly judgment becomes Radar truth.
- Stability and repeatability matter more than theoretical maximum coverage.
- The ability to provide typical price / discount percentage / Deal classification is a high-value source capability.
- Different markets may use different qualified truth sources.
- If qualified sources disagree, use an explicit source priority rather than averaging incompatible judgments.
- If the primary qualified source fails, fall back to the next qualified source.
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
- Keep both discovery paths: outbound-first and direct round-trip scanning.
- Merge duplicate evidence when both paths find the same Deal.
- A strong round-trip Deal may still be expanded into open-jaw alternatives when doing so is practical.

## 7. Open-jaw intent

Open-jaw is a first-class airfare opportunity, not a niche exception.

- Search may pair a cheap arrival city with a cheap departure city across Asia/Oceania.
- Same-city round trip and A-in/B-out alternatives may coexist.
- Large geographic span does **not** automatically disqualify an open-jaw Deal. Distance/span may be shown as context, but the user may still want an unusually cheap Okinawa-in / Hokkaido-out itinerary.
- Radar does not need to prove detailed ground transport between the two cities in order to show the airfare combination.
- Radar may add a coarse human-readable comment about whether a cross-city combination looks ordinary, unusual, or very spread out, but it is not responsible for planning the trip between cities.
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

- Routine automation should run the Radar about **once per day** for now; no immediate-alert requirement. This is a scheduling preference, not a prohibition on an explicit same-day operator-requested reacquisition when the user wants refreshed evidence, diagnosis, or a provider-health comparison.
- An operator-requested same-day reacquisition must be explicitly identified and append immutable evidence. It must not weaken duplicate protection for the routine daily trigger, silently retry a failed automatic run, or overwrite the canonical daily observation.
- Production should be sustainable at **ongoing TWD 0**: free public Web, free/open-source tooling, or APIs whose recurring free quota is actually sufficient for normal daily Radar use.
- Paid APIs, expiring trial credits, or unknown/inadequate free quotas are not production-core dependencies.
- Search should favor recall when free/stable resources permit: finding more legitimate possibilities is better than artificially optimizing for a very short runtime.
- Exact coverage depth, brute-force breadth, crawler design, API allocation, and execution budget are implementation questions to be decided after measuring available substrates. Do not turn temporary implementation limits into product intent.

## 12. Seller trust

- Airline official sales channels are trusted.
- OTAs used for formal Deals should come from a maintained trusted allowlist; an unfamiliar small OTA is not sufficient for a formal Deal even if its displayed fare is lower.
- Metasearch engines are valid discovery/verification surfaces when the final selling channel is trusted and the fare can be reproduced.
- Only use prices Radar can actually obtain/reproduce. Do not guess hidden app-only/member-only prices or checkout-only fees that the system cannot observe.
- If a mandatory fee is observable in the reproducible price path, include it; if it is not observable, do not invent it.

## 13. History and continuity

- A Deal that disappears from today's live dashboard may remain in historical records as evidence that the price existed.
- A Deal that remains available across multiple days is the same continuing Deal, not a brand-new Deal every day; record its price/status evolution.

## 14. Interpretation rule

When deciding future architecture or policy, ask first:

> Does this choice help Radar find more **real, abnormally cheap airfare Deals from Taiwan** with less long-term cost and unnecessary complexity?

If a crawler rule, scoring rule, transport model, source-coverage requirement, or historical-model requirement does not serve that product goal, it is a candidate for simplification or removal.

Do not ask the user to decide implementation questions that can only be answered after source/tool experimentation. Measure first, then propose the smallest policy necessary.
