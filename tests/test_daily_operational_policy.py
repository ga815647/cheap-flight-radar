from pathlib import Path
import unittest

import yaml


class DailyOperationalPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))

    def test_one_canonical_acquisition_attempt_per_taipei_day(self):
        acquisition = self.policy["price_history"]["persistence"]["canonical_daily_acquisition"]
        self.assertEqual(acquisition["local_day_timezone"], "Asia/Taipei")
        self.assertEqual(acquisition["max_automatic_attempts_per_local_day"], 1)
        self.assertEqual(acquisition["scope"], "routine_automatic_control_only")
        self.assertTrue(acquisition["claim_must_persist_before_live_provider_call"])
        self.assertEqual(
            acquisition["prior_claim_without_snapshot_action"],
            "fail_closed_no_automatic_same_day_reacquisition",
        )
        self.assertEqual(
            acquisition["claim_path_template"],
            "data/production-attempts/YYYY/MM/DD/canonical.json",
        )

    def test_local_runtime_control_and_no_github_production_path(self):
        orchestration = self.policy["publication"]["orchestration"]
        self.assertEqual(orchestration["primary_scheduler"], "openchamber_scheduled_local_run")
        local = orchestration["local_runtime"]
        self.assertEqual(local["runner"], "scripts/local_daily_radar.py")
        self.assertEqual(local["execution_plane"], "local_machine")
        self.assertEqual(local["request_local_date_timezone"], "Asia/Taipei")
        self.assertTrue(local["request_must_match_current_local_date"])
        self.assertEqual(local["concurrency"], "single_flight_flock_no_overlap")
        control = orchestration["canonical_daily_control"]
        self.assertEqual(control["request_mode"], "canonical_daily")
        self.assertEqual(control["request_local_date_timezone"], "Asia/Taipei")
        self.assertTrue(control["request_must_match_current_local_date"])
        operator = orchestration["operator_reacquisition_control"]
        self.assertEqual(operator["request_mode"], "operator_reacquisition")
        self.assertEqual(operator["request_local_date_timezone"], "Asia/Taipei")
        self.assertTrue(operator["request_must_match_current_local_date"])
        self.assertTrue(operator["request_id_required"])
        self.assertTrue(operator["requires_explicit_user_or_operator_request"])
        self.assertEqual(operator["scheduled_or_automatic_use"], "forbidden")
        explicit = self.policy["price_history"]["persistence"]["operator_requested_reacquisition"]
        self.assertTrue(explicit["enabled"])
        self.assertFalse(explicit["automatic_retry"])
        self.assertTrue(explicit["does_not_consume_or_replace_canonical_daily_claim"])
        self.assertTrue(explicit["does_not_overwrite_canonical_daily_snapshot"])
        self.assertEqual(
            orchestration["publication_recovery"],
            "immutable_run_evidence_without_reacquisition",
        )
        self.assertFalse(orchestration["github_actions_in_production_path"])
        self.assertEqual(orchestration["production_workflows"], "retired_use_local_runner")
        self.assertFalse(orchestration["independent_github_cron"])


if __name__ == "__main__":
    unittest.main()
