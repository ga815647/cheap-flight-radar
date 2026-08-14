# Production soak and 429 hardening — 2026-08-14

## Scope

This checkpoint is the post-merge operational follow-up to Issue #26. It does not reopen the production-search recall architecture or the airfare substrate decision.

Production invariants remain:

- Google Flight Deals is primary Deal discovery / route-relative anomaly truth.
- `gflights==0.3.0` remains the keyless acquisition substrate.
- production uses the explicit CheapFlightRadar User-Agent and `proxy=None`.
- no proxy rotation, browser-UA rotation, stealth/fingerprint behavior, CAPTCHA bypass, or `reset_rate_limit()` workaround is introduced.
- ChatGPT remains scheduler/orchestrator; GitHub Actions here is disposable one-shot compute only. No cron is added.

## Issue #26 closeout

PR #25 was merged as `44d254af594a25c860d2d5d61c106170ceddad0a`, which was the current `main` at the start of this checkpoint. The Issue #26 completion evidence was already durable, so Issue #26 was closed as completed before this operational follow-up.

## Normal `main` production baseline

The first soak ran the ordinary canonical command against production code from `main`:

```text
python -m cheap_flight_radar.production_runtime --history-dir _history --output-dir _out
```

Evidence:

- workflow run: `31787655458`
- production-soak job: `94727092431`
- runtime-equivalent source: `44d254af594a25c860d2d5d61c106170ceddad0a` (the branch head only added the disposable CI job)
- artifact: `9215241241`
- artifact digest: `sha256:c7f6a49bf5b53624a40aaca5fc120ba22462e3da8fbd88dd7c8a5f8b0497dbd2`
- Radar run: `production-radar-20260814T172041+0800`
- acquisition runtime: about 40m36s

Observed execution:

| Surface | Attempts | Success | Failed | Records |
| --- | ---: | ---: | ---: | ---: |
| Flight Deals | 12 | 12 | 0 | 360 |
| Explore | 4 | 4 | 0 | 393 |
| Conventional exact | 20 | 20 | 0 | 20 |
| Flexible dates | 20 | 16 | 4 | 1592 |
| Mixed Taiwan return | 4 | 0 | 4 | 0 |
| Open-jaw | 4 | 0 | 4 | 0 |

All TPE / TSA / RMQ / KHH origin sweeps were attempted. The run produced 10 Deals and 397 Signals.

Every mixed-return and open-jaw failure was the same gflights client-local sticky HTTP 429 condition:

```text
GFlightsError: Google Flights returned HTTP 429 Too Many Requests — all further requests on this client are blocked; call ApiClient::reset_rate_limit() to resume
```

The failure was therefore operationally structural on the shared client, not merely an absence of qualifying multi-city fares.

### Request-ordering / density finding

The production ordering places multi-city last. In the baseline run, the shared client completed roughly:

- 12 Flight Deals requests;
- 4 Explore requests;
- 20 conventional exact searches, each potentially followed by an offer request;
- 20 flexible-date requests;
- 16 successful flexible candidates followed by exact completion, each potentially followed by an offer request;

before the eight mixed/open-jaw requests. That is roughly 108 low-level provider calls before multi-city under this observed success pattern. Once the shared client became sticky-blocked by 429, the final eight requests could no longer execute normally.

## Bounded-timeout experiment: rejected

A first hardening experiment combined two changes:

1. reserve a second fixed `GFlightsAdapter` client for multi-city surfaces; and
2. apply a 30-second high-level provider-call timeout.

Evidence:

- workflow run: `31790575096`
- production-soak job: `94736322578`
- artifact: `9215639590`
- artifact digest: `sha256:7deaa2d5b2cb4b3d7f858020bc6a1ca00687b7ec1a6feade385d943fb05e6d15`
- Radar run: `production-radar-20260814T180239+0800`

Observed execution:

| Surface | Attempts | Success | Failed | Records |
| --- | ---: | ---: | ---: | ---: |
| Flight Deals | 12 | 12 | 0 | 360 |
| Explore | 4 | 4 | 0 | 415 |
| Conventional exact | 20 | 20 | 0 | 20 |
| Flexible dates | 20 | 0 | 20 | 0 |
| Mixed Taiwan return | 4 | 3 | 1 | 3 |
| Open-jaw | 4 | 2 | 2 | 2 |

No mixed/open-jaw request failed with HTTP 429. The three remaining multi-city failures were ordinary `empty` results. This proves that reserving multi-city client capacity breaks the shared-client sticky-starvation mechanism.

However, the 30-second timeout destroyed flexible-date recall (0/20 versus 16/20 in the baseline). That timeout is therefore rejected and is not part of the final design.

## Final no-timeout production soak: passed

The final validation reran the ordinary canonical production command with the timeout removed and only the reserved multi-city client retained.

Evidence:

- workflow run: `31791704712`
- production-soak job: `94739841094`
- runtime-equivalent source: `8fc82410dd046e953e75037442559733106c877a`
- artifact: `9216744987`
- artifact digest: `sha256:5e8e3d6df3c1dc231d902330e23ef70459ab43016593bfae2c5fe6ba572bf7e0`
- Radar run: `production-radar-20260814T181909+0800`
- acquisition runtime: about 39m36s

Observed execution:

| Surface | Attempts | Success | Failed | Records |
| --- | ---: | ---: | ---: | ---: |
| Flight Deals | 12 | 12 | 0 | 360 |
| Explore | 4 | 4 | 0 | 391 |
| Conventional exact | 20 | 20 | 0 | 20 |
| Flexible dates | 20 | 16 | 4 | 1577 |
| Mixed Taiwan return | 4 | 3 | 1 | 3 |
| Open-jaw | 4 | 2 | 2 | 2 |

All TPE / TSA / RMQ / KHH origin sweeps were attempted. The run produced 10 Deals and 395 Signals.

The only remaining multi-city failures were ordinary empty results:

- `RMQ · open_jaw · RMQ-HRB/DRP-RMQ · empty`
- `TSA · mixed_taiwan_return · TSA-CJU-TPE · empty`
- `TSA · open_jaw · TSA-CJU/DRP-TSA · empty`

There was no HTTP 429 failure in the final run. Conventional exact remained 20/20 and flexible-date recall returned to 16/20, matching the healthy baseline success count while mixed-return/open-jaw retained the 3/4 and 2/4 success pattern from the isolation experiment. The final no-timeout design therefore satisfies the operational completion criterion.

## Final hardening design

The final code keeps only the minimal operational isolation:

- construct one fixed primary `GFlightsAdapter` for Flight Deals / Explore / conventional exact / flexible dates;
- construct one fixed multi-city `GFlightsAdapter` at process start for mixed-return / open-jaw;
- both clients use the same explicit CheapFlightRadar User-Agent, direct `proxy=None`, locale, and currency;
- there is no per-request client creation, rotation, retry loop, rate-limit reset, proxy change, or browser identity change;
- primary-surface latency and recall semantics remain unchanged from `main`;
- provider refusal on the reserved multi-city client still fails closed through the normal `ProviderResult` evidence path.

This is a bounded surface request budget, not anti-bot evasion.

## Publication closeout

The final successful soak artifact was published without another live acquisition run.

Durable evidence refs:

- immutable history ref head after append: `17de2a23e5eab5fee975becf61746684f790ce42`
- snapshot: `data/price-history/2026/08/14/production-radar-20260814T181909-0800.json`
- publication ref head after append: `12126577d6fcb7957d8151c76a291161254bd460`
- manifest: `publication/runs/production-radar-20260814T181909+0800.json`

A disposable closeout job (`31798987692`) downloaded artifact `9216744987`, revalidated the final soak counters/failures, appended the exact generated snapshot and manifest to their dedicated refs, and built the deterministic site against the PR exact head. The one-shot scaffold was removed afterward and is not part of the merge diff.

Because a `GITHUB_TOKEN`-authored push does not recursively trigger another workflow, the publication manifest append did not itself start Radar Pages. A fresh dispatch of the existing `radar-pages.yml` workflow was therefore used; the authoritative publication deployment is:

- Radar Pages run: `31799143910`
- build job: `94762769491` — success
- deploy job: `94762844340` — success
- deployed Pages artifact: `9218531765`
- Pages artifact digest: `sha256:e98f9c585703e0a5515fe1055e306952f49a4bc29b561ea1ddcc7f20e049834b`

The deployed artifact verifies:

- permanent per-run page exists at `runs/production-radar-20260814T181909-0800/index.html`;
- `latest/index.html` is byte-identical to that permanent run page;
- root `index.html` links the permanent run;
- 10 Deal cards and 395 Signal / airfare-alternative cards are rendered;
- TPE / TSA / RMQ / KHH origin rows are all present;
- execution counters preserve conventional `20/20`, flexible `16/20`, mixed-return `3/4`, and open-jaw `2/4` outcomes;
- the three provider-failure rows are present and all show `empty` rather than HTTP 429;
- historical metrics are derived from immutable history, including sparse-history sample counts/confidence and prior/rolling lows where available (for example TPE→ISG has 2 comparable samples and a TWD 5,897 prior/30d/90d/365d low);
- exact itinerary identity remains visible in Deal presentation, including route, outbound/return dates, airline, and booking/evidence identity (for example TPE→FKS, 2026-09-15→2026-09-22, IT / Tigerair Taiwan).

An attempted re-run of the old Radar Pages run was not used as publication evidence because `actions/deploy-pages` correctly rejected the two same-named `github-pages` artifacts accumulated across run attempts. The fresh workflow-dispatch run above has one Pages artifact and is the authoritative successful deploy.

## Validation status

The final clean normal-production soak passed. Deterministic tests cover that multi-city calls use the reserved adapter while non-multi-city calls remain on the primary adapter. Publication evidence is durable, and both exact-head deterministic rendering and the fresh Pages build/deploy passed.

All temporary production-soak and publication-closeout/dispatch workflow scaffolds have been removed from the PR branch. The remaining closeout requirement is final Gate / exact-head CI on the cleaned PR head before merge recommendation.
