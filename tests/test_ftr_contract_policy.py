from pathlib import Path
import unittest

import yaml


class FTRContractPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))
        cls.ftr = cls.policy["ftr_handoff"]

    def test_contract_is_machine_ssot_and_activation_remains_disabled(self):
        self.assertEqual(self.ftr["schema_version"], "2.0")
        self.assertEqual(self.ftr["status"], "pending_activation")
        self.assertFalse(self.ftr["canonical_activation"]["enabled"])
        self.assertEqual(
            self.ftr["canonical_activation"]["enable_only_in_package"],
            "RP-04",
        )

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
