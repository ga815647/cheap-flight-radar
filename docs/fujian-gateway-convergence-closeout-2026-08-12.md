# Fujian gateway convergence closeout — 2026-08-12

Observed closeout: `2026-08-12T10:39:17+08:00`.

This document closes the focused convergence package that follows `docs/fujian-gateway-stress-2026-08-12.md`. It does **not** repeat the broad Fujian search. The target window remains the already-selected August convergence case around `2026-08-20` through `2026-08-23`.

## Evidence contract

At the time of the original closeout, the SSOT required exact priced ground components. A later same-day policy clarification now excludes **short local taxi-equivalent access** from both comparative cost and comparative transport time. Historical acquisition below is retained as evidence, but missing short local taxi fare/minutes are no longer blockers.

The current rule is therefore:

- every material priced required segment needs a current price;
- every material time-sensitive ferry / rail / intercity ground segment needs current schedule evidence;
- short local taxi-equivalent access needs only practical connection feasibility, not exact fare/time;
- unavoidable transport-caused overnight cost is part of complete effective transport cost;
- an essential material unknown keeps the route exploratory rather than final-verified;
- no proxy rotation, stealth/fingerprint spoofing, CAPTCHA bypass, residential proxy, or equivalent anti-bot workaround is permitted.

The immediately preceding convergence checkpoint is treated as durable input for components already acquired there. Those components are not re-searched or numerically reconstructed here. Where a prior exact value was not yet persisted into the repository, this closeout records its state as `exact-known (prior convergence checkpoint)` rather than inventing or backfilling the value.

## 1. One-shot 12306 probe closeout

PR #13 exact head `2a3c2a5cb0b6a82abd14766bcd2d7440fbb4bae8` ran the second branch-only `fujian-rail-probe` job successfully at the process / CI layer after adding normal 12306 session bootstrap and cookies. The preceding live checkpoint nevertheless observed the official error surface rather than usable target-date Xiamen North → Fuzhou South inventory / price evidence. A green Actions job therefore does not mean rail inventory was acquired.

No target-date train / seat / fare record from that probe was persisted into the repository, and the public Web retry in this closeout still did not expose a date-pinned `2026-08-20` inventory result: Ctrip search surfaces returned other dates or route-level/non-date-pinned train data.

Decision: **do not retain a production 12306 adapter**. The temporary `scripts/rail_12306_probe.py` and branch-only CI job were removed before merge. No further anti-bot workaround is justified.

## 2. KNH official August PDF — target-date page verification

The Taiwan Maritime and Port Bureau official page `115年8月金門小三通航班表`, published 2026-07-10, links the one-page August Kinmen ↔ Xiamen Wutong timetable PDF. The PDF page was visually inspected rather than relying only on parsed search text.

Official page:

- https://www.motcmpb.gov.tw/Information/Detail/92c6a106-2954-49b9-a721-a1095143b775?NodeId=543&SiteId=1

Official PDF:

- https://www.motcmpb.gov.tw/ServerFile/Get/5b1b46d6-5e9a-483d-b80c-c4da784ab25e?DLCount=1

For both `2026-08-20` and `2026-08-23`, the page contains vessel assignments for all twelve displayed departure slots in each direction. The common displayed departure times are:

`08:30, 09:00, 10:00, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:30, 17:00, 17:30`.

This fixes the target-date **timetable** evidence for the KNH gateway. It does not supply the still-missing target-date Taiwan domestic-air fare.

## 3. Focused remaining-component acquisition

Only the already-known blockers were queried. Once a component still failed to surface exact public evidence, searching stopped rather than rotating through more keywords.

### Kinmen / Xiamen chain

Current exact / usable evidence added in this closeout:

- The official Xiamen Airport Wutong shuttle page currently publishes Wutong → T4 → T3 departures from 09:00 through 18:15, about **15 minutes**, **CNY 6/person**; the reverse airport → Wutong direction is also explicitly timetabled.
- The official Xiamen Airport Wucun / Xiamen Railway Station shuttle currently publishes airport ↔ Wucun service, about **25 minutes**, **CNY 10/person**, with current operating-time information.
- These two official surfaces establish the required Wutong ↔ airport and airport ↔ Xiamen Station/Wucun priced transport edges. Actual end-to-end waiting time remains itinerary-dependent and is not guessed.

Sources:

- https://www.xiamenairport.com.cn/jcjt/jtzy-wtmt.aspx
- https://www.xiamenairport.com.cn/jcjt/jtzy.aspx

Still missing:

- `2026-08-20` **exact current fare** for a TSA/KHH → KNH morning flight that can safely feed the same-day ferry chain. Public schedule surfaces expose morning operations (including TSA departures as early as 06:40 and KHH services later in the morning), but the focused search did not expose a target-date fare tied to the required flight.
- required `2026-08-23` reverse domestic-air fare / itinerary at equivalent exactness. Public route pages expose schedules or other-date / route-floor fares, but not a complete target-date pair suitable for final normalization.

Public schedule/fare surfaces checked once for this blocker:

- https://www.directflights.com/TSA-KNH
- https://www.directflights.com/KHH-KNH
- https://www.directflights.com/KNH-KHH
- https://www.skyscanner.com.tw/routes/khh/knh/kaohsiung-to-kinmen.html
- https://us.trip.com/flights/airport-tsa-knh/
- https://us.trip.com/flights/airport-knh-tsa/

Result: **KNH remains fail closed on domestic-air exact fare**, despite the now-fixed official ferry timetable and usable official Xiamen city-transfer components.

### MFK / Huangqi / Fuzhou chain

Already exact-known from the preceding convergence checkpoint and deliberately not re-searched:

- `2026-08-20 → 2026-08-23` TSA ↔ MFK domestic-air component;
- Baisha ↔ Huangqi ferry fare / target-date operating evidence.

Still missing after one focused public acquisition attempt:

- Huangqi → Fuzhou city **target-date exact fare + time**. No public result surfaced a date-matched priced transfer suitable for normalization.
- The return topology still requires crossing back before the `2026-08-23` Taiwan flight, creating a transport-caused `2026-08-22 → 2026-08-23` Beigan overnight. Booking / Expedia public pages expose Beigan properties and generic/current prices, but did not expose a target-date `2026-08-22` price/availability record that can be safely inserted into transport cost.

Surfaces checked once for the overnight blocker:

- https://www.booking.com/accommodation/city/tw/beigan.zh-tw.html
- https://www.expedia.com.tw/Matsu-Beigan-Airport-Hotels.0-aMFK-0.Travel-Guide-Filter-Hotels

Result: **MFK remains fail closed on mainland transfer + unavoidable overnight cost**.

### Xiamen ↔ Fuzhou rail

A focused `2026-08-20` public retry still did not produce a date-pinned Xiamen North → Fuzhou South train / seat / fare record. Search surfaces returned other dates or non-date-pinned route results. The route-level fare / frequency evidence from the earlier stress test is therefore not promoted to exact target-date evidence.

Surfaces checked:

- https://trains.ctrip.com/trainbooking/xiamenbei-fuzhounan/dongche
- https://m.ctrip.com/html5/trains/xiamenbei-fuzhounan/

Result: **rail remains exact-missing; no production adapter retained**.

## 4. Convergence component matrix

| Candidate / component | State after closeout | Exact-known evidence | Exact-missing blocker | Decision |
|---|---|---|---|---|
| TSA ↔ MFK, 08/20→08/23 | exact-known (prior convergence checkpoint) | target-date domestic-air component previously acquired | — | retain as known component; do not backfill values |
| Baisha ↔ Huangqi, target dates | exact-known (prior convergence checkpoint) | target-date ferry + fare previously acquired | — | retain as known component; do not re-search |
| Huangqi → Fuzhou city | **exact-missing** | — | target-date fare + time | MFK route fail closed |
| Beigan overnight 08/22→08/23 | **exact-missing** | lodging topology is required by return connection | target-date unavoidable overnight price / availability | MFK route fail closed |
| TSA/KHH → KNH, 08/20 morning | **partial** | target-date schedule evidence exists | exact current fare tied to a connectable flight | KNH route fail closed |
| KNH → TSA/KHH, 08/23 | **partial** | return schedule evidence exists on public route surfaces | exact current fare / target-date pair | KNH route fail closed |
| KNH ↔ Shuitou / Shuitou ↔ Wutong | exact-known (prior convergence + official August PDF) | Kinmen ground/ferry components and target-date official sailing table | — | usable component evidence |
| Wutong ↔ Xiamen Airport | **exact-known current** | official timetable; ~15 min; CNY 6/person | itinerary-specific waiting time only | usable component evidence |
| Xiamen Airport ↔ Wucun / Xiamen Station | **exact-known current** | official service; ~25 min; CNY 10/person | itinerary-specific waiting time only | usable component evidence |
| Xiamen North ↔ Fuzhou South rail 08/20 | **exact-missing** | route topology only | target-date train / seat / fare evidence | rail/open-jaw branch fail closed |
| 12306 deterministic adapter | **rejected** | normal bootstrap probe executed | no usable target-date inventory; official error surface in preceding live result | remove temporary probe; no production adapter |

## 5. Fail-closed comparison output

The user-facing comparison contract for this closeout is stricter than the earlier exploratory table: **if any essential component is unknown, every derived comparison field stays `N/A`**.

| Gateway candidate | Complete effective transport cost | Usable time | Extra transport time | Risk | Same-date direct-air benchmark | Savings / extra transport hour |
|---|---:|---:|---:|---:|---:|---:|
| TSA → MFK → Baisha → Huangqi → Fuzhou → return | N/A | N/A | N/A | N/A | N/A | N/A |
| TSA/KHH → KNH → Shuitou → Wutong → Xiamen → return | N/A | N/A | N/A | N/A | N/A | N/A |
| XMN ↔ FOC rail / two-city expansion | N/A | N/A | N/A | N/A | N/A | N/A |

No partial sticker arithmetic is promoted to a deal score or benchmark delta.

## 6. Price-history decision

This closeout produced **no new observation that satisfies the current historical baseline fare scope `usable_complete_trip`**. The newly acquired evidence is timetable / transfer evidence, while the target gateway candidates remain incomplete. Therefore no synthetic or partial-fare snapshot is written to `history/price-observations` for this closeout. Existing history is left intact; nothing is backfilled.

## 7. Closeout decision and next atomic package

No new SSOT gap was discovered. `flight-radar.yaml` remains unchanged.

Both serious ferry gateways still fail closed, but for sharply bounded reasons rather than broad-search uncertainty:

- **MFK:** official/public surface for Huangqi ↔ Fuzhou target-date priced transfer, then a target-date Beigan overnight booking surface caused by the required early return crossing.
- **KNH:** official or otherwise exact-booking domestic-air surface for the connectable `08/20` outbound and `08/23` reverse fare. Short local KNH/Xiamen taxi-equivalent access is no longer a cost/time blocker; only practical connection feasibility matters.
- **Rail:** a legitimate target-date rail ticketing/inventory surface; the 12306 GitHub-runner experiment does not justify an adapter.

The next atomic package should research **the official ticketing / shuttle / booking surfaces that directly resolve those exact components**. It should not repeat a Fujian broad search and should not add general crawler infrastructure unless one specific official/public blocker surface first demonstrates a deterministic, compliant acquisition path.
