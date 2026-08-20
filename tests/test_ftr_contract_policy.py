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
        self.assertTrue(activation["readiness"]["recovery_capability_active"])
        self.assertFalse(activation["readiness"]["recovery_live_proof_complete"])
        self.assertFalse(activation["readiness"]["final_ftr_readiness"])
        self.assertNotIn("RP-05", activation["readiness"]["pending_packages"])
        self.assertEqual(set(activation["readiness"]["pending_packages"]), {"RP-06", "RP-07", "RP-08"})

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

    def test_active_repair_rp05_capability_is_active_while_live_proof_remains_pending(self):
        repair = self.ftr["canonical_activation"]["active_repair"]
        self.assertTrue(repair["ordinary_canonical_daily_cannot_clear"])
        self.assertTrue(repair["ordinary_canonical_daily_cannot_advance_latest"])
        self.assertTrue(repair["ordinary_canonical_daily_cannot_masquerade_as_recovery"])
        self.assertEqual(repair["required_clear_mode"], "same_day_recovery")
        self.assertEqual(repair["recovery_orchestration_package"], "RP-05")
        self.assertEqual(repair["recovery_orchestration_status"], "pending")
        self.assertEqual(
            repair["recovery_orchestration_status_semantics"],
            "live_proof_pending_not_capability_implementation",
        )
        self.assertEqual(repair["recovery_capability_state"], "implemented_active")
        self.assertEqual(repair["live_recovery_proof_status"], "pending")

    def test_rp05_same_day_recovery_machine_contract(self):
        recovery = self.ftr["same_day_recovery_orchestration"]
        self.assertTrue(recovery["enabled"])
        self.assertEqual(recovery["package"], "RP-05")
        self.assertEqual(recovery["contract_version"], "1.0")
        self.assertEqual(recovery["capability_state"], "implemented_active")
        self.assertEqual(recovery["live_proof_status"], "pending")
        self.assertFalse(recovery["scheduled"])
        self.assertEqual(recovery["workflow"], ".github/workflows/ftr-same-day-recovery.yml")
        self.assertEqual(recovery["driver_module"], "cheap_flight_radar.ftr_recovery_workflow")
        self.assertEqual(recovery["transaction_module"], "cheap_flight_radar.ftr_recovery")

        request = recovery["request"]
        self.assertEqual(set(request["required_fields"]), {"request_date", "recovery_request_id"})
        self.assertEqual(request["local_day_timezone"], "Asia/Taipei")
        self.assertTrue(request["request_date_must_equal_current_local_day"])
        self.assertTrue(request["request_id_path_safe"])
        self.assertTrue(request["new_explicit_id_required_for_each_additional_acquisition"])
        self.assertEqual(request["duplicate_request_provider_calls"], 0)

        identity = recovery["identity"]
        self.assertEqual(
            identity["claim_path_template"],
            "data/ftr-recovery-attempts/YYYY/MM/DD/{request_id}.json",
        )
        self.assertEqual(identity["run_id_prefix_template"], "ftr-recovery-{request_id}-")
        self.assertEqual(identity["mode"], "same_day_recovery")
        self.assertEqual(identity["application_sha_source"], "actual_current_main_checkout_head")
        self.assertTrue(identity["original_repair_incident_identity_required"])
        self.assertEqual(identity["canonical_daily_claim_consumption"], "forbidden")
        self.assertEqual(identity["canonical_daily_snapshot_rewrite"], "forbidden")
        self.assertEqual(identity["operator_claim_reuse"], "forbidden")
        self.assertEqual(identity["scoped_search_identity_reuse"], "forbidden")

        preflight = recovery["preflight"]
        self.assertTrue(preflight["current_status_required_and_valid"])
        self.assertTrue(preflight["active_repair_required"])
        self.assertTrue(preflight["repair_trigger_and_latest_failed_evidence_readable"])
        self.assertTrue(preflight["prior_last_good_and_latest_guard_required"])
        self.assertEqual(preflight["recovery_namespace_collision_action"], "fail_closed")
        self.assertTrue(preflight["claim_created_only_after_preflight"])
        self.assertEqual(preflight["no_active_repair_provider_calls"], 0)
        self.assertEqual(preflight["duplicate_request_provider_calls"], 0)

        acquisition = recovery["acquisition"]
        self.assertTrue(acquisition["reuse_production_runtime"])
        self.assertTrue(acquisition["reuse_existing_provider_adapter"])
        self.assertTrue(acquisition["reuse_source_router_and_exact_revalidation"])
        self.assertEqual(acquisition["execution_mode"], "same_day_recovery")
        self.assertEqual(acquisition["shared_concurrency_group"], "production-radar-acquisition")
        self.assertEqual(acquisition["provider_invocations_per_claimed_request"], 1)
        self.assertEqual(acquisition["hidden_retry"], "forbidden")
        self.assertEqual(acquisition["new_provider"], "forbidden")
        self.assertTrue(acquisition["sticky_429_semantics_unchanged"])
        self.assertEqual(acquisition["proxy_ua_session_rotation"], "forbidden")

        persistence = recovery["persistence"]
        self.assertEqual(persistence["durable_ref"], "history/price-observations")
        self.assertTrue(persistence["claim_must_commit_before_acquisition"])
        self.assertTrue(persistence["legitimate_cfr_evidence_must_commit_before_ftr_transaction"])
        self.assertTrue(persistence["cfr_evidence_survives_later_ftr_failure"])
        self.assertFalse(persistence["actions_artifact_correctness_dependency"])

        order = recovery["success_order"]
        self.assertLess(order.index("write_immutable_recovery_snapshot"), order.index("write_canonical_latest_to_exact_recovery_snapshot"))
        self.assertLess(
            order.index("reload_and_revalidate_checksum_run_id_mode_and_application_sha"),
            order.index("clear_repair_required_only_after_reload_validation"),
        )

        failure = recovery["failure"]
        self.assertTrue(failure["restore_prior_canonical_latest_exact_bytes_or_absence"])
        self.assertTrue(failure["preserve_prior_last_good_snapshot_exact_bytes"])
        self.assertTrue(failure["preserve_original_repair_trigger"])
        self.assertTrue(failure["repair_required_remains_true"])
        self.assertFalse(failure["automatic_second_provider_attempt"])
        self.assertEqual(recovery["publication_dispatch"], "forbidden_in_RP-05")
        self.assertEqual(recovery["artifacts"]["role"], "best_effort_debug_only")
        self.assertTrue(recovery["artifacts"]["continue_on_error"])

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
        self.assertTrue(self.ftr["identity_separation"]["same_day_recovery_is_only_current_repair_clear_identity"])

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
