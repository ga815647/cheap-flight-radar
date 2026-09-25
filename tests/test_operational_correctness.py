from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.operational_status import (
    decide_notification,
    derive_provider_health,
    reconcile_provider_failures,
    suppressed_request_count,
)

ROOT = Path(__file__).resolve().parents[1]


def execution_surface(**overrides):
    base = {"attempts": 0, "records": 0, "successes": 0, "empty": 0, "failures": 0, "unsupported": 0}
    base.update(overrides)
    return base


class OperationalCorrectnessTests(unittest.TestCase):
    def test_provider_counter_failure_forces_health_and_failure_evidence(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                "TPE": {"status": "attempted", "returned_flight_deals": 3, "explore_seeds": 2},
                "TSA": {"status": "attempted", "returned_flight_deals": 3, "explore_seeds": 2},
            },
            "execution": {
                "flight_deals": execution_surface(attempts=3, records=6, successes=1, failures=2),
                "explore": execution_surface(attempts=2, records=4, successes=2),
            },
        }
        existing = ({"origin": "TPE", "surface": "flight_deals", "error": "one explicit provider failure"},)
        failures = reconcile_provider_failures(coverage, existing)
        health = derive_provider_health(coverage, failures)
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["technical_failure_count"], 2)
        self.assertEqual(failures[0]["surface"], "flight_deals")
        reconciled = [item for item in failures if item.get("kind") == "counter_reconciliation"]
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["surface"], "flight_deals")
        self.assertIn("1 lacked explicit per-call failure evidence", reconciled[0]["error"])

    def test_complete_empty_is_not_technical_failure_but_broad_discovery_collapse_is_provider_failed(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                origin: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0}
                for origin in ("TPE", "TSA", "RMQ", "KHH")
            },
            "execution": {
                "flight_deals": execution_surface(attempts=12, empty=12),
                "explore": execution_surface(attempts=4, empty=4),
            },
        }
        failures = reconcile_provider_failures(coverage, ())
        health = derive_provider_health(coverage, failures)
        self.assertEqual(health["technical_failure_count"], 0)
        self.assertEqual(health["status"], "provider_failed")
        self.assertTrue(any(item.get("kind") == "coverage_collapse" for item in failures))

    def test_circuit_suppression_is_not_counted_as_new_technical_failure(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                origin: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0}
                for origin in ("TPE", "TSA", "RMQ", "KHH")
            },
            "execution": {
                "flight_deals": execution_surface(attempts=12, provider_calls=1, failures=1, suppressed=11),
                "explore": execution_surface(attempts=4, provider_calls=0, suppressed=4),
            },
        }
        existing = ({"origin": "TPE", "surface": "flight_deals", "error": "sticky HTTP 429"},)
        failures = reconcile_provider_failures(coverage, existing)
        health = derive_provider_health(coverage, failures)
        self.assertEqual(suppressed_request_count(coverage), 15)
        self.assertEqual(health["technical_failure_count"], 1)
        self.assertEqual(health["suppressed_request_count"], 15)
        self.assertEqual(health["status"], "provider_failed")
        self.assertTrue(any("circuit-suppressed" in reason for reason in health["reasons"]))

    def test_legacy_failure_counters_do_not_reclassify_healthy_coverage(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                origin: {"status": "attempted", "returned_flight_deals": 30, "explore_seeds": 20}
                for origin in ("TPE", "TSA", "RMQ", "KHH")
            },
            "execution": {
                "flight_deals": {"attempts": 12, "records": 330, "successes": 11, "failures": 1, "unsupported": 0},
                "explore": {"attempts": 4, "records": 283, "successes": 3, "failures": 1, "unsupported": 0},
            },
        }
        self.assertEqual(derive_provider_health(coverage, ())["status"], "healthy")

    def test_notification_decision_deal_failure_and_routine_no_change(self):
        self.assertEqual(
            decide_notification(meaningful_deal_count=1, provider_health_status="healthy"),
            {"notify": True, "reason": "meaningful_new_deal"},
        )
        self.assertEqual(
            decide_notification(meaningful_deal_count=0, provider_health_status="provider_failed"),
            {"notify": True, "reason": "provider_or_coverage_degradation"},
        )
        self.assertEqual(
            decide_notification(meaningful_deal_count=0, provider_health_status="healthy"),
            {"notify": False, "reason": "routine_no_meaningful_change"},
        )
        self.assertEqual(
            decide_notification(meaningful_deal_count=0, provider_health_status="healthy", operational_failure=True),
            {"notify": True, "reason": "operational_failure"},
        )

    def test_ssot_has_automatic_guard_operator_exception_and_final_evidence_notification_semantics(self):
        policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        canonical = policy["price_history"]["persistence"]["canonical_daily_acquisition"]
        operator = policy["price_history"]["persistence"]["operator_requested_reacquisition"]
        completion = policy["publication"]["orchestration"]["completion_evidence"]
        notifications = policy["notifications"]
        circuit = policy["operational_health"]["provider_acquisition"]["sticky_rate_limit_circuit"]
        self.assertEqual(canonical["max_automatic_attempts_per_local_day"], 1)
        self.assertTrue(operator["enabled"])
        self.assertEqual(operator["duplicate_same_request_id_action"], "recovery_or_noop_never_reacquire")
        self.assertTrue(completion["wait_for_workflow_terminal_state"])
        self.assertTrue(completion["read_final_immutable_run_evidence_before_notification_decision"])
        self.assertTrue(completion["control_request_submission_is_not_completion"])
        self.assertIn("provider_or_coverage_degradation", notifications["notify_on"])
        self.assertTrue(notifications["decision_requires_final_immutable_evidence"])
        self.assertEqual(circuit["fixed_client_lanes"], ["primary", "multi_city"])
        self.assertFalse(circuit["later_same_lane_logical_calls"]["invoke_provider_client"])
        self.assertFalse(circuit["later_same_lane_logical_calls"]["count_as_new_technical_failure"])
        self.assertFalse(circuit["complete_empty_opens_circuit"])
        self.assertFalse(circuit["generic_429_without_sticky_marker_opens_circuit"])
        self.assertEqual(circuit["reset_rate_limit"], "forbidden")
        self.assertFalse(circuit["automatic_retry"])

    def test_tracked_automation_prompt_scopes_same_day_guard_to_automatic_path_and_requires_final_evidence(self):
        text = (ROOT / "docs" / "daily-flight-radar-automation-prompt.md").read_text(encoding="utf-8")
        self.assertIn("automatic canonical path is limited to one claimed acquisition attempt per local day", text)
        self.assertIn("explicit user/operator request with a new unique request id", text)
        self.assertIn("Submitting the control request is not completion", text)
        self.assertIn("only decide user-facing status after that workflow reaches a terminal state", text)
        self.assertIn("final immutable `provider_health`", text)
        self.assertNotIn("same-day prior claim exists without a successful snapshot, fail closed and do not retry providers", text)


if __name__ == "__main__":
    unittest.main()
