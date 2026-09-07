# Flexible lane offload — 2026-09-07

Issue: #79

## Decision

Keep Google as the semantic/discovery substrate where it is difficult to replace, but remove routine flexible-calendar pressure from the gflights primary client.

Canonical routing after this change:

- Google Flight Deals: destination-free discovery and external anomaly baseline.
- Google Explore: secondary destination-free seeds.
- Conventional known-route exact: Google primary, one-attempt Kiwi MCP fallback only after technical Google failure.
- Flexible calendar selection: Kiwi MCP primary.
- Exact completion of dates selected by the flexible calendar: Kiwi MCP primary.
- Flexible Kiwi technical failure: fail closed; do not automatically call Google.
- Open-jaw / multi-city: Google-only on the reserved multi-city client lane.

Kiwi remains current-fare completion evidence only. It does not become anomaly authority and does not replace Google Flight Deals typical-price truth.

## Why

The canonical production run `34070620741` on 2026-09-07 established a narrower failure shape than a generic bad-runner-IP hypothesis:

- Flight Deals and Explore produced substantial usable records.
- conventional exact work completed before the first observed primary sticky 429.
- the first observed primary sticky 429 occurred on the first `cheapest_dates` call.
- after the sticky state opened, local circuit suppression correctly prevented repeated Google calls.
- the already-qualified Kiwi MCP exact/flexible fallback completed 40/40 fallback attempts without failure in the same run.

The gflights DateGrid path also performs bursty internal calendar work, while Kiwi's qualified MCP flexible call provides a bounded native date-range query. The smallest evidence-aligned repair is therefore to offload the high-pressure flexible lane rather than replace Google wholesale.

## Rejected first-line alternatives

### Playwright / browser automation

Not selected for canonical production. It would add a brittle consumer-UI parser and a browser-automation subsystem, while current CFR policy forbids anti-bot evasion, CAPTCHA bypass, login/member sessions, proxy/UA/session/identity rotation, and crawler/browser-automation substitution for canonical backend truth. Browser automation may be reconsidered only as separately qualified diagnostic/access-adapter research if Google semantic surfaces later become unusable through the current adapter.

### Proxy, user-agent, session or identity rotation

Forbidden. The repair must not turn provider throttling into an evasion problem.

### `reset_rate_limit()` or hidden retries

Forbidden. Sticky 429 remains fail-closed evidence; there is no automatic reset/reacquisition loop.

### Immediate self-hosted fixed egress

Deferred. Shared GitHub-hosted IP reputation may contribute, but the observed run did not fail from its first Google request. The first evidence-backed intervention is to remove the flexible workload that immediately preceded the sticky 429.

## Invariants

- no new provider credentials or paid quota;
- no new destination-free or anomaly authority;
- no silent fallback after healthy empty results;
- conventional exact still exposes Google primary degradation when Kiwi fallback recovers the route;
- flexible lane failure is explicit provider failure evidence;
- open-jaw capability and RP-06 route-shape semantics stay unchanged;
- FTR handoff must retain explicit per-provider execution truth when both gflights and Kiwi execute;
- one-per-day canonical acquisition identity, operator reacquisition identity, sticky-429 circuit and recovery contracts remain unchanged.

## Validation boundary

Code/contract tests and PR CI are required before merge. Live validation must use an already-authorized acquisition identity; it must not fabricate a second canonical daily attempt. A user-requested post-merge production reacquisition uses the existing operator-request contract with a fresh unique request id and must persist its claim before any provider call.
