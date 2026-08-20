from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from cheap_flight_radar.ftr_recovery import recovery_claim_repository_path
from cheap_flight_radar.ftr_recovery_workflow import RecoveryWorkflowError, run_recovery_workflow
from ftr_recovery_fixtures import APP_SHA, DAY, REQUEST_ID, RecoveryFixtureMixin


class FTRRecoveryWorkflowPolicyTest(RecoveryFixtureMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = Path(".github/workflows/ftr-same-day-recovery.yml").read_text(encoding="utf-8")
        cls.driver = Path("src/cheap_flight_radar/ftr_recovery_workflow.py").read_text(encoding="utf-8")
        cls.canonical = Path(".github/workflows/canonical-production-radar.yml").read_text(encoding="utf-8")
        cls.operator = Path(".github/workflows/operator-production-radar.yml").read_text(encoding="utf-8")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.history, self.output = root / "history", root / "output"
        self.history.mkdir(); self.output.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def test_workflow_is_explicit_unscheduled_same_day_and_shared_concurrency(self):
        text = self.workflow
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("request_date:", text)
        self.assertIn("recovery_request_id:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("TZ=Asia/Taipei", text)
        self.assertIn("group: production-radar-acquisition", text)
        self.assertIn("group: production-radar-acquisition", self.canonical)
        self.assertIn("group: production-radar-acquisition", self.operator)

    def test_workflow_uses_current_main_application_and_durable_history_only(self):
        text = self.workflow
        self.assertIn("Checkout current application", text)
        self.assertIn("ref: main", text)
        self.assertIn('APP_SHA="$(git -C _app rev-parse HEAD)"', text)
        self.assertIn("ref: history/price-observations", text)
        self.assertIn("python -m cheap_flight_radar.ftr_recovery_workflow", text)
        self.assertNotIn("Radar Pages", text)
        self.assertNotIn("publication/radar-reports", text)
        self.assertNotIn("ops/radar-request", text)
        self.assertNotIn("ops/radar-operator-request", text)

    def test_driver_order_is_preflight_claim_acquisition_cfr_durable_then_ftr(self):
        body = self.driver[self.driver.index("def run_recovery_workflow"):self.driver.index("def main")]
        preflight = body.index("state = inspect_recovery_state")
        claim = body.index("write_recovery_claim")
        claim_commit = body.index('(\"data/ftr-recovery-attempts\",)')
        acquisition = body.index("acquisition = command_runner")
        cfr = body.index("cfr = stage_recovery_cfr_success_evidence")
        cfr_commit = body.index('(\"data/price-history\", \"data/run-evidence\")')
        ftr = body.index("ftr = stage_recovery_success")
        self.assertLess(preflight, claim)
        self.assertLess(claim, claim_commit)
        self.assertLess(claim_commit, acquisition)
        self.assertLess(acquisition, cfr)
        self.assertLess(cfr, cfr_commit)
        self.assertLess(cfr_commit, ftr)
        self.assertEqual(body.count("acquisition = command_runner"), 1)
        self.assertEqual(body.count('"cheap_flight_radar.production_runtime"'), 1)

    def test_application_sha_is_checkout_head_and_not_control_trigger_sha(self):
        body = self.driver[self.driver.index("def run_recovery_workflow"):self.driver.index("def main")]
        self.assertIn('application_sha = _git_output(app_dir, "rev-parse", "HEAD")', body)
        self.assertIn("trigger_sha=trigger_sha", body)
        self.assertIn("application_sha=application_sha", body)
        self.assertNotIn("application_sha=trigger_sha", body)

    def test_failure_artifact_is_best_effort_and_correctness_independent(self):
        tail = self.workflow[self.workflow.index("Upload recovery failure debug evidence best effort"):]
        self.assertIn("if: failure()", tail)
        self.assertIn("continue-on-error: true", tail)
        self.assertIn("retention-days: 2", tail)
        self.assertNotIn("data/ftr-feed", tail)
        self.assertNotIn("data/run-evidence", tail)

    def test_no_active_repair_and_duplicate_request_make_zero_provider_calls(self):
        self.canonical_success()
        runner = mock.Mock()
        with mock.patch("cheap_flight_radar.ftr_recovery_workflow._git_output", return_value=APP_SHA):
            with self.assertRaises(RecoveryWorkflowError):
                run_recovery_workflow(
                    app_dir=Path("app"), history_dir=self.history, output_dir=self.output,
                    request_date=DAY, request_id=REQUEST_ID, workflow_run_id="1",
                    workflow_run_url="https://example.invalid/1", trigger_sha="control",
                    debug_dir=Path(self.tmp.name) / "debug", current_date=DAY,
                    command_runner=runner)
        runner.assert_not_called()

        self.activate_repair(); self.claim()
        with mock.patch("cheap_flight_radar.ftr_recovery_workflow._git_output", return_value=APP_SHA):
            with self.assertRaises(RecoveryWorkflowError):
                run_recovery_workflow(
                    app_dir=Path("app"), history_dir=self.history, output_dir=self.output,
                    request_date=DAY, request_id=REQUEST_ID, workflow_run_id="2",
                    workflow_run_url="https://example.invalid/2", trigger_sha="control",
                    debug_dir=Path(self.tmp.name) / "debug2", current_date=DAY,
                    command_runner=runner)
        runner.assert_not_called()

    def test_claim_exists_before_single_failed_acquisition_and_no_hidden_retry(self):
        self.activate_repair()
        calls = []
        def runner(command, **kwargs):
            calls.append(tuple(command))
            self.assertTrue((self.history / recovery_claim_repository_path(DAY, REQUEST_ID)).exists())
            return subprocess.CompletedProcess(command, 1, stdout="fixture provider failure")
        with mock.patch("cheap_flight_radar.ftr_recovery_workflow._git_output", return_value=APP_SHA), \
             mock.patch("cheap_flight_radar.ftr_recovery_workflow._commit_and_push"), \
             mock.patch("cheap_flight_radar.ftr_recovery_workflow._reset_to_durable_remote"):
            with self.assertRaises(RecoveryWorkflowError):
                run_recovery_workflow(
                    app_dir=Path("app"), history_dir=self.history, output_dir=self.output,
                    request_date=DAY, request_id=REQUEST_ID, workflow_run_id="3",
                    workflow_run_url="https://example.invalid/3", trigger_sha="control",
                    debug_dir=Path(self.tmp.name) / "debug3", current_date=DAY,
                    command_runner=runner)
        self.assertEqual(len(calls), 1)
        self.assertIn("cheap_flight_radar.production_runtime", calls[0])
        self.assertIn("same_day_recovery", calls[0])


if __name__ == "__main__": unittest.main()
