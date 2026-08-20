from pathlib import Path
import json
import tempfile
import unittest

from cheap_flight_radar.ftr_handoff import FTRHandoffError, clear_repair_required, load_current_status
from cheap_flight_radar.ftr_recovery import (
    inspect_recovery_state,
    recovery_claim_repository_path,
    recovery_run_prefix,
    stage_recovery_process_failure,
)
from cheap_flight_radar.production_operations import claim_repository_path
from ftr_recovery_fixtures import APP_SHA, DAY, REQUEST_ID, RecoveryFixtureMixin


class FTRRecoveryIdentityTest(RecoveryFixtureMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.history, self.output = root / "history", root / "output"
        self.history.mkdir(); self.output.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def inspect(self, request_id=REQUEST_ID, requested_date=DAY, current_date=DAY):
        return inspect_recovery_state(history_dir=self.history, requested_date=requested_date,
                                      request_id=request_id, application_sha=APP_SHA,
                                      current_date=current_date)

    def test_no_active_repair_and_missing_status_fail_before_claim(self):
        with self.assertRaisesRegex(FTRHandoffError, "current status is missing"):
            self.inspect()
        self.canonical_success()
        state = self.inspect()
        self.assertEqual(state.status, "no_active_repair")
        self.assertFalse((self.history / recovery_claim_repository_path(DAY, REQUEST_ID)).exists())
        with self.assertRaisesRegex(FTRHandoffError, "no_active_repair"):
            self.claim()

    def test_claim_is_recovery_specific_and_does_not_consume_canonical_claim(self):
        self.activate_repair(); self.claim()
        path = self.history / recovery_claim_repository_path(DAY, REQUEST_ID)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["mode"], "same_day_recovery")
        self.assertEqual(payload["application_sha"], APP_SHA)
        self.assertEqual(payload["run_prefix"], recovery_run_prefix(REQUEST_ID))
        self.assertFalse((self.history / claim_repository_path(DAY)).exists())

    def test_duplicate_request_is_consumed_and_new_request_id_is_required(self):
        self.activate_repair(); self.claim()
        self.assertEqual(self.inspect().status, "duplicate_request_claimed")
        with self.assertRaisesRegex(FTRHandoffError, "duplicate_request_claimed"):
            self.claim()
        self.assertEqual(self.inspect("repair-20260820-b").status, "acquire")

    def test_same_day_path_safe_and_application_sha_guards(self):
        self.activate_repair()
        with self.assertRaisesRegex(FTRHandoffError, "Asia/Taipei current day"):
            self.inspect(requested_date="2026-08-19")
        with self.assertRaisesRegex(FTRHandoffError, "path-safe"):
            self.inspect(request_id="../bad/request")
        with self.assertRaisesRegex(FTRHandoffError, "40-hex"):
            inspect_recovery_state(history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
                                   application_sha="trigger-sha", current_date=DAY)

    def test_claimed_process_failure_preserves_trigger_and_never_reopens_same_id(self):
        self.activate_repair()
        trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
        self.claim(); run_id = f"{recovery_run_prefix(REQUEST_ID)}workflow-9001"
        result = stage_recovery_process_failure(
            history_dir=self.history, requested_date=DAY, request_id=REQUEST_ID,
            application_sha=APP_SHA, attempt_run_id=run_id,
            failed_at=f"{DAY}T09:45:00+08:00", reason="fixture provider failure")
        self.assertEqual(result["status"], "failed")
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)
        self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["run_id"], run_id)
        self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["mode"], "same_day_recovery")
        self.assertEqual(self.inspect().status, "duplicate_request_claimed")

    def test_canonical_operator_and_scoped_identities_cannot_clear(self):
        self.activate_repair()
        for mode in ("canonical_daily", "operator_reacquisition", "scoped_search"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(FTRHandoffError, "only same_day_recovery"):
                    clear_repair_required(history_dir=self.history, recovery_run_id="irrelevant",
                                          attempt_mode=mode, cleared_at=f"{DAY}T10:00:00+08:00")


if __name__ == "__main__": unittest.main()
