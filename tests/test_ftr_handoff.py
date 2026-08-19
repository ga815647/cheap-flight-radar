import json
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.ftr_handoff import (
    CANONICAL_LATEST_PATH,
    CURRENT_STATUS_PATH,
    FTRHandoffError,
    SCHEMA_VERSION,
    build_snapshot,
    clear_repair_required,
    load_current_reference,
    load_current_status,
    load_manifest_snapshot,
    manifest_repository_path,
    mark_repair_required,
    snapshot_repository_path,
    stage_current_status_from_snapshot,
    stage_snapshot,
    summarize_coverage,
    validate_snapshot,
)


def record(
    record_id,
    *,
    origin="TPE",
    destination="KIX",
    return_gateway=None,
    outbound_date="2026-10-05",
    return_date="2026-10-09",
    price=5000,
    surface="exact",
    observed_at="2026-08-19T08:00:00+08:00",
):
    return_gateway = return_gateway or origin
    if surface == "open_jaw":
        legs = [
            {
                "origin": origin,
                "destination": destination,
                "date": outbound_date,
                "departure_time": "08:00+08:00",
                "arrival_time": "12:00+09:00",
            },
            {
                "origin": destination,
                "destination": return_gateway,
                "date": return_date,
                "departure_time": "13:00+09:00",
                "arrival_time": "15:30+08:00",
            },
        ]
        reproducible = {}
    else:
        legs = [
            {
                "origin": origin,
                "destination": destination,
                "date": outbound_date,
                "departure_time": "08:00+08:00",
                "arrival_time": "12:00+09:00",
            }
        ]
        reproducible = {"return_date": return_date}
    return {
        "record_id": record_id,
        "provider": "gflights",
        "surface": surface,
        "origin": {"iata": origin, "city": origin, "country": "Taiwan"},
        "destination": {"iata": destination, "city": destination, "country": "Japan"},
        "legs": legs,
        "current_price_twd": price,
        "observed_at": observed_at,
        "verification_state": "revalidated",
        "evidence_class": "qualified_round_trip_deal",
        "complete_airfare": True,
        "airlines": ["Example Air"],
        "evidence_url": "https://example.invalid/evidence",
        "reproducible_search": reproducible,
    }


def item(record_payload, *, classification="Deal", state="deal", price=None):
    return {
        "classification": classification,
        "state": state,
        "reason": "fixture",
        "observation_id": "obs-" + record_payload["record_id"],
        "current_complete_airfare_twd": price or record_payload["current_price_twd"],
        "discovery": record_payload,
        "exact": record_payload,
    }


def execution_row(*, attempts=0, records=0, successes=0, empty=0, failures=0, suppressed=0, unsupported=0):
    return {
        "attempts": attempts,
        "provider_calls": attempts - suppressed,
        "records": records,
        "successes": successes,
        "empty": empty,
        "failures": failures,
        "suppressed": suppressed,
        "unsupported": unsupported,
    }


def healthy_execution():
    return {
        "flight_deals": execution_row(attempts=4, records=6, successes=4),
        "explore": execution_row(attempts=4, records=4, successes=4),
        "conventional_exact": execution_row(attempts=1, records=1, successes=1),
        "flexible_dates": execution_row(),
        "mixed_taiwan_return": execution_row(),
        "open_jaw": execution_row(),
    }


def healthy_origins():
    return {
        "TPE": {"status": "attempted", "returned_flight_deals": 2, "explore_seeds": 1, "errors": []},
        "TSA": {"status": "attempted", "returned_flight_deals": 1, "explore_seeds": 1, "errors": []},
        "RMQ": {"status": "attempted", "returned_flight_deals": 1, "explore_seeds": 1, "errors": []},
        "KHH": {"status": "attempted", "returned_flight_deals": 2, "explore_seeds": 1, "errors": []},
    }


def market_rows():
    return {
        "japan": {"discovered": 2, "qualified": 2, "revalidated": 1, "deals": 1},
        "korea": {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0},
        "china": {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0},
        "other_asia_oceania": {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0},
    }


def run_result(
    *,
    deals=(),
    signals=(),
    absolute_low_non_deals=(),
    health="healthy",
    origins=None,
    execution=None,
    markets=None,
    run_id="production-radar-20260819T080000+0800",
    run_at="2026-08-19T08:00:00+08:00",
    provider_failures=None,
):
    reasons = [] if health == "healthy" else ["fixture coverage degradation"]
    return {
        "radar_run_id": run_id,
        "run_at": run_at,
        "deals": list(deals),
        "signals": list(signals),
        "ftr_absolute_low_non_deals": list(absolute_low_non_deals),
        "coverage": {
            "origins": origins if origins is not None else healthy_origins(),
            "markets": markets if markets is not None else market_rows(),
            "execution": execution if execution is not None else healthy_execution(),
            "all_origins_attempted": True,
            "destination_scope": "asia_oceania",
            "provider_health": {
                "status": health,
                "technical_failure_count": 0 if health == "healthy" else 1,
                "reasons": reasons,
            },
        },
        "provider_health": {
            "status": health,
            "technical_failure_count": 0 if health == "healthy" else 1,
            "reasons": reasons,
        },
        "provider_failures": list(provider_failures or []),
    }


def generic_provider_signal(record_id="provider-evidence"):
    return item(record(record_id), classification="Signal", state="weak_seed")


def assert_nested_paths(test_case, payload, paths):
    for path in paths:
        current = payload
        for component in path.split("."):
            test_case.assertIsInstance(current, dict, msg=f"{path}: {component} parent is not an object")
            test_case.assertIn(component, current, msg=f"machine SSOT required path missing: {path}")
            current = current[component]


class FTRHandoffCoverageTest(unittest.TestCase):
    def test_fully_healthy_coverage_is_slice_faithful(self):
        result = run_result(deals=(item(record("deal")),))
        coverage = summarize_coverage(result)
        self.assertEqual(coverage["overall_state"], "complete")
        self.assertEqual(coverage["providers"]["gflights"]["status"], "succeeded")
        self.assertTrue(all(value["status"] == "succeeded" for value in coverage["origins"].values()))
        self.assertTrue(all(value["status"] == "succeeded" for value in coverage["markets"].values()))
        self.assertEqual(coverage["surfaces"]["open_jaw"]["status"], "not_attempted")

    def test_partial_degraded_coverage_is_not_eaten_by_overall_success(self):
        origins = healthy_origins()
        origins["TPE"] = {"status": "degraded", "returned_flight_deals": 0, "explore_seeds": 1, "errors": []}
        result = run_result(
            signals=(generic_provider_signal(),),
            health="degraded",
            origins=origins,
        )
        coverage = summarize_coverage(result)
        self.assertEqual(coverage["origins"]["TPE"]["status"], "failed")
        self.assertEqual(coverage["providers"]["gflights"]["status"], "failed")
        self.assertEqual(coverage["overall_state"], "degraded")
        snapshot = build_snapshot(result, producer_commit_sha="abc123", generated_at="2026-08-19T08:05:00+08:00")
        self.assertEqual(snapshot["coverage_state"], "degraded")
        self.assertEqual(snapshot["freshness_state"], "degraded")

    def test_provider_failed_is_explicit_and_not_consumable(self):
        origins = {
            value: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0, "errors": ["failed"]}
            for value in ("TPE", "TSA", "RMQ", "KHH")
        }
        execution = healthy_execution()
        execution["flight_deals"] = execution_row(attempts=4, failures=4)
        execution["explore"] = execution_row(attempts=4, failures=4)
        failures = [{"provider": "gflights", "surface": "flight_deals", "origin": "TPE", "error": "fixture"}]
        result = run_result(health="provider_failed", origins=origins, execution=execution, provider_failures=failures)
        coverage = summarize_coverage(result)
        self.assertEqual(coverage["overall_state"], "failed")
        self.assertEqual(coverage["providers"]["gflights"]["status"], "failed")
        with self.assertRaisesRegex(FTRHandoffError, "not consumable"):
            build_snapshot(result, producer_commit_sha="abc123", generated_at="2026-08-19T08:05:00+08:00")

    def test_one_failed_origin_slice_remains_failed(self):
        origins = healthy_origins()
        origins["RMQ"] = {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0, "errors": ["fixture"]}
        result = run_result(signals=(generic_provider_signal(),), health="degraded", origins=origins)
        coverage = summarize_coverage(result)
        self.assertEqual(coverage["origins"]["RMQ"]["status"], "failed")
        self.assertEqual(coverage["markets"]["japan"]["status"], "failed")
        self.assertEqual(coverage["overall_state"], "degraded")

    def test_market_and_surface_not_attempted_are_preserved(self):
        markets = market_rows()
        markets["other_asia_oceania"]["status"] = "not_attempted"
        result = run_result(signals=(generic_provider_signal(),), markets=markets)
        coverage = summarize_coverage(result)
        self.assertEqual(coverage["markets"]["other_asia_oceania"]["status"], "not_attempted")
        self.assertEqual(coverage["surfaces"]["open_jaw"]["status"], "not_attempted")
        self.assertEqual(coverage["overall_state"], "degraded")

    def test_unknown_coverage_fails_closed(self):
        origins = healthy_origins()
        origins["TPE"]["status"] = "mystery"
        with self.assertRaisesRegex(FTRHandoffError, "unknown origin coverage state"):
            summarize_coverage(run_result(signals=(generic_provider_signal(),), origins=origins))

    def test_internally_inconsistent_coverage_fails_closed(self):
        origins = healthy_origins()
        origins["TPE"]["status"] = "failed"
        with self.assertRaisesRegex(FTRHandoffError, "healthy provider status contradicts"):
            summarize_coverage(run_result(signals=(generic_provider_signal(),), origins=origins))

        execution = healthy_execution()
        execution["flight_deals"]["provider_calls"] = 5
        with self.assertRaisesRegex(FTRHandoffError, "more provider/suppressed calls than attempts"):
            summarize_coverage(run_result(signals=(generic_provider_signal(),), execution=execution))

    def test_deal_count_never_decides_health_or_coverage(self):
        snapshot = build_snapshot(
            run_result(signals=(generic_provider_signal(),)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(snapshot["candidate_counts"]["deals"], 0)
        self.assertEqual(snapshot["candidate_counts"]["variants"], 0)
        self.assertEqual(snapshot["opportunities"], [])
        self.assertEqual(snapshot["coverage"]["providers"]["gflights"]["status"], "succeeded")
        self.assertEqual(snapshot["coverage_state"], "complete")
        self.assertEqual(snapshot["coverage"]["semantics"], "execution_and_coverage_evidence_not_candidate_or_deal_count")


class FTRHandoffSnapshotTest(unittest.TestCase):
    def test_groups_taiwan_gateway_variants_under_destination_route_shape(self):
        tpe = item(record("tpe-kix", origin="TPE", destination="KIX", price=5000))
        khh = item(record("khh-kix", origin="KHH", destination="KIX", price=4700))
        snapshot = build_snapshot(
            run_result(deals=(tpe, khh)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(len(snapshot["opportunities"]), 1)
        opportunity = snapshot["opportunities"][0]
        self.assertEqual(opportunity["destination_route_shape"], {"arrival_airport": "KIX", "departure_airport": "KIX"})
        self.assertEqual({variant["taiwan_origin_gateway"] for variant in opportunity["variants"]}, {"TPE", "KHH"})
        self.assertEqual(opportunity["variants"][0]["complete_airfare_twd"], 4700)

    def test_destination_side_open_jaw_is_separate_opportunity(self):
        round_trip = item(record("kix-rt", destination="KIX", price=5000))
        open_jaw_record = record("kix-fuk", destination="KIX", return_gateway="TPE", price=5300, surface="open_jaw")
        open_jaw_record["legs"][-1]["origin"] = "FUK"
        snapshot = build_snapshot(
            run_result(deals=(round_trip, item(open_jaw_record))),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        shapes = {
            (value["destination_route_shape"]["arrival_airport"], value["destination_route_shape"]["departure_airport"])
            for value in snapshot["opportunities"]
        }
        self.assertEqual(shapes, {("KIX", "KIX"), ("KIX", "FUK")})

    def test_only_dedicated_selected_absolute_low_state_is_consumed(self):
        generic = item(record("generic-signal", price=4100), classification="Signal", state="exact_revalidated_candidate")
        forged = item(record("forged-in-signal-journal", price=4000), classification="Signal", state="ftr_absolute_low_non_deal")
        selected = item(record("absolute-low", price=4200), classification="Signal", state="ftr_absolute_low_non_deal")
        snapshot = build_snapshot(
            run_result(signals=(generic, forged), absolute_low_non_deals=(selected,)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(snapshot["candidate_counts"]["variants"], 1)
        self.assertEqual(snapshot["candidate_counts"]["absolute_low_non_deals"], 1)
        variant = snapshot["opportunities"][0]["variants"][0]
        self.assertEqual(variant["variant_id"], "absolute-low")
        self.assertEqual(variant["candidate_kind"], "absolute_low_non_deal")

    def test_scoped_manifest_never_moves_canonical_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            canonical = build_snapshot(
                run_result(deals=(item(record("canonical")),)),
                producer_commit_sha="abc123",
                generated_at="2026-08-19T08:05:00+08:00",
            )
            stage_snapshot(history_dir=history, snapshot=canonical)
            latest_before = (history / CANONICAL_LATEST_PATH).read_bytes()
            scoped = build_snapshot(
                run_result(
                    deals=(item(record("scoped")),),
                    run_id="ftr-scoped-20260819T090000+0800",
                    run_at="2026-08-19T09:00:00+08:00",
                ),
                producer_commit_sha="def456",
                mode="scoped_search",
                generated_at="2026-08-19T09:05:00+08:00",
            )
            staged = stage_snapshot(history_dir=history, snapshot=scoped)
            self.assertNotEqual(staged["manifest_path"], CANONICAL_LATEST_PATH)
            self.assertEqual((history / CANONICAL_LATEST_PATH).read_bytes(), latest_before)
            self.assertEqual(staged["manifest_path"], manifest_repository_path(scoped))

    def test_consumer_fails_closed_on_checksum_or_unknown_major(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            snapshot = build_snapshot(
                run_result(deals=(item(record("deal")),)),
                producer_commit_sha="abc123",
                generated_at="2026-08-19T08:05:00+08:00",
            )
            staged = stage_snapshot(history_dir=history, snapshot=snapshot)
            snapshot_file = history / staged["snapshot_path"]
            payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
            payload["candidate_counts"]["variants"] = 999
            snapshot_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FTRHandoffError, "checksum mismatch"):
                load_manifest_snapshot(history_dir=history)

            unsupported = dict(snapshot)
            unsupported["schema_version"] = "3.0"
            with self.assertRaisesRegex(FTRHandoffError, "unsupported schema major"):
                validate_snapshot(unsupported)

    def test_stale_reference_is_forbidden_inside_immutable_snapshot(self):
        snapshot = dict(build_snapshot(
            run_result(deals=(item(record("deal")),)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        ))
        snapshot["freshness_state"] = "stale_reference"
        with self.assertRaisesRegex(FTRHandoffError, "belongs to current status"):
            validate_snapshot(snapshot)

    def test_snapshot_path_is_immutable_run_scoped(self):
        snapshot = build_snapshot(
            run_result(deals=(item(record("deal")),)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(SCHEMA_VERSION, "2.0")
        self.assertEqual(snapshot_repository_path(snapshot), "data/ftr-feed/2026/08/19/production-radar-20260819T080000-0800.json")


class FTRRepairIncidentTest(unittest.TestCase):
    def _seed_last_good(self, history: Path):
        snapshot = build_snapshot(
            run_result(deals=(item(record("last-good")),)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        staged = stage_snapshot(history_dir=history, snapshot=snapshot)
        stage_current_status_from_snapshot(history_dir=history, snapshot=snapshot, updated_at="2026-08-19T08:06:00+08:00")
        return snapshot, staged

    def _set_incident(self, history: Path):
        return mark_repair_required(
            history_dir=history,
            failed_attempt={
                "run_id": "production-radar-20260819T120000+0800",
                "mode": "canonical_daily",
                "attempt_state": "failed",
                "terminal_state": "failed",
                "producer_health_status": "provider_failed",
                "evidence_ref": "data/run-evidence/2026/08/19/failed-run/result.json",
            },
            incident_set_at="2026-08-19T12:10:00+08:00",
        )

    def test_machine_ssot_required_current_status_paths_match_persisted_payloads(self):
        policy = yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))
        contract = policy["ftr_handoff"]["current_status"]
        required_top_level = contract["required_top_level_fields"]
        conditional_paths = contract["required_nested_paths"]

        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            self._seed_last_good(history)
            healthy = load_current_status(history_dir=history)
            for field in required_top_level:
                self.assertIn(field, healthy, msg=f"machine SSOT required top-level field missing: {field}")
            assert_nested_paths(self, healthy, conditional_paths["when_last_good_present"])

            repair = self._set_incident(history)
            for field in required_top_level:
                self.assertIn(field, repair, msg=f"machine SSOT required top-level field missing: {field}")
            assert_nested_paths(self, repair, conditional_paths["when_last_good_present"])
            assert_nested_paths(self, repair, conditional_paths["when_repair_required"])

    def test_failed_attempt_preserves_last_good_and_exposes_stale_reference_only_in_current_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            snapshot, staged = self._seed_last_good(history)
            snapshot_file = history / staged["snapshot_path"]
            snapshot_before = snapshot_file.read_bytes()
            latest_before = (history / CANONICAL_LATEST_PATH).read_bytes()

            status = self._set_incident(history)
            self.assertTrue(status["repair_required"])
            self.assertEqual(status["current_freshness_state"], "stale_reference")
            self.assertEqual(status["last_good"]["run_id"], snapshot["run_id"])
            self.assertEqual((history / CANONICAL_LATEST_PATH).read_bytes(), latest_before)
            self.assertEqual(snapshot_file.read_bytes(), snapshot_before)

            current = load_current_reference(history_dir=history)
            self.assertEqual(current["current_freshness_state"], "stale_reference")
            self.assertEqual(current["snapshot"]["freshness_state"], "fresh")
            self.assertEqual(snapshot_file.read_bytes(), snapshot_before)

    def test_recovery_like_validated_transition_clears_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            self._seed_last_good(history)
            self._set_incident(history)
            recovery_run = run_result(
                deals=(item(record("recovery", observed_at="2026-08-19T13:00:00+08:00")),),
                run_id="recovery-radar-20260819T130000+0800",
                run_at="2026-08-19T13:00:00+08:00",
            )
            recovery = build_snapshot(
                recovery_run,
                producer_commit_sha="def456",
                mode="same_day_recovery",
                generated_at="2026-08-19T13:05:00+08:00",
            )
            stage_snapshot(history_dir=history, snapshot=recovery)
            cleared = clear_repair_required(
                history_dir=history,
                recovery_run_id=recovery["run_id"],
                attempt_mode="same_day_recovery",
                cleared_at="2026-08-19T13:06:00+08:00",
            )
            self.assertFalse(cleared["repair_required"])
            self.assertEqual(cleared["current_freshness_state"], "fresh")
            self.assertEqual(cleared["last_good"]["run_id"], recovery["run_id"])
            self.assertEqual(cleared["repair_incident"]["state"], "cleared")
            self.assertEqual(load_current_status(history_dir=history)["repair_required"], False)

    def test_invalid_or_incomplete_recovery_cannot_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            self._seed_last_good(history)
            self._set_incident(history)
            status_before = (history / CURRENT_STATUS_PATH).read_bytes()
            with self.assertRaisesRegex(FTRHandoffError, "does not reference the claimed recovery run"):
                clear_repair_required(
                    history_dir=history,
                    recovery_run_id="missing-recovery",
                    attempt_mode="same_day_recovery",
                    cleared_at="2026-08-19T13:06:00+08:00",
                )
            self.assertEqual((history / CURRENT_STATUS_PATH).read_bytes(), status_before)
            self.assertTrue(load_current_status(history_dir=history)["repair_required"])

    def test_scoped_and_operator_identity_cannot_masquerade_as_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            self._seed_last_good(history)
            self._set_incident(history)
            status_before = (history / CURRENT_STATUS_PATH).read_bytes()
            for mode in ("scoped_search", "operator_reacquisition"):
                with self.subTest(mode=mode):
                    with self.assertRaisesRegex(FTRHandoffError, "only same_day_recovery"):
                        clear_repair_required(
                            history_dir=history,
                            recovery_run_id="anything",
                            attempt_mode=mode,
                            cleared_at="2026-08-19T13:06:00+08:00",
                        )
                    self.assertEqual((history / CURRENT_STATUS_PATH).read_bytes(), status_before)

    def test_old_immutable_snapshot_bytes_never_mutate_after_later_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            snapshot, staged = self._seed_last_good(history)
            path = history / staged["snapshot_path"]
            old_bytes = path.read_bytes()
            self._set_incident(history)
            self.assertEqual(path.read_bytes(), old_bytes)
            self.assertEqual(json.loads(old_bytes.decode("utf-8"))["freshness_state"], "fresh")
            self.assertEqual(load_current_status(history_dir=history)["last_good"]["run_id"], snapshot["run_id"])


if __name__ == "__main__":
    unittest.main()
