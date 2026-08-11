# Fujian gateway stress test — 2026-08-12

Observed run: began 2026-08-11 23:49 Asia/Taipei and crossed midnight; durable observation timestamp is `2026-08-12T00:01:27+08:00`.

Rolling horizon: `2026-08-12` through approximately `2026-12-10`.

## Scope and evidence contract

This live operational pass compares direct Taiwan → Fujian air entry with Kinmen / Matsu Mini Three Links gateways, then attempts Fujian rail, domestic-air, second-city, and open-jaw expansion.

The run follows the current SSOT without adding a new policy:

- scan `TPE / TSA / RMQ / KHH → XMN / FOC` for direct-air opportunity;
- attempt `KNH`, `MFK`, and `LZN` gateway coverage rather than assuming they are cheaper;
- keep a conventional round-trip benchmark;
- treat return windows as search/scoring guidance only, never as a hard rejection rule;
- compare complete required transport cost and required transport time, not sticker airfare alone;
- fail closed when an essential target-date price, timetable, transfer, or availability component cannot be revalidated;
- public fare-index / metasearch observations remain public-fare evidence, not checkout guarantees.

The lowest direct one-way seeds found on indexed route surfaces were clicked through when possible. The exact Skyscanner deal endpoints used for the early `TSA-FOC ~TWD 4.47k` and `KHH-XMN ~TWD 4.59k` seeds returned cache misses. Those values therefore remain discovery seeds and are not promoted to current bookable fares.

## 1. Rolling 120-day Taiwan → Fujian direct-air sweep

| Origin | XMN direct-air result | FOC direct-air result | Decision |
|---|---|---|---|
| TPE | direct Xiamen Airlines seeds around TWD 5.2k one way were exposed in the horizon | direct Xiamen Airlines seeds around TWD 5.2k one way were exposed | covered; not the cheapest current Taiwan entry |
| TSA | **current KAYAK one-way TWD 4,164 on 2026-09-14**; current direct RT TWD 9,491 on 09/01→09/04 and TWD 9,459 on 09/20→10/03 | **current KAYAK one-way TWD 4,158 on 2026-09-13**; current direct RT TWD 8,961 on 08/21→08/26 and TWD 8,833 on 09/20→10/07 | **best current direct Fujian entry family** |
| RMQ | no direct flight surfaced; connected fares were materially above the TSA direct seeds | no direct flight surfaced; connected fares were materially above the TSA direct seeds | direct-air branch exhausted; do not manufacture a direct option |
| KHH | direct service exists; earlier indexed seed around TWD 4.59k one way failed exact deal click-through | direct service exists; current indexed 08/23 one-way around TWD 5,235 and route-level RT estimate around TWD 8,468 | useful secondary origin, but current exact-date direct benchmark did not beat TSA |

The meaningful live result is not the old `TSA-FOC ~4.47k` index price. The fresher KAYAK surface now exposes `TSA-FOC` at **TWD 4,158 one way** and `TSA-XMN` at **TWD 4,164 one way** in the next several weeks. Both pages explicitly state that their displayed recent deals may change or expire, so they are discovery/current-public-fare evidence rather than checkout guarantees.

Sources:

- https://www.tw.kayak.com/%E8%88%AA%E7%8F%AD/%E5%8F%B0%E5%8C%97-TW1/%E7%A6%8F%E5%B7%9E%E9%95%B7%E6%A8%82%E5%9C%8B%E9%9A%9B%E6%A9%9F%E5%A0%B4-FOC
- https://www.tw.kayak.com/%E8%88%AA%E7%8F%AD/%E5%8F%B0%E5%8C%97%E6%9D%BE%E5%B1%B1-TSA/%E5%BB%88%E9%96%80%E6%A9%9F%E5%A0%B4-XMN
- https://www.skyscanner.com.tw/routes/khh/foc/kaohsiung-to-fuzhou.html
- https://www.skyscanner.com.tw/routes/khh/xmn/kaohsiung-to-xiamen.html

## 2. Complete conventional direct-air benchmarks

To avoid comparing airport-only sticker prices against ferry gateways, this run normalizes each direct benchmark to a practical city rail-station anchor using a currently published required transfer.

For small CNY components only, comparison arithmetic uses approximately `TWD 4.78 / CNY`, consistent with current late-July CNY/TWD market observations. This is a comparison normalization, not additional fare precision.

### Fuzhou benchmark — TSA → FOC → Fuzhou Railway Station

Use the current direct `2026-08-21 → 2026-08-26` Mandarin Airlines pair exposed by KAYAK:

- outbound `TSA 07:05 → FOC 08:40`;
- return `FOC 09:45 → TSA 11:25`;
- round-trip airfare: **TWD 8,961**;
- Fuzhou Binhai Express airport ↔ Fuzhou Railway Station: **CNY 17 each way**, with airport ↔ station as fast as 30 minutes and hourly limited-stop trains around 38 minutes;
- required rail transfer: CNY 34 ≈ **TWD 163**;
- **complete effective required transport ≈ TWD 9,124** to the Fuzhou Railway Station anchor.

Raw destination window is about `121h05m`. Subtracting two 38-minute airport-rail movements gives about **119h49m ground-adjusted usable span**, before any standardized international airport-process buffer.

A cheaper direct RT, `2026-09-20 → 2026-10-07` at **TWD 8,833**, is 17 nights. It remains eligible evidence: the long stay is **not** rejected merely for exceeding the preferred return window.

Sources:

- KAYAK FOC route above.
- https://jtyst.fujian.gov.cn/zwgk/jtyw/mtsy/202509/t20250930_7017910.htm
- https://www.fuzhou.gov.cn/zwgk/gzdt/rcyw/202602/t20260201_5279714.htm

### Xiamen benchmark — TSA → XMN → Xiamen Railway Station / Wucun anchor

Use the current direct `2026-09-01 → 2026-09-04` Xiamen Airlines pair exposed by KAYAK:

- outbound `TSA 19:45 → XMN 21:30`;
- return `XMN 17:10 → TSA 18:45`;
- round-trip airfare: **TWD 9,491**;
- Xiamen Airport's official Wucun / Xiamen Railway Station airport coach: about **25 minutes, CNY 10 each way**;
- required airport transfer: CNY 20 ≈ **TWD 96**;
- **complete effective required transport ≈ TWD 9,587** to the Xiamen Railway Station / Wucun anchor.

Raw destination window is about `67h40m`. Subtracting two 25-minute airport-coach movements gives about **66h50m ground-adjusted usable span**, before standardized airport-process buffers.

The current route page also exposes a slightly cheaper direct `2026-09-20 → 2026-10-03` RT at **TWD 9,459**. Its 13-night length is not a rejection condition.

Sources:

- KAYAK XMN route above.
- https://www.xiamenairport.com.cn/jcjt/jtzy.aspx

### Benchmark result

On a normalized city-anchor basis, **FOC currently wins the direct-air benchmark** in this pass: approximately TWD 9,124 versus TWD 9,587 for the selected short-stay XMN benchmark, while both remain low-friction one-ticket international round trips.

## 3. Kinmen gateway — KHH / TSA → KNH → Shuitou → Xiamen Wutong

Kinmen produces the most tempting partial-cost result, but it does **not** converge to a verified complete itinerary in this run.

Current evidence:

- `KHH-KNH` route-level round-trip estimate: about **TWD 3,694** from recent Skyscanner searches; average flight time about 1h03;
- current August one-way seed: about **TWD 1,779**;
- KNH → Shuitou: official guidance says taxi / car about 15 minutes, or bus via Jincheng and route 7;
- Shuitou ↔ Xiamen Wutong: about **30 minutes**;
- ferry full fare: **TWD 650 + TWD 100 cleaning = TWD 750 each way**;
- Xiamen Airport's official Wutong ↔ airport coach is about **15 minutes / CNY 6**, showing that the Wutong edge is practical, but it does not remove the Kinmen-side exact-fare requirement.

The tempting partial round-trip arithmetic is therefore only:

`KHH-KNH route estimate 3,694 + two ferry fares 1,500 = TWD 5,194`

That is **not** a complete effective transport cost. It still omits an exact target-date domestic-air pair, target-date sailing convergence, Kinmen airport ↔ port fare, and onward Xiamen city-anchor transport for the actual candidate.

More importantly, the official Kinmen Harbor page is monthly. At the time of this run it publishes **August 2026** as the latest timetable. Therefore a September/October/November KNH bargain cannot borrow August sailings. Future-month KNH candidates remain fail-closed until their target month is officially published.

Risk: **medium to high versus direct air** because the itinerary combines separately ticketed domestic air + land transfer + international ferry, and the official local guidance explicitly warns that typhoon, fog, or strong wind can alter or cancel sailings.

Result: **exploratory / incomplete**. Complete effective cost, usable time, savings per extra transport hour, and exact benchmark delta remain unknown rather than guessed.

Sources:

- https://www.skyscanner.com.tw/routes/khh/knh/kaohsiung-to-kinmen.html
- https://harbor.kinmen.gov.tw/News.aspx?Create=1&n=AEF80E822F444916
- https://harbor.kinmen.gov.tw/News_Content.aspx?Create=1&n=5E0D2C39126B9A02&s=B05269E92001A2A3&sms=B675900615BB79BF
- https://lieyu.kinmen.gov.tw/cp.aspx?Create=1&n=A6488ABECB4F8E7D
- https://www.xiamenairport.com.cn/jcjt/jtzy-wtmt.aspx

## 4. Matsu gateways — MFK / LZN → Fuzhou

Matsu has a stronger future timetable evidence shape than Kinmen: the current Mini Three Links material exposes fixed 2026 operating patterns well beyond the current month.

### MFK / Beigan → Huangqi

Current transport evidence:

- TSA ↔ MFK is a direct domestic-air market; current public route surfaces expose low fare signals, but this pass did not converge a target-date TWD round-trip pair with all downstream components;
- local Matsu bus fare is **TWD 15 per ride** where a usable bus edge applies;
- Beigan Baisha ↔ Huangqi ferry: about **30 minutes**;
- full ferry fare: **TWD 650**, inclusive of the listed ticket / insurance / terminal / cleaning components;
- the published pattern shows two daily directional sailings, with ticketing / reservation rules that require advance handling.

The missing essential component is the **current exact Huangqi → Fuzhou city transfer fare/time matched to the candidate**, together with a converged exact Taiwan domestic-air pair. Therefore no complete total is emitted.

### LZN / Nangan → Langqi

Current transport evidence:

- TSA ↔ LZN direct-air exists; indexed exact-date public results are available, but this pass did not obtain a current target-date TWD itinerary suitable for final normalization;
- Nangan Fuao ↔ Fuzhou Langqi: about **90 minutes**;
- full ferry fare: **TWD 1,000** inclusive of the listed fee components.

Compared with Beigan ↔ Huangqi, the 90-minute ferry creates materially more transport friction before mainland ground transfer is even added. With no complete exact candidate, LZN is currently **dominated as a stress-test gateway shape**, not removed from future search coverage.

Risk for both Matsu paths: **medium to high** because weather, ferry check-in / reservation, domestic-air positioning, and separately ticketed transport layers all compound.

Result: **attempted, incomplete, fail closed** for both MFK and LZN.

Sources:

- https://client.matsu.idv.tw/North-South/index.html
- https://www.matsu-nsa.gov.tw/zh-TW/transport/mini-three-links
- https://www.skyscanner.com.tw/routes/mfk/tsa/matsu-beigan-to-taipei-sung-shan.html
- https://www.skyscanner.com.hk/routes/tsa/lzn/taipei-sung-shan-to-matsu.html

## 5. Fujian second city — Xiamen ↔ Fuzhou rail versus domestic air

The transport graph strongly prefers rail for Xiamen ↔ Fuzhou:

- Xiamen North → Fuzhou South public rail surface: roughly **238 trains/day**, fastest about **57 minutes**, route fare around **TWD 371** second class;
- the broader corridor reports roughly 200+ daily trains and a **15-day sales window**;
- XMN ↔ FOC also has direct domestic flights, but the flight itself is around one hour and necessarily adds airport access, check-in, security, and waiting friction.

The run deliberately retried rail inside the 15-day sale window, but the public Web surface still did not expose a sufficiently target-date-specific inventory / seat result to promote a multi-city candidate to final verification. That is an evidence-availability failure, not permission to reuse a route-level fare as an exact target-date ticket.

Result:

- **rail / HSR is the preferred second-city edge** on practical friction;
- exact complete two-city cost remains **unknown** until target-date rail inventory is surfaced;
- the domestic-flight alternative is structurally valid but currently dominated on time friction and also lacked a better exact target-date price case.

Sources:

- https://www.trip.com/trains/china/route/xiamen-north-to-fuzhou-south/
- https://www.trip.com/trains/china/route/xiamen-to-fuzhou/
- https://www.directflights.com/XMN-FOC

## 6. Open-jaw stress case

A live air-only skeleton does exist:

- current KAYAK `TSA → FOC` one-way: **TWD 4,158** on 2026-09-13;
- current KAYAK `XMN → TSA` one-way: **TWD 5,520** on 2026-10-02;
- airfare subtotal: **TWD 9,678**.

This would create the topology:

`TSA → FOC → [Fujian rail / second-city movement] → XMN → TSA`

But the rail movement for a practical target day in that future window is not yet inside a revalidatable sales window, so the open-jaw candidate **fails closed**. It is invalid to append the route-level TWD 371 rail fare and call TWD 10,049 a complete current itinerary.

Result: **open-jaw topology survives; current complete effective cost and usable time remain unknown**.

Source:

- https://www.tw.kayak.com/%E8%88%AA%E7%8F%AD/%E5%BB%88%E9%96%80%E6%A9%9F%E5%A0%B4-XMN/%E5%8F%B0%E5%8C%97%E6%9D%BE%E5%B1%B1-TSA

## Live comparison

| Pattern | Complete effective transport cost | Ground-adjusted usable time | Extra required transport | Transfer risk | Current exact revalidation | Decision |
|---|---:|---:|---:|---|---|---|
| TSA→FOC direct RT 08/21→08/26 | **~TWD 9,124** to Fuzhou Railway Station | **~119h49m** before standardized airport-process buffers | benchmark | low | exact airport/date/time public airfare + current airport rail fare/time | **best normalized complete benchmark** |
| TSA→XMN direct RT 09/01→09/04 | **~TWD 9,587** to Xiamen Station/Wucun | **~66h50m** before standardized airport-process buffers | benchmark | low | exact airport/date/time public airfare + current airport coach fare/time | complete benchmark; loses to FOC on cost in this pass |
| KHH→KNH→Xiamen | **unknown**; partial floor ~TWD 5,194 before required transfers | unknown | at least domestic-air + airport-port + 30m ferry + mainland transfer | medium-high | August timetable exists, but complete exact target-date chain did not converge | exploratory only |
| TSA→MFK→Huangqi→Fuzhou | unknown | unknown | domestic-air + local transfer + 30m ferry + Huangqi-Fuzhou transfer | medium-high | ferry fare/pattern current; exact positioning + mainland transfer incomplete | exploratory only |
| TSA→LZN→Langqi→Fuzhou | unknown | unknown | domestic-air + local transfer + 90m ferry + Langqi-Fuzhou transfer | medium-high | ferry fare/pattern current; exact positioning + mainland transfer incomplete | exploratory; currently higher friction than MFK |
| XMN↔FOC HSR second-city edge | unknown exact candidate | unknown | ~57m rail each direction plus stations | low-moderate | route edge current; target-date inventory not sufficiently surfaced | preferred edge, not final-verified |
| XMN↔FOC domestic flight | unknown exact candidate | unknown | flight + two airport processes/access legs | moderate | topology/schedule exists; no superior exact target-date price case | dominated by rail in this run |
| FOC-entry → rail → XMN-exit open jaw | unknown; exact air subtotal TWD 9,678 | unknown | one Fujian rail movement + station transfers | low-moderate if rail fixed | both air legs exact-public-fare; essential rail target date unresolved | exploratory only |

## Result

1. **TSA is the strongest current Taiwan origin for Fujian direct-air discovery** in this pass, with fresh one-way public-fare signals around TWD 4.16k to both FOC and XMN.
2. The cheapest normalized complete conventional benchmark found is **TSA-FOC 08/21→08/26 at about TWD 9,124 including airport rail to Fuzhou Railway Station**.
3. Mini Three Links can look dramatically cheaper on partial sticker arithmetic, especially KNH, but **none of KNH / MFK / LZN produced a complete exact end-to-end candidate in this run**. They therefore cannot outrank direct air yet.
4. Kinmen has a specific horizon problem: its official timetable is monthly and currently only covers August. A future-month gateway fare must not borrow the August ferry schedule.
5. Matsu has stronger forward schedule evidence, but exact Taiwan positioning plus mainland port-to-city transfer still prevented complete normalization.
6. Xiamen ↔ Fuzhou rail is decisively the right second-city transport shape on friction, but route-level frequency/fare does not substitute for target-date inventory.
7. The open-jaw air legs can both be priced, but the essential future rail component cannot yet be exact-revalidated; fail closed.
8. Return-window behavior is confirmed again: low direct RT observations at 13–17 nights remain eligible evidence and are not rejected merely because they exceed a preferred stay window.
9. **No SSOT / code / test change is justified by this run.** The existing `flight-radar.yaml` and `docs/china-routing.md` already encode every behavior the live evidence required: current component revalidation, complete-cost normalization, advisory return windows, ferry live-status requirements, second-city edge verification, and fail-closed handling.

## Next atomic operational package

The highest-value next stress test is **gateway convergence inside the ferry/rail booking windows**, not new crawler infrastructure:

- choose one August KNH date pair with officially published August sailings and force every Kinmen-side transfer fare/time plus Wutong→Xiamen anchor to convergence;
- choose one MFK date pair and force TSA↔MFK + Baisha↔Huangqi + Huangqi→Fuzhou to convergence;
- force one XMN↔FOC target-date rail search inside the 15-day sales window;
- compare those complete candidates directly against a same-date direct-air benchmark;
- only if public Web still cannot expose the exact component should the next package evaluate a narrow deterministic acquisition adapter for that one missing surface.

No daemon, scheduler, queue, persistent Actions state, or speculative city whitelist is warranted by this stress test.
