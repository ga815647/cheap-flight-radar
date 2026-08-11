# China mixed-routing deep-radar — 2026-08-11

Observed window: 2026-08-11 evening, Asia/Taipei.

## Scope

This is a targeted live China specialist run after the return-window correction. It tests the routing shape:

```text
Taiwan cheap entry → mainland gateway → verified HSR / domestic flight / rail → second city → same-gateway return or open-jaw exit
```

The run prioritizes the prior `KHH-PVG ~TWD 4,755 / 7 nights` seed, but does not retroactively turn that seed into a current/history observation. Public fare-index and route-page prices remain discovery/revalidation evidence rather than checkout guarantees; baggage/fare-family semantics remain unknown where the source does not expose them.

All TWD normalizations for CNY components below use Land Bank of Taiwan's observed CNY spot sell rate `4.807 TWD/CNY` on this run. Rounded totals are comparison aids, not extra fare precision.

## 1. KHH → PVG seed revalidation

The old ~TWD 4,755 route-floor seed did **not** reappear on current exact surfaces.

Current exact evidence repeatedly exposed Spring Airlines `KHH-PVG`, `2026-10-02 → 2026-10-11`, at approximately TWD 6,987–7,005 round trip. The lowest exact observation retained in this run is **TWD 6,987**.

This is about **46.9% above** the old 4,755 seed, so 4,755 must not be described as a current fare.

The corrected return-window semantics materially change the result: the 9-night `10/02 → 10/11` pair at TWD 6,987 was cheaper than the 7-night `10/02 → 10/09` pair at about TWD 7,144–7,171 and the 5-night `10/02 → 10/07` pair around TWD 7,010. A hard `max_nights` rejection would therefore discard the better current fare.

Current Spring Airlines schedule evidence for the exact travel days gives `9C8878 KHH 18:15 → PVG 20:35` and `9C8877 PVG 14:55 → KHH 17:15`. The raw PVG-arrival → PVG-departure destination window is therefore about **210h20m** before required ground transport and airport-process buffers.

Sources:
- https://www.expedia.com.tw/lp/flights/khh/pvg/kaohsiung-to-shanghai?flightType=ONE_WAY
- https://www.expedia.com.tw/en/lp/flights/khh/sha/kaohsiung-to-shanghai?flightType=MULTI_CITY
- https://en.ch.com/flights/flight-date/num-9C8878/
- https://en.ch.com/flights/flight-date/num-9C8877/

## 2. Same-city Shanghai benchmark

Use the exact KHH-PVG TWD 6,987 airfare as the conventional round-trip benchmark.

Shanghai Pudong Airport → People's Square on Metro Line 2 is about 60 minutes and CNY 7 each way. Required airport transfer therefore adds about CNY 14 / TWD 67.

Approximate complete required transport cost for the simplest Shanghai-only benchmark:

- airfare: TWD 6,987;
- required PVG ↔ central-Shanghai metro: CNY 14 ≈ TWD 67;
- **effective required transport ≈ TWD 7,054**.

Using only source-backed required ground time, the 210h20m raw destination window loses about two hours to PVG ↔ central-Shanghai metro, leaving roughly **208h20m of ground-adjusted usable destination span**. Immigration, check-in, security, and discretionary local transport are not silently guessed here; a production ranking may subtract standardized verified airport-process buffers separately.

Normal city sightseeing transport and normal hotels are excluded by SSOT. Checked baggage remains unknown unless required by the trip.

Source:
- https://www.shanghai-airport.com/metro.php

## 3. Gateway + HSR: Shanghai / PVG → Hangzhou

This is the strongest **normalized** mixed expansion in this run.

Current rail references show Shanghai Hongqiao → Hangzhou East has 100+ daily trains, generally around 45–70 minutes, with a common second-class fare around CNY 73. A 2026 timetable reference shows service extending late into the evening, but the candidate should not rely on a tight same-night self-transfer after the evening KHH arrival. The practical low-risk shape is to treat Shanghai as a real first stop, then continue to Hangzhou and return toward PVG with adequate buffer before the Taiwan flight.

One practical two-city cost model:

- KHH-PVG round trip: TWD 6,987;
- PVG → central Shanghai: CNY 7;
- central Shanghai → Hongqiao rail station: about CNY 6;
- Shanghai → Hangzhou HSR: CNY 73;
- Hangzhou → Shanghai HSR: CNY 73;
- Hongqiao → PVG: about CNY 9;
- required China transport subtotal: about CNY 168 ≈ TWD 808;
- **effective required transport ≈ TWD 7,795**.

This is only about **TWD 740 more** than the Shanghai-only benchmark while adding a genuine second city. Required transport time is roughly 4–5 hours more than the simplest Shanghai-only airport-transfer benchmark once rail-station access and a practical station buffer are counted. Against the same 210h20m raw destination window, that leaves roughly **203–204h of usable destination span** after required ground/rail movement, before standardized airport-process buffers.

Risk is **low to moderate** if the return rail segment reaches Shanghai with generous buffer / a prior-night Shanghai stay. A tight same-day rail → separately ticketed international flight should be penalized more heavily.

The HSR corridor, route time and current fare level are verified transport-edge evidence; the exact October target-date train/seat still requires final live revalidation when that date can be searched. Therefore this is the best current mixed-routing candidate, **not yet a fully final-verified October rail booking**.

Sources:
- https://chinarailguide.com/routes/shanghai-to-hangzhou/
- https://www.travelchinaguide.com/china-trains/high-speed/shanghai-hangzhou.htm
- https://www.shanghai-airport.com/metro.php

## 4. Gateway + HSR: Shanghai / PVG → Nanjing

Nanjing is also a valid transport-edge candidate, but it loses to Hangzhou in this run.

Current references show 300+ Shanghai–Nanjing high-speed train pairs, a shortest trip around 59 minutes, and second-class fares from about CNY 104. Using the same gateway logic, the rail component alone costs at least about CNY 208 round trip before station/airport metro.

The complete route therefore lands around **TWD 8.1k** using the same KHH-PVG airfare and required Shanghai transfer model, while adding more cost and at least comparable transport friction. Ground-adjusted usable time is roughly in the same ~203h class as Hangzhou but with a higher transport bill; exact target-date rail still needs final live revalidation. Nanjing is therefore a valid expansion but currently dominated by Hangzhou.

Source:
- https://www.travelchinaguide.com/china-trains/high-speed/shanghai-nanjing.htm

## 5. Gateway + mainland domestic flight: Shanghai → Wuhan

This branch did not pass final exact-date revalidation.

Current Trip.com route evidence shows Shanghai–Wuhan nonstop flights around 1h54m average and a rolling route floor of about USD 113 round trip, with October showing low one-way examples. At Land Bank's observed USD spot sell rate `32.295 TWD/USD`, USD 113 is about TWD 3.65k **before** Shanghai/Wuhan airport transfers and additional check-in/wait time.

Even before those missing required components, combining that route-floor domestic return with the KHH-PVG gateway airfare pushes the airfare-only combination above TWD 10.6k. It also adds materially more required transport time and a separately ticketed connection surface than Hangzhou HSR.

Because the public result did not establish the exact `2026-10-02 → 2026-10-11` domestic component or enough target-date transfer detail to normalize usable time, both current exact complete cost and usable time remain **unknown**. This branch is exploratory, not a verified finalist.

Source:
- https://www.trip.com/flights/shanghai-to-wuhan/airfares-sha-wuh/

## 6. Open-jaw exit: PVG gateway → Nanjing → KHH

Nanjing can structurally serve as an open-jaw exit, but the current target-date exit fare did not converge.

Public route evidence exposed NKG-KHH one-way floors around TWD 4,761–5,318 on other dates, but did not establish an exact current `2026-10-11` NKG-KHH one-way fare. It would be invalid to divide a round-trip fare by two or reuse an unrelated-date headline as the exit component.

Result: **exploratory / final revalidation failed**. Complete effective cost and usable time remain unknown because the essential target-date exit component is unresolved. The routing topology survives; the price does not.

Source:
- https://www.expedia.com.tw/en/lp/flights/nkg/khh/nanjing-to-kaohsiung?flightType=ONE_WAY

## 7. Kinmen gateway attempt

Kinmen was attempted as required by the China specialist coverage model rather than assumed to be cheaper.

Current Taiwan fare evidence shows KHH-KNH round-trip floors around **TWD 4,522**. The official Kinmen tourism source currently states:

- KNH ↔ Kinmen port taxi: about 20 minutes;
- Kinmen ↔ Xiamen ferry: about 30 minutes;
- Kinmen ↔ Quanzhou ferry: about 70 minutes;
- Kinmen-origin full fare: TWD 650 one way;
- non-Kinmen passenger service fee: TWD 160;
- ferry operation may change in typhoon/fog/strong-wind conditions and must be reconfirmed.

So the KHH→KNH positioning airfare plus only the outbound ferry/fee is already about TWD 5.3k before the return ferry, airport-port transfers, exact target-date sailing match, and mainland onward transport are normalized.

Kinmen remains a potentially valuable **Xiamen/Quanzhou gateway**, especially when mainland direct air is expensive, but this pass did not establish a complete target-date end-to-end candidate that beats the PVG/Hangzhou branch. Complete effective cost and usable time therefore remain unknown; it is attempted but exploratory, not a verified finalist.

Sources:
- https://www.expedia.com.tw/en/lp/flights/khh/knh/kaohsiung-to-kinmen-island?flightType=ONE_WAY
- https://www.kinmen.travel/zh-tw/information/kinmen

## 8. Matsu gateway attempt

Matsu was also attempted for China-mode coverage.

The current Matsu National Scenic Area page confirms the active topology and operating pattern:

- Nangan Fuao ↔ Fuzhou Langqi: about 90 minutes;
- Beigan Baisha ↔ Fuzhou Huangqi: about 30 minutes;
- Huangqi service shown as year-round;
- ticketing/check-in must be completed before sailing and current operation must still be checked.

This run did not establish a defensible exact Taiwan→MFK/LZN positioning fare plus target-date ferry/return combination inside the radar horizon. Complete effective cost and usable time remain unknown. The Matsu branch is therefore **attempted but incomplete/exploratory**; no missing component is invented.

Source:
- https://www.matsu-nsa.gov.tw/zh-TW/transport/mini-three-links

## Live comparison

| Pattern | Current complete effective transport | Ground-adjusted usable span | Extra required transport vs Shanghai-only | Transfer risk | Current exact revalidation | Run decision |
|---|---:|---:|---:|---|---|---|
| KHH-PVG same-city round trip | ~TWD 7,054 | ~208h20m | benchmark | low | exact 10/02→10/11 air + current transfer reference | cheapest complete benchmark |
| PVG gateway + Hangzhou HSR + PVG return | ~TWD 7,795 | ~203–204h | ~4–5h | low–moderate with buffer | exact gateway air; route-level rail/transfer edge current, target-date rail final check pending | **best normalized mixed expansion** |
| PVG gateway + Nanjing HSR + PVG return | ~TWD 8.1k | ~203h class | comparable/slightly higher | low–moderate with buffer | exact gateway air; route-level rail edge current, target-date rail final check pending | valid but dominated by Hangzhou |
| PVG gateway + Wuhan domestic flight | >TWD 10.6k airfare-only before missing transfers | unknown | materially higher | moderate separate-ticket | exact target-date domestic component missing | exploratory only |
| PVG → Nanjing → KHH open-jaw | unknown | unknown | unknown | unknown until exit fixed | exact target-date NKG-KHH exit missing | exploratory only |
| KHH → KNH → Xiamen/Quanzhou | unknown complete total | unknown | high gateway friction | medium ferry/separate-ticket | current positioning/ferry topology, incomplete target-date end-to-end | exploratory only |
| Matsu → Fuzhou | unknown | unknown | unknown | ferry-dependent | topology/schedule evidence, Taiwan positioning incomplete | exploratory only |

## Result

1. The old KHH-PVG ~TWD 4,755 seed is **not current**; keep it only as prior benchmark provenance, without synthetic history backfill.
2. The best current exact KHH-PVG pair found is around **TWD 6,987 for 9 nights**, which directly proves that `return_windows.max_nights` cannot be a hard rejection gate.
3. **PVG should be treated as a gateway.** Hangzhou HSR is the clearest current mixed expansion: roughly TWD 7.8k effective required transport, ~203–204h ground-adjusted usable span, and only ~TWD 740 above the Shanghai-only benchmark. Exact October rail availability still requires final target-date revalidation.
4. Domestic-flight and open-jaw branches remain eligible search patterns, but this run correctly stops when exact target-date components fail revalidation.
5. Kinmen and Matsu were attempted for China-mode coverage; neither is silently omitted or promoted from partial cost.

## Minimal repeatable China mixed-routing flow derived from the run

1. Revalidate the cheap mainland gateway on exact Taiwan airport + exact gateway airport + current date pair.
2. Keep the conventional same-city round trip as the benchmark.
3. Trigger gateway expansion only when a current exact gateway fare and at least one verified practical transport edge exist.
4. Generate second cities from verified HSR/rail/domestic-flight/open-jaw edges, not geographic proximity alone.
5. Prefer HSR when it beats domestic air on complete required time/friction; use domestic air when rail is absent or materially worse.
6. Normalize complete required transport cost, required time, usable time, transfer risk, baggage/fare scope, and verification state.
7. Consider open-jaw exits only with a current exact exit component; never infer one-way price from a round-trip or unrelated date.
8. Stop an expansion when an essential segment cannot be revalidated, complete cost/time cannot be normalized, it is clearly dominated, or the deep-search candidate budget is exhausted.
9. Fail closed: unresolved essential components remain exploratory rather than verified.

This is the decision contract now reflected in `flight-radar.yaml` and `docs/china-routing.md`; it adds no crawler, daemon, scheduler, city whitelist, or durable GitHub Actions state.
