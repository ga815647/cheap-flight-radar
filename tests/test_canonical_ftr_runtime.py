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
    CURRENT_STATUS_PATH,
    load_current_status,
    load_manifest_snapshot,
)


APP_SHA = "a" * 40
DAY = "2026-08-20"
RUN_AT = "2026-08-20T08:00:00+08:00"
GENERATED_AT = "2026-08-20T08:05:00+08:00"


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


def markets():
    return {
        name: {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0}
        for name in ("japan", "korea", "china", "other_asia_oceania")
    }


def record(record_id="deal-kix", *, price=5000):
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
        "current_price_twd": price,
        "observed_at": RUN_AT,
        "verification_state": "revalidated",
        "evidence_class": "qualified_round_trip_deal",
        "complete_airfare": True,
        "airlines": ["Example Air"],
        "evidence_url": "https://example.invalid/evidence",
    }


def item(payload=None, *, classification="Deal", state="deal"):
    payload = payload or record()
    return {
        "classification": classification,
        "state": state,
        "observation_id": "obs-" + payload["record_id"],
        "current_complete_airfare_twd": payload["current_price_twd"],
        "discovery": payload,
        "exact": payload,
    }


def weak_signal():
    return item(record("weak"), classification="Signal", state="weak_seed")


def run_result(
    run_id="production-radar-20260820T080000+0800",
    *,
    deals=None,
    signals=None,
    health="healthy",
    origins=None,
    execution=None,
    terminal_state=None,
):
    reasons = [] if health == "healthy" else ["fixture degradation"]
    payload = {
        "radar_run_id": run_id,
        "run_at": RUN_AT,
        "deals": [item()] if deals is None else list(deals),
        "signals": [] if signals is None else list(signals),
        "ftr_absolute_low_non_deals": [],
        "coverage": {
            "origins": healthy_origins() if origins is None else origins,
            "markets": markets(),
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
    if terminal_state is not None:
        payload["terminal_state"] = terminal_state
    return payload


class CanonicalFTRRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.history = Path(self.tmp.name) / "history"
        self.history.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_run_result(self, payload, *, name=None):
        run_id = str(payload.get("radar_run_id") or name or "invalid-run")
        path = self.history / "data" / "run-evidence" / "2026" / "08" / "20" / run_id / "run-result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def stage(self, payload, **kwargs):
        path = self.write_run_result(payload)
        return stage_canonical_success(
            history_dir=self.history,
            run_result_path=path,
            producer_commit_sha=kwargs.pop("producer_commit_sha", APP_SHA),
            attempt_run_id=kwargs.pop("attempt_run_id", payload.get("radar_run_id")),
            requested_date=DAY,
            generated_at=kwargs.pop("generated_at", GENERATED_AT),
            failed_at=kwargs.pop("failed_at", GENERATED_AT),
            **kwargs,
        )

    def test_healthy_success_snapshot_latest_reload_status_and_application_sha(self):
        result = self.stage(run_result())
        self.assertEqual(result["status"], "success")
        loaded = load_manifest_snapshot(history_dir=self.history)
        self.assertEqual(loaded["producer_commit_sha"], APP_SHA)
        self.assertEqual(loaded["freshness_state"], "fresh")
        snapshot_bytes = (self.history / result["snapshot_path"]).read_bytes()
        self.assertEqual(hashlib.sha256(snapshot_bytes).hexdigest(), result["snapshot_sha256"])
        status = load_current_status(history_dir=self.history)
        self.assertFalse(status["repair_required"])
        self.assertEqual(status["current_freshness_state"], "fresh")
        self.assertEqual(status["last_good"]["snapshot_sha256"], result["snapshot_sha256"])

    def test_consumable_degraded_success_is_not_fresh(self):
        origins = healthy_origins()
        origins["RMQ"] = {
            "status": "degraded",
            "returned_flight_deals": 0,
            "explore_seeds": 1,
            "errors": ["fixture"],
        }
        result = self.stage(run_result(health="degraded", origins=origins))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["coverage_state"], "degraded")
        self.assertEqual(result["freshness_state"], "degraded")
        self.assertEqual(load_current_status(history_dir=self.history)["current_freshness_state"], "degraded")

    def test_healthy_zero_ftr_candidates_is_valid_zero_opportunity_snapshot(self):
        result = self.stage(run_result(deals=[], signals=[weak_signal()]))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["candidate_counts"]["opportunities"], 0)
        loaded = load_manifest_snapshot(history_dir=self.history)
        self.assertEqual(loaded["opportunities"], [])
        self.assertEqual(loaded["freshness_state"], "fresh")

    def test_provider_failed_does_not_create_latest_and_sets_unavailable_repair(self):
        origins = {
            airport: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0, "errors": ["failed"]}
            for airport in ("TPE", "TSA", "RMQ", "KHH")
        }
        execution = healthy_execution()
        execution["flight_deals"] = execution_row(attempts=4, failures=4)
        execution["explore"] = execution_row(attempts=4, failures=4)
        payload = run_result(health="provider_failed", origins=origins, execution=execution, deals=[], signals=[weak_signal()])
        payload["provider_failures"] = [{"provider": "gflights", "surface": "flight_deals", "error": "fixture"}]
        result = self.stage(payload)
        self.assertEqual(result["status"], "failed")
        self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["current_freshness_state"], "unavailable")
        self.assertTrue((self.history / result["failure_evidence_ref"]).exists())

    def test_invalid_terminal_and_candidate_fail_closed(self):
        terminal = self.stage(run_result(terminal_state="failed"))
        self.assertEqual(terminal["status"], "failed")
        self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())

        other_history = self.history.parent / "other-history"
        other_history.mkdir()
        malformed = run_result()
        malformed["deals"][0]["exact"]["complete_airfare"] = False
        path = other_history / "data/run-evidence/2026/08/20/production-radar-invalid/run-result.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
        failed = stage_canonical_success(
            history_dir=other_history,
            run_result_path=path,
            producer_commit_sha=APP_SHA,
            attempt_run_id=malformed["radar_run_id"],
            requested_date=DAY,
            generated_at=GENERATED_AT,
            failed_at=GENERATED_AT,
        )
        self.assertEqual(failed["status"], "failed")
        self.assertFalse((other_history / CANONICAL_LATEST_PATH).exists())
        self.assertTrue(load_current_status(history_dir=other_history)["repair_required"])

    def test_existing_last_good_is_byte_identical_after_later_failure(self):
        first = self.stage(run_result())
        latest_path = self.history / CANONICAL_LATEST_PATH
        snapshot_path = self.history / first["snapshot_path"]
        old_latest = latest_path.read_bytes()
        old_snapshot = snapshot_path.read_bytes()
        failed = stage_canonical_process_failure(
            history_dir=self.history,
            requested_date=DAY,
            attempt_run_id="canonical-attempt-20260820-999",
            producer_commit_sha=APP_SHA,
            failed_at="2026-08-20T09:00:00+08:00",
        )
        self.assertEqual(latest_path.read_bytes(), old_latest)
        self.assertEqual(snapshot_path.read_bytes(), old_snapshot)
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["current_freshness_state"], "stale_reference")
        self.assertEqual(status["last_good"]["snapshot_sha256"], first["snapshot_sha256"])
        self.assertEqual(failed["current_freshness_state"], "stale_reference")

    def test_reload_failure_rolls_back_tentative_manifest_before_repair(self):
        first = self.stage(run_result())
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        second = run_result(run_id="production-radar-20260820T090000+0800")
        path = self.write_run_result(second)
        with mock.patch(
            "cheap_flight_radar.canonical_ftr_runtime.load_manifest_snapshot",
            side_effect=ValueError("fixture reload mismatch"),
        ):
            result = stage_canonical_success(
                history_dir=self.history,
                run_result_path=path,
                producer_commit_sha=APP_SHA,
                attempt_run_id=second["radar_run_id"],
                requested_date=DAY,
                generated_at="2026-08-20T09:05:00+08:00",
                failed_at="2026-08-20T09:05:00+08:00",
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        self.assertEqual(load_manifest_snapshot(history_dir=self.history)["run_id"], first["radar_run_id"])
        self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])

    def test_same_immutable_path_with_different_bytes_fails_closed(self):
        payload = run_result()
        first = self.stage(payload)
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        # Keep the same run id/path but change generation bytes.
        second = self.stage(payload, generated_at="2026-08-20T08:06:00+08:00", failed_at="2026-08-20T08:06:00+08:00")
        self.assertEqual(second["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        self.assertEqual(load_manifest_snapshot(history_dir=self.history)["run_id"], first["radar_run_id"])

    def test_active_repair_incident_blocks_ordinary_canonical_success(self):
        first = self.stage(run_result())
        old_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        stage_canonical_process_failure(
            history_dir=self.history,
            requested_date=DAY,
            attempt_run_id="canonical-attempt-20260820-repair",
            producer_commit_sha=APP_SHA,
            failed_at="2026-08-20T09:00:00+08:00",
        )
        second = run_result(run_id="production-radar-20260820T100000+0800")
        failed = self.stage(second, generated_at="2026-08-20T10:05:00+08:00", failed_at="2026-08-20T10:05:00+08:00")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), old_latest)
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"]["run_id"], "canonical-attempt-20260820-repair")
        self.assertEqual(status["last_good"]["run_id"], first["radar_run_id"])

    def test_legitimate_cfr_evidence_survives_ftr_staging_failure(self):
        payload = run_result()
        path = self.write_run_result(payload)
        cfr_snapshot = self.history / "data/price-history/2026/08/20/production-radar-cfr.json"
        cfr_snapshot.parent.mkdir(parents=True)
        cfr_snapshot.write_bytes(b"immutable-cfr-evidence\n")
        run_result_before = path.read_bytes()
        cfr_before = cfr_snapshot.read_bytes()
        payload["deals"][0]["exact"]["complete_airfare"] = False
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        invalid_run_result_bytes = path.read_bytes()
        result = stage_canonical_success(
            history_dir=self.history,
            run_result_path=path,
            producer_commit_sha=APP_SHA,
            attempt_run_id=payload["radar_run_id"],
            requested_date=DAY,
            generated_at=GENERATED_AT,
            failed_at=GENERATED_AT,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(cfr_snapshot.read_bytes(), cfr_before)
        self.assertEqual(path.read_bytes(), invalid_run_result_bytes)
        self.assertNotEqual(path.read_bytes(), run_result_before)

    def test_no_last_good_process_failure_creates_no_fabricated_latest(self):
        result = stage_canonical_process_failure(
            history_dir=self.history,
            requested_date=DAY,
            attempt_run_id="canonical-attempt-20260820-123",
            producer_commit_sha=APP_SHA,
            failed_at=GENERATED_AT,
        )
        self.assertEqual(result["status"], "failed")
        self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
        status = json.loads((self.history / CURRENT_STATUS_PATH).read_text(encoding="utf-8"))
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["current_freshness_state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
