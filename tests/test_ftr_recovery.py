import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cheap_flight_radar.canonical_ftr_runtime import (
    stage_canonical_process_failure,
    stage_canonical_success,
)
from cheap_flight_radar.ftr_handoff import (
    CANONICAL_LATEST_PATH,
    FTRHandoffError,
    clear_repair_required,
    load_current_status,
    load_manifest_snapshot,
)
from cheap_flight_radar.ftr_recovery import (
    inspect_recovery_state,
    recovery_claim_repository_path,
    recovery_run_prefix,
    stage_recovery_cfr_success_evidence,
    stage_recovery_process_failure,
    stage_recovery_success,
    write_recovery_claim,
)
from cheap_flight_radar.production_operations import claim_repository_path


DAY = "2026-08-20"
RUN_AT = "2026-08-20T10:00:00+08:00"
APP_SHA = "b" * 40
CANONICAL_SHA = "a" * 40
REQUEST_ID = "repair-20260820-a"


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
        "flight_deals": execution_row(attempts=4, records=4, successes=4),
        "explore": execution_row(attempts=4, records=4, successes=4),
        "conventional_exact": execution_row(attempts=1, records=1, successes=1),
        "flexible_dates": execution_row(),
        "mixed_taiwan_return": execution_row(),
        "open_jaw": execution_row(),
    }


def healthy_origins():
    return {
        airport: {
            "status": "attempted",
            "returned_flight_deals": 1,
            "explore_seeds": 1,
            "errors": [],
        }
        for airport in ("TPE", "TSA", "RMQ", "KHH")
    }


def market_rows():
    return {
        name: {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0}
        for name in ("japan", "korea", "china", "other_asia_oceania")
    }


def airfare_record(record_id="deal-kix", *, observed_at=RUN_AT):
    return {
        "record_id": record_id,
        "provider": "gflights",
        "surface": "exact",
        "origin": {"iata": "TPE", "city": "Taoyuan", "country": "Taiwan"},
        "destination": {"iata": "KIX", "city": "Osaka", "country": "Japan"},
        "legs": [{
            "origin": "TPE",
            "destination": "KIX",
            "date": "2026-10-05",
            "departure_time": "08:00+08:00",
            "arrival_time": "12:00+09:00",
        }],
        "reproducible_search": {"return_date": "2026-10-09"},
        "current_price_twd": 5000,
        "observed_at": observed_at,
        "verification_state": "revalidated",
        "evidence_class": "qualified_round_trip_deal",
        "complete_airfare": True,
        "airlines": ["Example Air"],
        "evidence_url": "https://example.invalid/evidence",
    }


def radar_item(payload=None):
    payload = payload or airfare_record()
    return {
        "classification": "Deal",
        "state": "deal",
        "observation_id": "obs-" + payload["record_id"],
        "current_complete_airfare_twd": payload["current_price_twd"],
        "discovery": payload,
        "exact": payload,
    }


def run_result(run_id, *, mode=None, health="healthy", origins=None, execution=None):
    reasons = [] if health == "healthy" else ["fixture degradation"]
    payload = {
        "radar_run_id": run_id,
        "run_at": RUN_AT,
        "deals": [radar_item()],
        "signals": [],
        "ftr_absolute_low_non_deals": [],
        "coverage": {
            "origins": healthy_origins() if origins is None else origins,
            "markets": market_rows(),
            "execution": healthy_execution() if execution is None else execution,
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
        "provider_failures": [],
    }
    if mode is not None:
        payload["execution_mode"] = mode
    return payload


class FTRRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.history = root / "history"
        self.output = root / "output"
        self.history.mkdir()
        self.output.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_canonical_result(self, payload):
        run_id = payload["radar_run_id"]
        path = self.history / "data/run-evidence/2026/08/20" / run_id / "run-result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _canonical_success(self):
        payload = run_result("production-radar-20260820T080000+0800")
        path = self._write_canonical_result(payload)
        result = stage_canonical_success(
            history_dir=self.history,
            run_result_path=path,
            producer_commit_sha=CANONICAL_SHA,
            attempt_run_id=payload["radar_run_id"],
            requested_date=DAY,
            generated_at="2026-08-20T08:05:00+08:00",
            failed_at="2026-08-20T08:05:00+08:00",
        )
        self.assertEqual(result["status"], "success")
        return result

    def _activate_repair(self, *, with_last_good=True):
        baseline = self._canonical_success() if with_last_good else None
        failure = stage_canonical_process_failure(
            history_dir=self.history,
            requested_date=DAY,
            attempt_run_id="canonical-attempt-20260820-failed",
            producer_commit_sha=CANONICAL_SHA,
            failed_at="2026-08-20T09:00:00+08:00",
            reason="fixture canonical failure",
        )
        self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])
        return baseline, failure

    def _claim(self, request_id=REQUEST_ID):
        return write_recovery_claim(
            history_dir=self.history,
            requested_date=DAY,
            request_id=request_id,
            application_sha=APP_SHA,
            claimed_at="2026-08-20T09:30:00+08:00",
            workflow_run_id="9001",
            workflow_run_url="https://github.example/actions/runs/9001",
            trigger_sha="control-sha",
            current_date=DAY,
        )

    def _write_recovery_output(self, *, request_id=REQUEST_ID, payload=None):
        run_id = f"{recovery_run_prefix(request_id)}20260820T100000+0800"
        payload = payload or run_result(run_id, mode="same_day_recovery")
        run_id = payload["radar_run_id"]
        safe_id = run_id.replace("+", "-")
        history_rel = f"data/price-history/2026/08/20/{safe_id}.json"
        snapshot_path = self.output / "history" / history_rel
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps({
            "schema_version": 1,
            "radar_run_id": run_id,
            "run_at": payload["run_at"],
            "observations": [],
        }, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path = self.output / "publication/runs" / f"{run_id}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "schema_version": 2,
            "radar_run_id": run_id,
            "run_at": payload["run_at"],
            "history_snapshot_path": history_rel,
            "execution_mode": "same_day_recovery",
            "deals": [],
            "signals": [],
            "coverage": payload["coverage"],
            "provider_failures": payload.get("provider_failures", []),
        }, sort_keys=True) + "\n", encoding="utf-8")
        (self.output / "run-result.json").write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        return run_id, history_rel

    def _stage_cfr(self, request_id=REQUEST_ID, payload=None):
        run_id, history_rel = self._write_recovery_output(request_id=request_id, payload=payload)
        staged = stage_recovery_cfr_success_evidence(
            output_dir=self.output,
            history_dir=self.history,
            requested_date=DAY,
            request_id=request_id,
            application_sha=APP_SHA,
        )
        self.assertEqual(staged["radar_run_id"], run_id)
        self.assertTrue((self.history / history_rel).exists())
        return staged

    def _stage_ftr(self, staged, request_id=REQUEST_ID, **kwargs):
        return stage_recovery_success(
            history_dir=self.history,
            run_result_path=self.history / staged["run_result_path"],
            requested_date=DAY,
            request_id=request_id,
            application_sha=APP_SHA,
            generated_at=kwargs.pop("generated_at", "2026-08-20T10:05:00+08:00"),
            failed_at=kwargs.pop("failed_at", "2026-08-20T10:05:00+08:00"),
            current_date=kwargs.pop("current_date", DAY),
            **kwargs,
        )

    def test_no_active_repair_refuses_before_claim_namespace(self):
        self._canonical_success()
        state = inspect_recovery_state(
            history_dir=self.history,
            requested_date=DAY,
            request_id=REQUEST_ID,
            application_sha=APP_SHA,
            current_date=DAY,
        )
        self.assertEqual(state.status, "no_active_repair")
        self.assertFalse((self.history / recovery_claim_repository_path(DAY, REQUEST_ID)).exists())
        with self.assertRaisesRegex(FTRHandoffError, "no_active_repair"):
            self._claim()

    def test_preflight_requires_existing_valid_current_status(self):
        with self.assertRaisesRegex(FTRHandoffError, "current status is missing"):
            inspect_recovery_state(
                history_dir=self.history,
                requested_date=DAY,
                request_id=REQUEST_ID,
                application_sha=APP_SHA,
                current_date=DAY,
            )

    def test_claim_is_distinct_and_duplicate_request_cannot_reacquire(self):
        self._activate_repair()
        self._claim()
        claim_path = self.history / recovery_claim_repository_path(DAY, REQUEST_ID)
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        self.assertEqual(claim["mode"], "same_day_recovery")
        self.assertEqual(claim["application_sha"], APP_SHA)
        self.assertFalse((self.history / claim_repository_path(DAY)).exists())
        state = inspect_recovery_state(
            history_dir=self.history,
            requested_date=DAY,
            request_id=REQUEST_ID,
            application_sha=APP_SHA,
            current_date=DAY,
        )
        self.assertEqual(state.status, "duplicate_request_claimed")
        with self.assertRaisesRegex(FTRHandoffError, "duplicate_request_claimed"):
            self._claim()

        new_state = inspect_recovery_state(
            history_dir=self.history,
            requested_date=DAY,
            request_id="repair-20260820-b",
            application_sha=APP_SHA,
            current_date=DAY,
        )
        self.assertEqual(new_state.status, "acquire")

    def test_same_day_guard_and_path_safe_request_id_fail_closed(self):
        self._activate_repair()
        with self.assertRaisesRegex(FTRHandoffError, "Asia/Taipei current day"):
            inspect_recovery_state(
                history_dir=self.history,
                requested_date="2026-08-19",
                request_id=REQUEST_ID,
                application_sha=APP_SHA,
                current_date=DAY,
            )
        with self.assertRaisesRegex(FTRHandoffError, "path-safe"):
            inspect_recovery_state(
                history_dir=self.history,
                requested_date=DAY,
                request_id="../bad/request",
                application_sha=APP_SHA,
                current_date=DAY,
            )

    def test_healthy_same_day_recovery_advances_latest_and_clears_incident(self):
        baseline, failure = self._activate_repair()
        original_status = load_current_status(history_dir=self.history)
        original_trigger = dict(original_status["repair_incident"]["trigger_attempt"])
        self._claim()
        staged = self._stage_cfr()
        result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["repair_required"])
        latest = load_manifest_snapshot(history_dir=self.history)
        self.assertEqual(latest["run_id"], result["radar_run_id"])
        self.assertEqual(latest["mode"], "same_day_recovery")
        self.assertEqual(latest["producer_commit_sha"], APP_SHA)
        status = load_current_status(history_dir=self.history)
        self.assertFalse(status["repair_required"])
        self.assertEqual(status["current_freshness_state"], "fresh")
        self.assertEqual(status["last_good"]["run_id"], result["radar_run_id"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], original_trigger)
        self.assertEqual(status["repair_incident"]["cleared_by"]["run_id"], result["radar_run_id"])
        self.assertEqual(status["repair_incident"]["cleared_by"]["snapshot_sha256"], result["snapshot_sha256"])
        self.assertNotEqual(status["last_good"]["run_id"], baseline["radar_run_id"])
        self.assertTrue((self.history / result["transition_evidence_ref"]).exists())
        self.assertTrue((self.history / failure["failure_evidence_ref"]).exists())

    def test_recovery_can_create_first_valid_latest_when_no_prior_last_good(self):
        self._activate_repair(with_last_good=False)
        self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
        self._claim()
        staged = self._stage_cfr()
        result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "success")
        self.assertTrue((self.history / CANONICAL_LATEST_PATH).exists())
        status = load_current_status(history_dir=self.history)
        self.assertFalse(status["repair_required"])
        self.assertEqual(status["last_good"]["run_id"], result["radar_run_id"])

    def test_degraded_recovery_preserves_prior_latest_and_original_trigger(self):
        baseline, _ = self._activate_repair()
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        before = load_current_status(history_dir=self.history)
        original_trigger = dict(before["repair_incident"]["trigger_attempt"])
        origins = healthy_origins()
        origins["RMQ"] = {
            "status": "degraded",
            "returned_flight_deals": 0,
            "explore_seeds": 1,
            "errors": ["fixture"],
        }
        payload = run_result(
            f"{recovery_run_prefix(REQUEST_ID)}20260820T100000+0800",
            mode="same_day_recovery",
            health="degraded",
            origins=origins,
        )
        self._claim()
        staged = self._stage_cfr(payload=payload)
        result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["last_good"]["run_id"], baseline["radar_run_id"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], original_trigger)
        self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["mode"], "same_day_recovery")

    def test_provider_failed_recovery_cannot_advance_or_clear(self):
        self._activate_repair()
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        origins = {
            airport: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0, "errors": ["failed"]}
            for airport in ("TPE", "TSA", "RMQ", "KHH")
        }
        execution = healthy_execution()
        execution["flight_deals"] = execution_row(attempts=4, failures=4)
        execution["explore"] = execution_row(attempts=4, failures=4)
        payload = run_result(
            f"{recovery_run_prefix(REQUEST_ID)}20260820T100000+0800",
            mode="same_day_recovery",
            health="provider_failed",
            origins=origins,
            execution=execution,
        )
        payload["provider_failures"] = [{"provider": "gflights", "surface": "flight_deals", "error": "fixture"}]
        self._claim()
        staged = self._stage_cfr(payload=payload)
        result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])

    def test_snapshot_collision_with_different_bytes_fails_closed(self):
        self._activate_repair()
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        self._claim()
        staged = self._stage_cfr()
        run_id = staged["radar_run_id"]
        collision = self.history / f"data/ftr-feed/2026/08/20/{run_id}.json"
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"different immutable bytes\n")
        result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])

    def test_checksum_mismatch_restores_prior_latest_and_keeps_repair(self):
        self._activate_repair()
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        self._claim()
        staged = self._stage_cfr()
        from cheap_flight_radar import ftr_recovery as module
        real_stage = module.stage_snapshot

        def bad_stage(*args, **kwargs):
            value = dict(real_stage(*args, **kwargs))
            value["snapshot_sha256"] = "0" * 64
            return value

        with mock.patch("cheap_flight_radar.ftr_recovery.stage_snapshot", side_effect=bad_stage):
            result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertIn("checksum", result["failure_reason"])
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])

    def test_reload_run_mode_or_sha_mismatch_restores_and_keeps_repair(self):
        for field, bad_value in (
            ("run_id", "ftr-recovery-other-20260820T100000+0800"),
            ("mode", "canonical_daily"),
            ("producer_commit_sha", "c" * 40),
        ):
            with self.subTest(field=field):
                other = Path(self.tmp.name) / f"case-{field}"
                other.mkdir()
                prior_history = self.history
                self.history = other
                try:
                    self._activate_repair(with_last_good=False)
                    self._claim()
                    staged = self._stage_cfr()
                    from cheap_flight_radar import ftr_recovery as module
                    real_load = module.load_manifest_snapshot
                    calls = {"count": 0}

                    def corrupted_load(*args, **kwargs):
                        calls["count"] += 1
                        loaded = dict(real_load(*args, **kwargs))
                        # No prior latest exists, so the first actual load is the
                        # post-stage verification that must fail closed.
                        if calls["count"] == 1:
                            loaded[field] = bad_value
                        return loaded

                    with mock.patch("cheap_flight_radar.ftr_recovery.load_manifest_snapshot", side_effect=corrupted_load):
                        result = self._stage_ftr(staged)
                    self.assertEqual(result["status"], "failed")
                    self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
                    self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])
                finally:
                    self.history = prior_history

    def test_post_latest_clear_failure_rolls_back_status_and_keeps_cfr_evidence(self):
        self._activate_repair()
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        original_trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
        self._claim()
        staged = self._stage_cfr()
        cfr_paths = [
            self.history / staged["history_snapshot_path"],
            self.history / staged["run_result_path"],
            self.history / staged["recovery_manifest_path"],
            self.history / staged["recovery_acquisition_path"],
        ]
        before = {path: path.read_bytes() for path in cfr_paths}
        with mock.patch(
            "cheap_flight_radar.ftr_recovery.clear_repair_required",
            side_effect=FTRHandoffError("fixture clear failure after latest advancement"),
        ):
            result = self._stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], original_trigger)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_process_failure_after_claim_preserves_original_incident_and_consumes_request_id(self):
        self._activate_repair()
        original = load_current_status(history_dir=self.history)
        original_trigger = dict(original["repair_incident"]["trigger_attempt"])
        self._claim()
        failed_id = f"{recovery_run_prefix(REQUEST_ID)}workflow-9001"
        result = stage_recovery_process_failure(
            history_dir=self.history,
            requested_date=DAY,
            request_id=REQUEST_ID,
            application_sha=APP_SHA,
            attempt_run_id=failed_id,
            failed_at="2026-08-20T09:45:00+08:00",
            reason="fixture provider process failure",
        )
        self.assertEqual(result["status"], "failed")
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], original_trigger)
        self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["run_id"], failed_id)
        state = inspect_recovery_state(
            history_dir=self.history,
            requested_date=DAY,
            request_id=REQUEST_ID,
            application_sha=APP_SHA,
            current_date=DAY,
        )
        self.assertEqual(state.status, "duplicate_request_claimed")

    def test_only_same_day_recovery_identity_can_clear(self):
        self._activate_repair()
        for forbidden in ("canonical_daily", "operator_reacquisition", "scoped_search"):
            with self.subTest(mode=forbidden):
                with self.assertRaisesRegex(FTRHandoffError, "only same_day_recovery"):
                    clear_repair_required(
                        history_dir=self.history,
                        recovery_run_id="irrelevant",
                        attempt_mode=forbidden,
                        cleared_at="2026-08-20T10:00:00+08:00",
                    )


if __name__ == "__main__":
    unittest.main()
