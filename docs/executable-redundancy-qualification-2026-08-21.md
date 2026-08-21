# CFR-SR-D — executable TWD-0 access redundancy qualification (2026-08-21)

## Decision

Qualify and integrate the official public Kiwi.com remote MCP as CFR's **automatic known-route exact/flexible fallback** behind the primary gflights Google access lane.

The qualification is deliberately scoped.  It does **not** create destination-free Flight Deals/anomaly redundancy and it does not replace Google Flight Deals as CFR anomaly truth.  Open-jaw/multi-city remains on the qualified gflights path only.  A failed primary known-route request may fall back once to Kiwi MCP; both attempts remain explicit execution evidence.

## Candidate A — fli / flights==0.9.0

Release-source audit found two defaults that are not admissible under CFR's accepted transport contract:

- Google requests explicitly pass `impersonate="chrome"` through curl-cffi;
- the HTTP client is decorated with three automatic retry attempts.

Experiment PR #68 proved that fli's protocol/parser implementation still works when the experiment removes browser impersonation before import, forces retry attempts to exactly one, adds the fixed CFR user agent and uses direct/no-proxy access.  The bounded TPE–NRT exact round-trip and 31-day flexible-calendar probes both returned current TWD evidence.

This proves the parser/protocol implementation is useful, but it remains the same Google upstream as gflights and stock fli cannot be adopted without maintaining a transport shim/fork.  It therefore does not provide the independent access redundancy SR-D is seeking and is not selected for production.

Experiment PR #68 is evidence-only and must remain unmerged.

## Candidate B — official Kiwi.com remote MCP

Kiwi.com's public remote MCP endpoint was tested directly with the standard MCP client, without an API key/login, proxy, CAPTCHA/stealth mechanism, browser/TLS impersonation, session/UA rotation or CFR retry loop.

Experiment PR: #69

Exact experiment head: `27dc0914429f5872a7bd74b618c6f9f856973738`

Workflow run: `32492608693`

Qualification job: `96803536401`

Observed live server contract:

- endpoint: `https://mcp.kiwi.com`;
- server: `kiwicom-flight-search` version `1.28.1`;
- MCP protocol: `2025-11-25`;
- search tool: `search-flight`;
- required query fields: `flyFrom`, `flyTo`, `departureDate`;
- TWD currency supported;
- exact return date, departure/return ranges, destination-stay nights, baggage/self-transfer and result sorting are exposed in the live tool schema.

The corrected single bounded call queried one adult/economy TPE→NRT on 2026-10-05 returning 2026-10-09 in TWD.  The tool returned 15 exact itineraries.  The first result was TWD 9,168 with exact airports, segment times, carriers/flight numbers, baggage metadata and a Kiwi booking URL.  `isError=false` and `error=null`.

This is an independent provider/access lane rather than another Google parser.  It is therefore qualified for exact/flexible known-route fallback execution.

## Integration scope

Current canonical routing becomes:

- destination-free Deal discovery/anomaly acquisition: `gflights_google_flight_deals` only; no automatic executable fallback;
- known-route exact/flexible completion primary: `gflights_google_exact`;
- known-route exact/flexible automatic fallback after a primary technical failure: `kiwi_mcp_exact`;
- open-jaw/multi-city: `gflights_google_exact` only;
- anomaly truth order remains `google_flight_deals -> google_flights_exact_price_insight -> own_price_history`.

Kiwi fallback records may prove current complete airfare and exact itinerary evidence, but they do not invent Google typical-price/anomaly context.  A Deal can still use a qualified Google Flight Deals discovery baseline with independently revalidated current complete airfare from Kiwi.

## Execution-truth requirements

- fallback is attempted only after primary known-route technical failure, not after a healthy complete-empty result;
- no retries/evasion are introduced by CFR;
- primary failure and fallback outcome are retained separately in `coverage.access_redundancy`;
- a successful fallback does not erase the primary degradation; provider health becomes degraded for that run;
- if both primary and fallback fail, the request remains failed closed;
- no destination-free or open-jaw coverage is claimed from Kiwi MCP.

## Cost / authority

The qualified path is currently credential-free and TWD-0 from CFR's perspective.  If Kiwi later adds a credential, payment, partnership, login or materially restricted-access gate, this qualification no longer authorizes unattended production use and the lane must fail closed pending requalification.

No FTR work is included in SR-D.
