from pathlib import Path
import unittest

import yaml


class FTRContractPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))
        cls.ftr = cls.policy["ftr_handoff"]

    def test_contract_is_machine_ssot_and_canonical_runtime_is_activated_by_rp04(self):
        self.assertEqual(self.ftr["schema_version"], "2.0")
        self.assertEqual(self.ftr["status"], "canonical_runtime_active_not_launch_ready")
        activation = self.ftr["canonical_activation"]
        self.assertTrue(activation["enabled"])
        self.assertEqual(activation["activated_by_package"], "RP-04")
        self.assertEqual(activation["runtime_module"], "cheap_flight_radar.canonical_ftr_runtime")
        self.assertEqual(activation["evidence_ref"], "history/price-observations")
        self.assertTrue(activation["readiness"]["canonical_producer_active"])
        self.assertFalse(activation["readiness"]["final_ftr_readiness"])
        self.assertIn("RP-05", activation["readiness"]["pending_packages"])

    def test_canonical_application_sha_comes_from_actual_main_checkout(self):
        checkout = self.ftr["canonical_activation"]["application_checkout"]
        self.assertEqual(checkout["ref"], "main")
        self.assertEqual(checkout["producer_commit_sha_source"], "actual_checkout_head")
        self.assertEqual(checkout["resolve_command"], "git_-C__app_rev-parse_HEAD")
        self.assertTrue(checkout["request_trigger_sha_forbidden_as_producer_commit_sha"])

    def test_canonical_write_order_is_snapshot_checksum_manifest_reload_status(self):
        order = self.ftr["canonical_activation"]["write_order"]
        self.assertEqual(
            order,
            [
                "durable_cfr_evidence_already_persisted",
                "build_and_validate_snapshot",
                "write_immutable_snapshot",
                "sha256_exact_persisted_snapshot_bytes",
                "write_canonical_latest_manifest",
                "reload_manifest_snapshot_checksum_and_run_identity",
                "write_current_status_from_exact_latest_snapshot",
            ],
        )
        persistence = self.ftr["persistence"]
        self.assertEqual(persistence["ref"], "history/price-observations")
        self.assertEqual(persistence["immutable_snapshot_path_template"], "data/ftr-feed/YYYY/MM/DD/{run_id}.json")
        self.assertEqual(persistence["canonical_latest_path"], "data/ftr-feed/latest.json")
        self.assertTrue(persistence["sha256_required"])
        self.assertTrue(persistence["manifest_write_last"])

    def test_canonical_failure_is_durable_repair_and_preserves_last_good(self):
        failure = self.ftr["canonical_activation"]["failure"]
        self.assertTrue(failure["set_repair_required"])
        self.assertTrue(failure["preserve_previous_latest_bytes"])
        self.assertTrue(failure["preserve_previous_immutable_snapshot_bytes"])
        self.assertEqual(
            failure["compact_failed_attempt_evidence_path_template"],
            "data/run-evidence/YYYY/MM/DD/{attempt_run_id}/ftr-failed-attempt.json",
        )
        self.assertEqual(failure["no_last_good_freshness"], "unavailable")
        self.assertEqual(failure["existing_last_good_freshness"], "stale_reference")
        self.assertFalse(failure["actions_artifact_correctness_dependency"])
        self.assertTrue(failure["cfr_evidence_survives_ftr_failure"])

    def test_active_repair_stays_rp05_boundary(self):
        repair = self.ftr["canonical_activation"]["active_repair"]
        self.assertTrue(repair["ordinary_canonical_daily_cannot_clear"])
        self.assertTrue(repair["ordinary_canonical_daily_cannot_advance_latest"])
        self.assertTrue(repair["ordinary_canonical_daily_cannot_masquerade_as_recovery"])
        self.assertEqual(repair["required_clear_mode"], "same_day_recovery")
        self.assertEqual(repair["recovery_orchestration_package"], "RP-05")
        self.assertEqual(repair["recovery_orchestration_status"], "pending")

    def test_modes_and_identity_separation_are_explicit(self):
        self.assertEqual(
            set(self.ftr["modes"]),
            {"canonical_daily", "scoped_search", "same_day_recovery"},
        )
        self.assertEqual(
            self.ftr["identity_separation"]["operator_reacquisition"],
            "cfr_acquisition_identity_not_ftr_snapshot_mode",
        )
        self.assertTrue(self.ftr["identity_separation"]["scoped_search_cannot_advance_canonical_latest"])
        self.assertTrue(self.ftr["identity_separation"]["scoped_or_operator_cannot_clear_repair_required"])

    def test_coverage_semantics_are_slice_faithful(self):
        coverage = self.ftr["coverage"]
        self.assertEqual(set(coverage["slice_states"]), {"succeeded", "failed", "not_attempted"})
        self.assertEqual(
            set(coverage["required_dimensions"]),
            {"provider", "surface", "origin", "market"},
        )
        self.assertTrue(coverage["unknown_or_inconsistent_action"] == "fail_closed")
        self.assertFalse(coverage["deal_count_is_coverage_or_provider_health_truth"])
        self.assertEqual(
            coverage["preferred_evidence"],
            "existing_normalized_execution_and_coverage_evidence",
        )

    def test_immutable_freshness_and_mutable_current_status_are_separate(self):
        freshness = self.ftr["freshness"]
        self.assertEqual(set(freshness["immutable_snapshot_states"]), {"fresh", "degraded"})
        self.assertEqual(
            set(freshness["mutable_current_states"]),
            {"fresh", "degraded", "stale_reference", "unavailable"},
        )
        self.assertTrue(freshness["later_failure_never_mutates_old_snapshot_bytes"])
        self.assertTrue(freshness["stale_reference_belongs_to_current_status_only"])

    def test_durable_repair_incident_and_clear_contract_are_explicit(self):
        current = self.ftr["current_status"]
        self.assertEqual(current["durable_store"], "github_repository")
        self.assertEqual(current["ref"], "history/price-observations")
        self.assertEqual(current["path"], "data/ftr-feed/current-status.json")
        self.assertTrue(current["failed_attempt_preserves_last_good_latest"])
        self.assertEqual(current["repair_required_clear"]["required_mode"], "same_day_recovery")
        self.assertTrue(current["repair_required_clear"]["requires_complete_coverage"])
        self.assertTrue(current["repair_required_clear"]["requires_fresh_snapshot"])
        self.assertTrue(current["repair_required_clear"]["requires_manifest_snapshot_checksum_match"])
        self.assertTrue(current["repair_required_clear"]["operator_reacquisition_cannot_clear"])
        self.assertTrue(current["repair_required_clear"]["scoped_search_cannot_clear"])
        self.assertTrue(current["repair_required_clear"]["publication_recovery_cannot_clear"])


if __name__ == "__main__":
    unittest.main()
