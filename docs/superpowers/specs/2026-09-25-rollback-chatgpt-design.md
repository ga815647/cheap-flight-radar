# Rollback to ChatGPT Operation — Design Spec

**Status:** proposed, awaiting owner review.
**Decisions recorded:** 2026-09-25 — local OpenChamber loop disabled (PR #88);
rollback target is the pre-2026-09-18 ChatGPT-trigger + GitHub Actions architecture;
JSON snapshots are the history substrate (no Neon/SQLite for now);
backfill covers 27 canonical Git-era days + 8 local days; observation-source
expansion is out of scope.

## 1. Goal and non-goals

Restore routine Daily Radar operation to ChatGPT control: the ChatGPT automation
(`Daily Flight Radar`) submits one canonical request per Taipei day on the control
branch, GitHub Actions executes acquisition, immutable evidence lands in the repo,
ChatGPT reads it back and notifies per `PRODUCT_INTENT.md`. History-derived
baselines are promoted from supplemental display to the primary typical-price
source (with external fallback). The local box keeps nothing on a timer afterward.

Non-goals: adding observation providers or changing typical-price accuracy by
source; Neon/Postgres/SQLite; synthetic backfill (still forbidden); automated
booking; any change to Deal scoring beyond the typical-price source switch in §3.

## 2. Read contract (JSON as the query layer)

- Snapshot path (frozen, identical in both eras):
  `data/price-history/YYYY/MM/DD/{radar_run_id}.json`, schema_version 1.
- Observation contract (frozen, 16 fields incl. `radar_run_id`, `observed_at`,
  `origin`, `destination`, `trip_type`, `departure_date`, `source_id`,
  `original_currency`, `original_price`, `normalized_twd_price`,
  `availability_state`, `verification_state`): any file failing
  `snapshot_from_json` validation is excluded and stays `unknown`.
- Readers use existing derivation only: `snapshot_from_json` +
  `compare_with_history` with the `price_history` policy in `flight-radar.yaml`.
  No new query service, no index; full scan each run (fine at ~35 days, revisit
  past ~3 years).
- In the restored GitHub layout the history root is the repo root, i.e. readers
  open `data/price-history/**` and `data/run-evidence/**` from checkout; the
  local `{CFR_LOCAL_ROOT}/history` tree is left untouched as archive.

## 3. Promotion: history baseline becomes primary typical-price

SSOT deltas in `flight-radar.yaml` under `price_history`:

- `role: supplemental_evidence_and_fallback_anomaly_truth` →
  `role: primary_history_baseline_with_external_fallback`.
- New rule `primary_typical_price_source`: when a current observation's
  `compare_with_history` result has `selected_baseline_twd` non-null AND
  `confidence` in `{low, medium, high}` (≥3 comparable samples), that baseline
  is the typical price for anomaly magnitude
  (`percentage_below_baseline = (baseline-current)/baseline*100`).
  When baseline is null or confidence is `none`/`sparse`, fall back to the
  existing `external_anomaly_truth.priority` order
  (`google_flight_deals` → `google_flights_exact_price_insight`) with
  `conflict_resolution: explicit_source_priority_never_average` unchanged.
- `required_for_formal_deal` stays `false`: history never blocks a Deal that
  the external path qualifies; sparse history yields low-confidence display,
  never an invented percentile (existing `sparse_history_action` unchanged).
- Explainability is already rendered (sample count, confidence, window days on
  the site pages); promotion adds the source tag (history vs external) next to
  each shown baseline. No scoring-formula change beyond the source switch.

## 4. Backfill: 27 + 8 days of observed evidence

- Scope: 27 `Persist canonical Radar evidence` commits (2026-08-15～09-10,
  `data/price-history` + `data/run-evidence` trees) + operator evidence commits
  in the same span (policy: operator snapshots are additional immutable
  history) + the 8 local snapshots (09-18～09-25) copied byte-identical out of
  `{CFR_LOCAL_ROOT}/history/data/price-history`.
- Gap 09-11～09-17 (7 days, failed/probation period) is accepted as sparse;
  `never_impute_missing_window` already covers it. Expected effect: steady
  routes reach ~30 comparable samples (medium confidence, percentile and
  historical_floor gates at ≥10 pass); thin routes stay low/sparse with
  external fallback per §3.
- Validation before merge (all must pass): every backfilled snapshot loads via
  `snapshot_from_json`; per-destination-bucket sample inventory is published in
  the PR; any file failing validation is excluded, never repaired in place.

## 5. Rollback execution

- Restore the 5 workflows deleted in `2f3e131` from `2f3e131^`
  (`canonical-production-radar.yml`, `canonical-production-radar-test.yml`,
  `operator-production-radar.yml`, `radar-pages.yml`, `radar-pages-isolated-test.yml`).
  The evidence commits prove these workflows wrote repo-root `data/` trees, so
  restore verbatim first and verify the history-root handling matches §2;
  adapt only on mismatch.
- SSOT (`flight-radar.yaml`): restore the pre-decoupling `persistence` and
  `orchestration` blocks from `2f3e131^:flight-radar.yaml`, then apply §3 deltas
  plus `history_root_absent_action: initialize_empty_history_without_backfill` →
  load committed history (backfill in §4 is observed evidence, not synthetic, so
  `synthetic_backfill: forbidden` still holds) and revisit
  `github_actions_is_not_durable_history_service: true` (it must become false if
  the repo tree is the durable store again — explicit decision, no silent keep).
- Finish the local decommission per `docs/superpowers/plans/2026-09-25-cancel-daily-radar.md`
  (UI-trash card deletion + sync-branch cleanup).
- ChatGPT trigger: un-retire `docs/daily-flight-radar-automation-prompt.md` into
  the restored flow (control branch `ops/radar-request`, `requests/daily.json`
  with `schema_version: 1`, `mode: canonical_daily`, `requested_date` = Taipei
  date; one claim per day; request submission is not completion — read back
  claim, snapshot, run-result, recovery manifest, publication manifest before
  any notification decision).
- `chatgpt-instructions.md` (new, repo root): minimal complete revision of the
  retired prompt for the restored architecture, ≤2000 Unicode chars per the
  project-sync budget (build commands, SQL details and deploy todos stay out).
  Owner pastes it into ChatGPT Project settings and confirms; local file alone
  is "locally updated", never "installed".
- Proof: the first ChatGPT-triggered canonical run reaches terminal state with
  the full evidence chain; no manual reacquisition is used for verification
  (claim discipline: one canonical attempt per Taipei day).

## 6. Risks

- GitHub egress 429s: the GitHub era had 429 days too; sticky-429 handling and
  the single-claim fail-closed rule are unchanged, so a bad day degrades, never
  double-acquires.
- Old-evidence methodology drift: mitigated by §4 validation (schema + contract
  gate); anything non-conforming stays out.
- Secret handling in restored workflows: reuse the pre-decoupling pattern only;
  no new secret values are introduced by this spec (history needs none).
