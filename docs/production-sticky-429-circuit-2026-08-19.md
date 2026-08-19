# Production sticky-429 circuit hardening — 2026-08-19

## Scope

This is a narrow operational follow-up to the explicit operator reacquisition after PR #34. It does not reopen provider selection, search recall architecture, or the 2026-08-14 multi-city isolation design. Production remains Google Flight Deals plus `gflights==0.3.0`, fixed CheapFlightRadar User-Agent, direct `proxy=None`, and short-lived GitHub Actions compute.

No proxy/UA rotation, `reset_rate_limit()`, automatic retry storm, 30-second timeout, new provider, cron, daemon, queue, or durable state service is introduced.

## Live evidence that exposed the gap

Explicit request `op-20260819-1445-e2e-health` ran in workflow `32224942582` as `operator-radar-op-20260819-1445-e2e-health-20260819T144821+0800`. The workflow completed and persisted immutable operator evidence, but provider health was `degraded`: only one of twelve Flight Deals calls returned records; TSA/RMQ/KHH discovery failed; exact/flexible completion did not converge; and the run emitted zero Deals with 25 Signals.

The old execution summary reported 63 technical failures. The repeated error was:

`Google Flights returned HTTP 429 Too Many Requests — all further requests on this client are blocked; call ApiClient::reset_rate_limit() to resume`

That count was operationally misleading. It described 63 logical Radar calls that encountered a failed client state, not 63 independent failed network requests.

## Upstream sticky-client semantics

The inspected upstream `nas-/google-flights-rs` implementation documents `RateLimitedError`: after any request on an `ApiClient` receives HTTP 429, that client and its clones share a `rate_limited` flag and refuse all later requests until reset. While flagged, later `do_request` calls return the rate-limit error immediately without touching the network. Upstream also states that 429 is not automatically retried.

Radar deliberately does not call `reset_rate_limit()`. Once this exact sticky condition is observed, continuing to invoke the same fixed client cannot improve recall and only inflates failure counters.

## Corrected execution semantics

Production keeps the two fixed lanes established by the prior hardening:

- `primary`: Flight Deals, Explore, conventional exact, flexible dates;
- `multi_city`: mixed-Taiwan-return and open-jaw.

Each lane has an in-process fail-closed circuit. It opens only when the normalized gflights failure contains both the HTTP 429 marker and the explicit upstream statement that all further requests on that client are blocked.

The first observed sticky failure remains an actual technical provider failure and actual client call. Later logical work on the same lane:

- remains counted as a logical `attempt`;
- does not invoke that provider client;
- increments `suppressed`;
- does not increment the technical `failures` counter;
- remains visible as missing/degraded coverage and therefore cannot be mistaken for a healthy empty market.

Normal complete-empty responses never open the circuit. Generic provider failures and a generic 429 lacking the explicit sticky marker do not open it either. Primary and multi-city lanes are independent: a sticky primary client does not pre-emptively suppress the reserved multi-city client, and vice versa.

## Evidence and publication

New execution evidence separates:

- logical attempts;
- actual provider/client calls;
- circuit-suppressed logical calls;
- successful responses;
- complete-empty responses;
- actual technical failures;
- unsupported work.

`provider_health.technical_failure_count` therefore represents actual attempted technical failures rather than repeated local sticky refusals. `provider_health.suppressed_request_count` records the amount of work deliberately not sent after the circuit opened. Pages renders both counts. Historical manifests remain readable because missing `provider_calls`/`suppressed` fields retain the legacy display path.

## Validation policy

This change is deterministic first. Tests must prove exact sticky matching, non-triggering for empty/generic failures, independent client lanes, one actual failure plus suppressed follow-ons, health accounting, and Pages rendering. The full unittest Gate and exact-head PR CI are required.

Do not immediately create another live operator request merely to exercise this patch. A new production acquisition is a separate intentional provider call and should occur on the next natural canonical day or a separately authorized operator request after merge.
