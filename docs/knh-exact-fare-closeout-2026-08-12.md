# KNH exact-fare closeout — 2026-08-12

Observed closeout: `2026-08-12T12:01:29+08:00`.

Baseline main: `17bddcd990311f24b64c092bb536880265c52fd0`.

This package is a narrow continuation of `docs/fujian-gateway-convergence-closeout-2026-08-12.md`. It does **not** repeat the Fujian broad search. The target is fixed to Taiwan → Kinmen → Xiamen on `2026-08-20`, returning Xiamen → Kinmen → Taiwan on `2026-08-23`.

## 1. Evidence contract

The current SSOT already says short taxi-equivalent local access is excluded from comparative cost and comparative transport time. Therefore:

- KNH ↔ Shuitou and Wutong ↔ Xiamen local access need only practical connection feasibility;
- no exact taxi fare or exact taxi minutes are required or inserted into comparison math;
- domestic air, cross-strait ferry, and the same-date direct-air benchmark remain material components;
- every material exact-current unknown fails closed rather than being guessed or reconstructed from route floors;
- no CAPTCHA bypass, Turnstile-token synthesis, stealth/fingerprint spoofing, proxy rotation, or residential proxy is allowed.

No SSOT rule changed in this package. The result below is new target-date evidence, not a normalization-policy change.

## 2. Inherited official small-three-links evidence

The preceding convergence closeout visually verified the Taiwan Maritime and Port Bureau August 2026 Kinmen ↔ Xiamen Wutong timetable PDF. Both `2026-08-20` and `2026-08-23` show twelve departures in each direction at:

`08:30, 09:00, 10:00, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:30, 17:00, 17:30`.

The current public full-fare passenger component is TWD 650 plus the TWD 100 terminal-cleaning charge, i.e. **TWD 750 one way** for the Taiwan-paid full-fare case. This remains a material priced ferry component, but no partial cost total is promoted because the complete chain fails closed below.

The local KNH ↔ Shuitou and Wutong ↔ Xiamen access legs are practically ordinary short local transfers. Their exact taxi price/minutes are deliberately not acquired and are not comparative components.

## 3. Mandarin Airlines official target-date acquisition

A branch-only vanilla-Playwright probe used the normal Mandarin Airlines booking UI. The form contains a Cloudflare Turnstile field, but the probe did not touch or synthesize that field, did not bypass any challenge, and used no stealth/proxy behavior. Normal browser selection + search returned the public flight-result page without a challenge.

This is sufficiently deterministic to read the official target-date flight list, but it does **not** justify retaining a production adapter: the required itinerary is currently unavailable and the project explicitly avoids generic crawler infrastructure without a live blocker that needs it. The temporary probe script/workflow is removed before PR finalization.

### 2026-08-20 outbound — KHH → KNH

| Flight | Time | Public fare field | Booking state | Same-day ferry use |
|---|---|---:|---|---|
| AE-301 | 07:20→08:25 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-303 | 10:15→11:20 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-307 | 13:30→14:35 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-309 | 17:15→18:20 | `--` | buy | arrives after the 17:30 final ferry |
| AE-311 | 18:50→19:55 | TWD 2,138 from; resident TWD 1,388 from | buy | arrives after the 17:30 final ferry |

### 2026-08-20 outbound — TSA → KNH

| Flight | Time | Public fare field | Booking state | Same-day ferry use |
|---|---|---:|---|---|
| AE-1261 | 06:40→08:00 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1267 | 06:50→08:10 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1263 | 08:10→09:30 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1265 | 10:20→11:40 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1269 | 11:50→13:10 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1271 | 13:55→15:15 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1273 | 14:40→16:00 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1277 | 17:30→18:50 | `--` | waitlist | too late for the final ferry |
| AE-1275 | 18:05→19:10 | `--` | buy | too late for the final ferry |
| AE-1279 | 18:25→19:45 | TWD 2,288 from; resident TWD 1,388 from | buy | too late for the final ferry |

**Outbound conclusion:** every Mandarin flight early enough to feed a same-day small-three-links sailing is currently waitlisted. The only currently buyable flights reach Kinmen after the final `17:30` sailing. There is therefore no material exact fare to acquire for a usable Mandarin outbound: the candidate fails on current availability first.

### 2026-08-23 return — KNH → KHH

| Flight | Time | Public fare field | Booking state | Same-day ferry use |
|---|---|---:|---|---|
| AE-302 | 09:00→10:00 | `--` | buy | cannot follow the day's first 08:30 Wutong sailing plus local port→airport transfer |
| AE-304 | 12:05→13:05 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-308 | 15:10→16:10 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-310 | 19:15→20:15 | `--` | waitlist | schedule-connectable, but not currently buyable |

### 2026-08-23 return — KNH → TSA

| Flight | Time | Public fare field | Booking state | Same-day ferry use |
|---|---|---:|---|---|
| AE-1262 | 08:35→09:45 | `--` | buy | earlier than a passenger can arrive from the first 08:30 Wutong sailing |
| AE-1264 | 10:05→11:15 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1266 | 12:15→13:25 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1270 | 13:50→15:00 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1272 | 15:50→17:00 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1274 | 16:40→17:50 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1278 | 19:30→20:40 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1276 | 20:00→21:00 | `--` | waitlist | schedule-connectable, but not currently buyable |
| AE-1280 | 20:20→21:30 | `--` | waitlist | schedule-connectable, but not currently buyable |

**Return conclusion:** the only currently buyable Mandarin return flights are too early to follow the day's first Wutong → Kinmen sailing. Every later flight that could fit the return topology is waitlisted.

Deterministic run evidence:

- outbound normal-browser target-date probe: GitHub Actions run `31561526012`, successful;
- return normal-browser target-date probe: GitHub Actions run `31561719103`, successful;
- temporary artifacts were retained only for short-lived evidence review and are not project state.

## 4. UNI Air — exact-public evidence boundary

UNI Air's official booking surface requires CAPTCHA interaction. This package does not bypass it.

Focused public indexing did expose target-date examples, but not the one material missing outbound component:

- KHH → KNH on `2026-08-20`: public indexed exact-date buyable examples surface in the late afternoon/evening (including a 17:25→18:30 flight), too late for the `17:30` final ferry;
- TSA → KNH on `2026-08-20`: public indexed exact-date buyable examples include 18:20→19:25 and later, also too late;
- KNH → KHH on `2026-08-23`: a public indexed 10:30→11:30 one-way result exposes an exact current fare of OMR 19.

No public result acquired in this focused package ties an **early, same-day-ferry-connectable `2026-08-20` UNI outbound** to both current buyability and an exact current fare. The official surface cannot be deterministically queried without CAPTCHA interaction, so the correct state is **unknown**, not an inference that all UNI morning seats are sold out.

This is the remaining material domestic-air blocker for the KNH candidate.

## 5. Same-date direct-air benchmark revalidation

The direct KHH ↔ XMN topology remains real on the target days: public current surfaces expose a direct `2026-08-20` KHH → XMN outbound and direct `2026-08-23` XMN → KHH return options.

However, this package did **not** acquire one admissible exact-current **`2026-08-20 → 2026-08-23` round-trip total**. Current public evidence includes target-date one-way / paired-search signals, but stitching unlike search contexts into a synthetic round-trip price would violate the exact-evidence contract.

Explicitly excluded as benchmark substitutes:

- a current KHH → XMN `2026-08-20` one-way floor of US$ 143 because the indexed route page's carrier/schedule presentation is not internally clean enough to promote into the final pair;
- a current XMN → KHH `2026-08-23` one-way XiamenAir result of THB 5,750 because it is a different one-way search context;
- a current official KHH ↔ XMN `2026-08-20 → 2026-08-24` round-trip from TWD 10,230 because the return date is wrong by one day;
- a public `2026-08-16 → 2026-08-23` round-trip around US$ 277 because the outbound date is wrong.

**Benchmark state:** target-day direct-flight feasibility revalidated; exact same-date round-trip benchmark total remains material exact-missing.

## 6. Fail-closed result

Status: **FAIL_CLOSED**.

Material blockers:

1. `2026-08-20` early UNI TSA/KHH → KNH current buyability + exact fare is still unknown; the official surface is CAPTCHA-gated and public indexing only closed late flights.
2. the exact-current same-date `2026-08-20 → 2026-08-23` Taiwan → XMN direct-air round-trip benchmark total was not acquired.

Separately, Mandarin is no longer an unknown: its target-date official result is a verified **availability/timing failure** for this small-three-links chain in both directions.

Per the SSOT, no partial sticker arithmetic is promoted to a deal score:

| Field | Result |
|---|---:|
| Complete effective transport cost | N/A |
| Usable time | N/A |
| Extra transport time | N/A |
| Formal normalized risk | N/A |
| Savings vs same-date direct air | N/A |
| Savings per extra transport hour | N/A |

Known qualitative risk signals remain ferry/weather interruption, split-ticket/self-connect exposure, and severe target-date domestic seat pressure, but those signals are not converted into a formal score while the candidate is incomplete.

## 7. Repository / acquisition decision

- **SSOT unchanged:** the existing short-local-access and fail-closed rules already model this case correctly.
- **Tests unchanged:** there is no behavior/specification change to encode.
- **No generic crawler added.**
- The Mandarin official flight-list surface proved readable through ordinary browser interaction, but there is no live usable candidate that justifies retaining an adapter; the temporary branch-only probe is removed.
- UNI CAPTCHA is treated as a stop condition, not a reason to add bypass machinery.
- No price-history observation is written because there is no `usable_complete_trip` observation.

The next KNH revisit should be event-driven or date-shifted: only retry when a public/official surface can supply a currently buyable early `2026-08-20`-equivalent UNI outbound (or when the target dates are intentionally changed), then acquire the exact same-date direct-air benchmark before computing savings.