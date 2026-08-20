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
APP_SHA = "b" * 40
CANONICAL_SHA = "a" * 40
REQUEST_ID = "repair-20260820-a"


def execution_row(attempts=0, records=0, successes=0, failures=0):
    return {
        "attempts": attempts, "provider_calls": attempts, "records": records,
        "successes": successes, "empty": 0, "failures": failures,
        "suppressed": 0, "unsupported": 0,
    }


def healthy_execution():
    return {
        "flight_deals": execution_row(4, 4, 4),
        "explore": execution_row(4, 4, 4),
        "conventional_exact": execution_row(1, 1, 1),
        "flexible_dates": execution_row(),
        "mixed_taiwan_return": execution_row(),
        "open_jaw": execution_row(),
    }


def healthy_origins():
    return {
        airport: {"status": "attempted", "returned_flight_deals": 1, "explore_seeds": 1, "errors": []}
        for airport in ("TPE", "TSA", "RMQ", "KHH")
    }


def run_result(run_id, *, mode=None, health="healthy", origins=None, execution=None):
    record = {
        "record_id": "deal-kix", "provider": "gflights", "surface": "exact",
        "origin": {"iata": "TPE", "city": "Taoyuan", "country": "Taiwan"},
        "destination": {"iata": "KIX", "city": "Osaka", "country": "Japan"},
        "legs": [{"origin": "TPE", "destination": "KIX", "date": "2026-10-05",
                  "departure_time": "08:00+08:00", "arrival_time": "12:00+09:00"}],
        "reproducible_search": {"return_date": "2026-10-09"},
        "current_price_twd": 5000, "observed_at": f"{DAY}T10:00:00+08:00",
        "verification_state": "revalidated", "evidence_class": "qualified_round_trip_deal",
        "complete_airfare": True, "airlines": ["Example Air"],
        "evidence_url": "https://example.invalid/evidence",
    }
    reasons = [] if health == "healthy" else ["fixture degradation"]
    payload = {
        "radar_run_id": run_id, "run_at": f"{DAY}T10:00:00+08:00",
        "deals": [{"classification": "Deal", "state": "deal", "observation_id": "obs-deal-kix",
                   "current_complete_airfare_twd": 5000, "discovery": record, "exact": record}],
        "signals": [], "ftr_absolute_low_non_deals": [],
        "coverage": {
            "origins": origins or healthy_origins(),
            "markets": {name: {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0}
                        for name in ("japan", "korea", "china", "other_asia_oceania")},
            "execution": execution or healthy_execution(), "all_origins_attempted": True,
            "destination_scope": "asia_oceania",
            "provider_health": {"status": health, "technical_failure_count": 0 if health == "healthy" else 1,
                                "reasons": reasons},
        },
        "provider_health": {"status": health, "technical_failure_count": 0 if health == "healthy" else 1,
                            "reasons": reasons},
        "provider_failures": [],
    }
    if mode:
        payload["execution_mode"] = mode
    return payload


class FTRRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.history, self.output = root / "history", root / "output"
        self.history.mkdir(); self.output.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def canonical_success(self):
        payload = run_result("production-radar-20260820T080000+0800")
        path = self.history / "data/run-evidence/2026/08/20" / payload["radar_run_id"] / "run-result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        result = stage_canonical_success(
            history_dir=self.history, run_result_path=path, producer_commit_sha=CANONICAL_SHA,
            attempt_run_id=payload["radar_run_id"], requested_date=DAY,
            generated_at=f"{DAY}T08:05:00+08:00", failed_at=f"{DAY}T08:05:00+08:00")
        self.assertEqual(result["status"], "success")
        return result

    def activate_repair(self, with_last_good=True):
        baseline = self.canonical_success() if with_last_good else None
        failure = stage_canonical_process_failure(
            history_dir=self.history, requested_date=DAY,
            attempt_run_id="canonical-attempt-20260820-failed", producer_commit_sha=CANONICAL_SHA,
            failed_at=f"{DAY}T09:00:00+08:00", reason="fixture canonical failure")
        return baseline, failure

    def claim(self, request_id=REQUEST_ID):
        return write_recovery_claim(
            history_dir=self.history, requested_date=DAY, request_id=request_id,
            application_sha=APP_SHA, claimed_at=f"{DAY}T09:30:00+08:00",
            workflow_run_id="9001", workflow_run_url="https://example.invalid/runs/9001",
            trigger_sha="control-sha", current_date=DAY)

    def recovery_output(self, request_id=REQUEST_ID, payload=None):
        run_id = f"{recovery_run_prefix(request_id)}20260820T100000+0800"
        payload = payload or run_result(run_id, mode="same_day_recovery")
        run_id = payload["radar_run_id"]
        history_rel = f"data/price-history/2026/08/20/{run_id.replace('+', '-')}.json"
        snap = self.output / "history" / history_rel
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({"schema_version": 1, "radar_run_id": run_id,
                                    "run_at": payload["run_at"], "observations": []}) + "\n", encoding="utf-8")
        manifest = self.output / "publication/runs" / f"{run_id}.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"schema_version": 2, "radar_run_id": run_id,
                                        "run_at": payload["run_at"], "history_snapshot_path": history_rel,
                                        "execution_mode": "same_day_recovery", "deals": [], "signals": [],
                                        "coverage": payload["coverage"], "provider_failures": payload["provider_failures"]}) + "\n",
                            encoding="utf-8")
        (self.output / "run-result.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def stage_cfr(self, request_id=REQUEST_ID, payload=None):
        self.recovery_output(request_id, payload)
        return stage_recovery_cfr_success_evidence(
            output_dir=self.output, history_dir=self.history, requested_date=DAY,
            request_id=request_id, application_sha=APP_SHA)

    def stage_ftr(self, staged, request_id=REQUEST_ID):
        with mock.patch("cheap_flight_radar.ftr_recovery._today_local", return_value=DAY):
            return stage_recovery_success(
                history_dir=self.history, run_result_path=self.history / staged["run_result_path"],
                requested_date=DAY, request_id=request_id, application_sha=APP_SHA,
                generated_at=f"{DAY}T10:05:00+08:00", failed_at=f"{DAY}T10:05:00+08:00")

    def test_no_active_repair_refuses_without_claim(self):
        self.canonical_success()
        state = inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
                                       application_sha=APP_SHA, current_date=DAY)
        self.assertEqual(state.status, "no_active_repair")
        self.assertFalse((self.history / recovery_claim_repository_path(DAY, REQUEST_ID)).exists())
        with self.assertRaisesRegex(FTRHandoffError, "no_active_repair"):
            self.claim()

    def test_missing_current_status_fails_closed(self):
        with self.assertRaisesRegex(FTRHandoffError, "current status is missing"):
            inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
                                   application_sha=APP_SHA, current_date=DAY)

    def test_claim_identity_isolated_duplicate_blocked_new_id_allowed(self):
        self.activate_repair(); self.claim()
        claim = json.loads((self.history / recovery_claim_repository_path(DAY, REQUEST_ID)).read_text())
        self.assertEqual(claim["mode"], "same_day_recovery")
        self.assertEqual(claim["application_sha"], APP_SHA)
        self.assertFalse((self.history / claim_repository_path(DAY)).exists())
        state = inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
                                       application_sha=APP_SHA, current_date=DAY)
        self.assertEqual(state.status, "duplicate_request_claimed")
        with self.assertRaisesRegex(FTRHandoffError, "duplicate_request_claimed"):
            self.claim()
        new = inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id="repair-20260820-b",
                                     application_sha=APP_SHA, current_date=DAY)
        self.assertEqual(new.status, "acquire")

    def test_same_day_and_path_safe_guards(self):
        self.activate_repair()
        with self.assertRaisesRegex(FTRHandoffError, "Asia/Taipei current day"):
            inspect_recovery_state(history_dir=self.history, requested_date="2026-08-19", request_id=REQUEST_ID,
                                   application_sha=APP_SHA, current_date=DAY)
        with self.assertRaisesRegex(FTRHandoffError, "path-safe"):
            inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id="../bad/request",
                                   application_sha=APP_SHA, current_date=DAY)

    def test_healthy_recovery_advances_latest_and_clears_preserving_chronology(self):
        baseline, _ = self.activate_repair()
        trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
        self.claim(); staged = self.stage_cfr(); result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "success")
        latest = load_manifest_snapshot(history_dir=self.history)
        self.assertEqual((latest["run_id"], latest["mode"], latest["producer_commit_sha"]),
                         (result["radar_run_id"], "same_day_recovery", APP_SHA))
        status = load_current_status(history_dir=self.history)
        self.assertFalse(status["repair_required"])
        self.assertEqual(status["last_good"]["run_id"], result["radar_run_id"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)
        self.assertEqual(status["repair_incident"]["cleared_by"]["snapshot_sha256"], result["snapshot_sha256"])
        self.assertNotEqual(status["last_good"]["run_id"], baseline["radar_run_id"])
        self.assertTrue((self.history / result["transition_evidence_ref"]).exists())

    def test_recovery_creates_first_latest_without_prior_last_good(self):
        self.activate_repair(with_last_good=False)
        self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
        self.claim(); result = self.stage_ftr(self.stage_cfr())
        self.assertEqual(result["status"], "success")
        self.assertEqual(load_current_status(history_dir=self.history)["last_good"]["run_id"], result["radar_run_id"])

    def test_degraded_and_provider_failed_cannot_advance_or_clear(self):
        cases = []
        degraded_origins = healthy_origins()
        degraded_origins["RMQ"] = {"status": "degraded", "returned_flight_deals": 0,
                                    "explore_seeds": 1, "errors": ["fixture"]}
        cases.append(run_result(f"{recovery_run_prefix(REQUEST_ID)}degraded", mode="same_day_recovery",
                                health="degraded", origins=degraded_origins))
        failed_origins = {a: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0, "errors": ["failed"]}
                          for a in ("TPE", "TSA", "RMQ", "KHH")}
        failed_exec = healthy_execution(); failed_exec["flight_deals"] = execution_row(4, 0, 0, 4); failed_exec["explore"] = execution_row(4, 0, 0, 4)
        cases.append(run_result(f"{recovery_run_prefix(REQUEST_ID)}provider-failed", mode="same_day_recovery",
                                health="provider_failed", origins=failed_origins, execution=failed_exec))
        for index, payload in enumerate(cases):
            with self.subTest(index=index):
                case = Path(self.tmp.name) / f"case-{index}"; case.mkdir()
                old = self.history; self.history = case
                try:
                    self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
                    trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
                    self.claim(); result = self.stage_ftr(self.stage_cfr(payload=payload))
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)
                    status = load_current_status(history_dir=self.history)
                    self.assertTrue(status["repair_required"])
                    self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)
                    self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["mode"], "same_day_recovery")
                finally:
                    self.history = old

    def test_snapshot_collision_different_bytes_fails_closed(self):
        self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        self.claim(); staged = self.stage_cfr()
        collision = self.history / f"data/ftr-feed/2026/08/20/{staged['radar_run_id']}.json"
        collision.parent.mkdir(parents=True, exist_ok=True); collision.write_bytes(b"different\n")
        result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)

    def test_checksum_mismatch_and_clear_failure_restore_latest(self):
        for kind in ("checksum", "clear"):
            with self.subTest(kind=kind):
                case = Path(self.tmp.name) / f"rollback-{kind}"; case.mkdir()
                old = self.history; self.history = case
                try:
                    self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
                    self.claim(); staged = self.stage_cfr()
                    if kind == "checksum":
                        from cheap_flight_radar import ftr_recovery as module
                        real = module.stage_snapshot
                        def bad(*args, **kwargs):
                            value = dict(real(*args, **kwargs)); value["snapshot_sha256"] = "0" * 64; return value
                        patcher = mock.patch("cheap_flight_radar.ftr_recovery.stage_snapshot", side_effect=bad)
                    else:
                        patcher = mock.patch("cheap_flight_radar.ftr_recovery.clear_repair_required",
                                             side_effect=FTRHandoffError("fixture post-latest clear failure"))
                    with patcher:
                        result = self.stage_ftr(staged)
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)
                    self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])
                finally:
                    self.history = old

    def test_reload_run_mode_sha_mismatch_fails_closed(self):
        for field, bad in (("run_id", "wrong"), ("mode", "canonical_daily"), ("producer_commit_sha", "c" * 40)):
            with self.subTest(field=field):
                case = Path(self.tmp.name) / f"reload-{field}"; case.mkdir()
                old = self.history; self.history = case
                try:
                    self.activate_repair(with_last_good=False); self.claim(); staged = self.stage_cfr()
                    from cheap_flight_radar import ftr_recovery as module
                    real = module.load_manifest_snapshot
                    def corrupted(*args, **kwargs):
                        value = dict(real(*args, **kwargs)); value[field] = bad; return value
                    with mock.patch("cheap_flight_radar.ftr_recovery.load_manifest_snapshot", side_effect=corrupted):
                        result = self.stage_ftr(staged)
                    self.assertEqual(result["status"], "failed")
                    self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
                    self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])
                finally:
                    self.history = old

    def test_cfr_evidence_survives_later_ftr_transaction_failure(self):
        self.activate_repair(); self.claim(); staged = self.stage_cfr()
        paths = [self.history / staged[key] for key in ("history_snapshot_path", "run_result_path", "recovery_manifest_path", "recovery_acquisition_path")]
        before = {p: p.read_bytes() for p in paths}
        with mock.patch("cheap_flight_radar.ftr_recovery.clear_repair_required", side_effect=FTRHandoffError("fixture")):
            result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        for path, content in before.items(): self.assertEqual(path.read_bytes(), content)

    def test_claimed_process_failure_preserves_trigger_and_consumes_request(self):
        self.activate_repair(); trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
        self.claim(); failed_id = f"{recovery_run_prefix(REQUEST_ID)}workflow-9001"
        stage_recovery_process_failure(history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
                                       application_sha=APP_SHA, attempt_run_id=failed_id,
                                       failed_at=f"{DAY}T09:45:00+08:00", reason="fixture provider failure")
        status = load_current_status(history_dir=self.history)
        self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)
        self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["run_id"], failed_id)
        state = inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
                                       application_sha=APP_SHA, current_date=DAY)
        self.assertEqual(state.status, "duplicate_request_claimed")

    def test_only_recovery_identity_can_clear(self):
        self.activate_repair()
        for mode in ("canonical_daily", "operator_reacquisition", "scoped_search"):
            with self.assertRaisesRegex(FTRHandoffError, "only same_day_recovery"):
                clear_repair_required(history_dir=self.history, recovery_run_id="irrelevant", attempt_mode=mode,
                                      cleared_at=f"{DAY}T10:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
