# Crawler runtime build-vs-reuse spike — 2026-08-11

## Decision

Use **Scrapy as the fixed-watch HTTP runtime** and keep **scrapy-playwright as an opt-in JavaScript fallback** for sources that are later proven to need browser rendering.

Do not build a custom crawler runtime. Keep source-specific parsers, fixtures, coverage semantics, normalized observation models, provenance, and dedupe inside this repository.

The current three fixed watches are all `direct_http`, so the normal GitHub Actions execution path installs Scrapy only and does not download a browser. A future source may opt into `scrapy-playwright` only after a fixture and live probe demonstrate that HTTP is insufficient.

No CAPTCHA bypass, stealth fingerprinting, fingerprint spoofing, proxy rotation, residential IP, or similar anti-bot evasion is permitted.

## Orchestration boundary

GitHub Actions is **not** the primary scheduler for Cheap Flight Radar.

A ChatGPT scheduled radar run is the orchestrator. It reads the fixed-watch registry and prior successful attempt state, determines which watches are due under `cadence_hours`, dispatches the required deterministic GitHub execution, reads the resulting attempt manifest and normalized observations, then continues with opportunistic Web discovery, deep search, revalidation, and report generation.

`cadence_hours` is a freshness/reuse ceiling and due threshold measured from the latest successful fixed-watch attempt. It is not an Actions cron expression or an instruction to create an independent GitHub schedule. Failed attempts do not refresh the due clock.

## Candidates

| Runtime | HTTP + JS | Retry / session / queue | Fixtureability / output | Actions cost observed | Maintenance / compliance | License | Decision |
|---|---|---|---|---|---|---|---|
| Scrapy + scrapy-playwright | Native Scrapy HTTP; Playwright per-request opt-in | Mature scheduler/queue, RetryMiddleware, cookies/session support | Parsel selectors are easy to fixture-test; feed exports support JSON/JSONL/CSV/XML | Probe: pip 9.46s; Chromium install 22.90s; HTTP+JS smoke 1.62s | Clear separation between HTTP and vanilla Playwright; no anti-bot feature required | Scrapy BSD-3-Clause; scrapy-playwright BSD-3-Clause | **Selected** |
| Crawlee for Python | ParselCrawler + PlaywrightCrawler | Built-in request queue, retries, sessions, datasets | Strong crawler-level storage and routing | Probe: pip 9.15s; Chromium install 27.21s; HTTP+JS smoke 2.97s | Technically good, but Playwright extra installs fingerprint packages and fingerprint generation is a default capability; project would need permanent explicit opt-out guards | Apache-2.0 | Not selected |
| urlwatch | URL jobs + Browser jobs | Per-job retry; state/history is oriented to change monitoring | Excellent page-diff fixtures, but primary output/state model is changed/unchanged history rather than normalized sightings/run manifests | Probe: pip 10.10s; Chromium install 23.83s; browser test 1.32s. Static test hit a local test-server readiness race, not a product limitation | Adds diff/history semantics the radar does not need | BSD-family project; not embedded | Not selected |
| changedetection.io | HTTP service; JS normally uses a separate browser service | Watch-oriented service state/retry | UI/API centered on change detection and notification history | Probe: container cold start about 20s; image 1,020,365,287 bytes | Heavy persistent-service architecture for an ephemeral Actions backend; repository also has historical licensing-surface ambiguity around an added commercial-license file | Repository advertises Apache-2.0; licensing ambiguity noted in upstream issue #2806 | Not selected |

## GitHub Actions probes

Temporary workflow: `.github/workflows/crawler-runtime-spike.yml`.

- First probe commit: `572ace2d2e468520128ede271a479b59254de3e9`
  - run `31471922991`
  - exposed two test-harness issues and one important Crawlee compliance default: old Scrapy `start_requests`, Chromium sandbox launch, and Crawlee Playwright fingerprint injection when not explicitly disabled.
- Corrected probe commit: `e8bd1995b81500c30fc10bb4804966b5c6ade0ad`
  - run `31472215749`
  - `scrapy_playwright`: success on HTTP and JS
  - `crawlee`: success on HTTP and JS with `fingerprint_generator=None`, `retry_on_blocked=False`, and session rotation disabled
  - `changedetection`: service startup success
  - `urlwatch`: browser job returned `js-ready`; HTTP assertion raced the local fixture server startup
  - ordinary project CI run `31472215751`: success

The spike workflow is temporary evidence and should be removed after the runtime decision is recorded; production workflow(s) must remain `workflow_dispatch`/caller-driven with no independent cron.

## Why Scrapy wins this repository

1. All current fixed watches are ordinary HTTP sources, so Scrapy gives queue/retry/cookies/export without a browser dependency.
2. Parsel selectors can be exercised directly against committed HTML fixtures, keeping parser drift deterministic and source-specific.
3. A future JS-only source can use `scrapy-playwright` on a request-by-request basis without changing the queue, retry, item pipeline, or run-manifest contract.
4. Vanilla Playwright is the default integration path. This avoids importing a crawler whose browser extra ships fingerprint generation as a normal/default anti-blocking feature.
5. Scrapy's output does not impose a separate page-diff/history database; normalized observations and provenance remain Cheap Flight Radar concepts.

## Production runtime contract

The repository owns:

- SSOT registry validation and due planning;
- fixed-watch attempt/run manifests;
- source-specific parsers and committed fixtures;
- normalized discovery sightings;
- campaign/exact-itinerary dedupe keys and append-only provenance;
- coverage interpretation.

Scrapy owns:

- HTTP request scheduling and queueing;
- normal HTTP retries;
- cookie/session continuity where a public source requires it;
- downloader lifecycle;
- parser response objects / selectors;
- optional vanilla Playwright rendering when explicitly enabled for a source.

Blocked/login/CAPTCHA outcomes are recorded as coverage failures. They are not a trigger for stealth, fingerprint spoofing, proxy rotation, residential IPs, or CAPTCHA bypass.