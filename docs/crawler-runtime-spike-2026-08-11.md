# Crawler runtime build-vs-reuse spike — 2026-08-11

## Decision

Use **Scrapy as the fixed-watch HTTP runtime**. Keep **scrapy-playwright as an opt-in vanilla JavaScript fallback interface**, but do not promote a source to fixed coverage merely because a browser exits successfully.

Do not build a custom crawler runtime. Source-specific parsers, fixtures, coverage semantics, normalized observation models, provenance, and dedupe stay in this repository. Scrapy owns request scheduling, queueing, normal retries, cookies/session continuity, downloader lifecycle, and selector response objects.

No CAPTCHA bypass, stealth/fingerprint spoofing, proxy rotation, residential IP, or similar anti-bot evasion is permitted.

## Orchestration boundary

GitHub Actions is **not** the primary scheduler. A ChatGPT scheduled radar run reads the registry and prior successful attempt state, determines which fixed watches are due, dispatches the deterministic GitHub execution backend, reads the attempt manifest and normalized observations, then continues with opportunistic Web discovery, deep search, revalidation, and final reporting.

`cadence_hours` is the maximum reusable age of the latest **successful** fixed-watch attempt. It is not an Actions cron expression. A failed attempt never refreshes the due clock. Production fixed-watch execution is `workflow_dispatch` only; there is no independent GitHub cron.

## Candidate comparison

| Runtime | HTTP + JS | Queue / retry / session | Output / fixture fit | Observed Actions cost | Maintenance / compliance | License | Decision |
|---|---|---|---|---|---|---|---|
| Scrapy + scrapy-playwright | Native HTTP; per-request Playwright opt-in | Mature scheduler, retry middleware, cookies | Parsel is fixture-friendly; repo controls normalized manifests | pip 9.46s; Chromium 22.90s; HTTP+JS smoke 1.62s | Clean HTTP-first boundary; vanilla Playwright only | BSD-3-Clause / BSD-3-Clause | **Selected** |
| Crawlee for Python | ParselCrawler + PlaywrightCrawler | Built-in queue/retries/sessions/datasets | Strong crawler storage/routing | pip 9.15s; Chromium 27.21s; smoke 2.97s | Browser extra installed fingerprint tooling; safe behavior required explicit fingerprint/session/block-retry opt-outs | Apache-2.0 | Not selected |
| urlwatch | URL + browser jobs | Watch-oriented retry/state | Excellent diff monitoring, but output model is changed/unchanged history rather than radar sightings/manifests | pip 10.10s; Chromium 23.83s; browser test 1.32s | Would add a second state/diff model the radar does not need | not decision-critical | Not selected |
| changedetection.io | HTTP service + separate browser service for JS | Persistent watch service | UI/API centered on page changes/history | ~20s container cold start; ~1.02 GB image | Too heavy for ephemeral Actions execution; persistent-service architecture mismatches ChatGPT orchestration | upstream advertises Apache-2.0; licensing surface not needed for decision | Not selected |

## Framework probe evidence

- `572ace2d2e468520128ede271a479b59254de3e9`, run `31471922991`: initial harness exposed Chromium sandbox/test issues and Crawlee fingerprint behavior when not explicitly disabled.
- `e8bd1995b81500c30fc10bb4804966b5c6ade0ad`, run `31472215749`: corrected probe. Scrapy+Playwright and Crawlee both passed deterministic HTTP+JS fixtures; Crawlee used `fingerprint_generator=None`, `retry_on_blocked=False`, and no session rotation. changedetection.io started successfully; urlwatch browser job returned the JS fixture. Project CI run `31472215751` passed.
- The temporary generic runtime-spike workflow was removed after the evidence was recorded.

## Current-source live evidence

A separate one-shot live workflow ran the actual registry sources on GitHub-hosted Ubuntu and was removed after evidence collection.

### First integration probe

Run `31473460091`:

- China Airlines: HTTP 200, parser succeeded, but the first parser was too broad and included generic fare-information/disruption links.
- PTT Japan_Travel: HTTP 200, parser contract succeeded, zero matching `[資訊]` airfare signals at that moment. Zero observations is still a successful source attempt when the public board structure is valid.
- Tigerair Taiwan current homepage: HTTP 200 but no stable public promotion-anchor contract; correctly recorded `parse_failed`.

### Corrected integration probe

Run `31473909367` on exact source head `86d3bf3e9c3e93ae32a9a8a1cbba5d5475181f12`:

- China Airlines: HTTP 200, parser succeeded and was narrowed to actual event pages / route-price cards; 8 observations in that live snapshot.
- PTT Japan_Travel: HTTP 200, parser succeeded, zero matching current airfare signals.
- Tigerair Taiwan: ordinary Playwright also returned HTTP 200 but still did not expose a stable promotion-anchor parser contract; it remained `parse_failed`.

This result changed the registry. Tigerair is **not** a fixed watch in v1. Public Web discovery can find official Tigerair news and `static.tigerairtw.com` event pages, so Tigerair remains valuable as `opportunistic`, but a source whose deterministic HTTP and vanilla-browser attempts cannot establish a stable parse contract must not permanently degrade fixed coverage.

## Final v1 runtime shape

Current fixed watches are:

- `china_airlines_official` — direct HTTP, 6-hour freshness threshold;
- `ptt_japan_travel_info` — direct HTTP, 3-hour freshness threshold.

Therefore current fixed-watch executions install **Scrapy only**. The production workflow retains a conditional `scrapy-playwright` installation path for a future source only after that source has a repeatable, public, source-specific browser contract and fixture. No current fixed watch requires a browser.

Tigerair official news/static event pages are handled by ChatGPT's opportunistic open-Web phase and do not count toward fixed-watch coverage.

## Repository/runtime ownership

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
- optional vanilla Playwright rendering only when explicitly enabled by a future source contract.

Blocked/login/CAPTCHA outcomes are coverage failures, not triggers for evasion.