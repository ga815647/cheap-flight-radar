from pathlib import Path
import unittest

import yaml


class RetiredFeedContractPolicyTest(unittest.TestCase):
    """Downstream FTR feed is retired; absolute-low and scoped policy remains."""

    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))
        cls.ftr = cls.policy["ftr_handoff"]

    def test_downstream_feed_is_retired(self):
        self.assertEqual(
            self.ftr["status"],
            "downstream_feed_retired_absolute_low_and_scoped_retained",
        )
        for retired_key in (
            "same_day_recovery_orchestration",
            "canonical_activation",
            "schema_version",
            "schema_versioning",
            "modes",
            "identity_separation",
            "persistence",
            "coverage",
            "freshness",
            "current_status",
            "activation_dependencies",
        ):
            self.assertNotIn(retired_key, self.ftr)
        self.assertIn("route_shape_return_gateway_convergence", self.ftr)
        self.assertIn("scoped_search_acquisition", self.ftr)
        self.assertIn("absolute_low_non_deal_producer", self.ftr)

    def test_rp06_route_shape_return_gateway_machine_contract(self):
        contract = self.ftr["route_shape_return_gateway_convergence"]
        self.assertTrue(contract["enabled"])
        self.assertEqual(contract["package"], "RP-06")
        self.assertEqual(contract["capability_state"], "implemented_active")
        self.assertEqual(contract["runtime_module"], "cheap_flight_radar.production_runtime")
        self.assertEqual(contract["exact_variant_source"], "already_acquired_canonical_open_jaw_provider_results")
        self.assertEqual(contract["exact_non_deal_pool"], "current_run_exact_non_deal_candidates")
        self.assertFalse(contract["generic_signal_journal_is_admission_authority"])
        self.assertTrue(contract["rp02_absolute_low_selector_remains_admission_authority"])
        self.assertTrue(contract["deal_truth_and_ranking_unchanged"])
        self.assertEqual(contract["provider_calls_added_by_rp06"], 0)
        self.assertEqual(contract["mixed_return_provider_attempts_per_expansion_seed_max"], 1)
        self.assertTrue(contract["existing_destination_open_jaw_attempt_shape_unchanged"])
        self.assertEqual(contract["route_identity_source"], "exact_normalized_itinerary_legs")
        self.assertTrue(contract["destination_route_shape_defines_opportunity"])
        self.assertTrue(contract["taiwan_gateways_are_variants"])

        gateway = contract["gateway_coverage"]
        self.assertTrue(gateway["completion_validity_is_not_search_coverage"])
        self.assertEqual(gateway["primary_return_airports_semantics"], "bounded_search_pool_not_exhaustive_claim")
        self.assertFalse(gateway["automatic_search_exhaustive"])
        self.assertFalse(gateway["current_runtime_proactively_exhausts_extra_main_island_airports"])
        self.assertTrue(gateway["attempted_and_not_attempted_persisted"])
        self.assertEqual(gateway["run_result_coverage_key"], "return_gateway_expansion")
        self.assertTrue(gateway["opportunistic_non_primary_requires_live_route_evidence"])
        self.assertTrue(gateway["exact_revalidated_itinerary_is_live_route_evidence"])
        self.assertEqual(
            gateway["no_live_evidence_semantics"],
            "not_searched_not_eligible_as_opportunistic_extra",
        )

        return_policy = self.policy["search"]["return_to_taiwan"]
        self.assertEqual(
            return_policy["completion_scope"],
            "any_public_passenger_airport_on_taiwan_main_island",
        )
        self.assertTrue(return_policy["primary_return_search_airports_are_bounded_pool_not_exhaustive_claim"])
        self.assertFalse(return_policy["automatic_return_gateway_search_exhaustive"])
        self.assertTrue(return_policy["completion_validity_is_not_search_coverage"])
        self.assertTrue(return_policy["live_route_evidence_required_for_non_primary_return_airport"])

    def test_rp06_scoped_exclusion_is_resolved_not_hidden_pending_work(self):
        scoped = self.ftr["scoped_search_acquisition"]
        acquisition = scoped["acquisition"]
        self.assertEqual(acquisition["rp06_open_jaw_expansion"], "out_of_scope")
        self.assertEqual(
            acquisition["rp06_open_jaw_expansion_resolution"],
            "resolved_intentional_exclusion_from_bounded_scoped_coverage",
        )
        self.assertFalse(acquisition["canonical_route_variant_capability_implies_scoped_coverage"])

        semantics = scoped["semantics"]
        self.assertEqual(semantics["rp06_eligibility_expansion"], "out_of_scope")
        self.assertEqual(
            semantics["rp06_eligibility_expansion_resolution"],
            "resolved_intentional_exclusion_from_bounded_scoped_coverage",
        )
        self.assertEqual(semantics["route_variant_absence_without_provider_call"], "not_attempted")
        self.assertFalse(semantics["consumer_may_infer_canonical_route_variant_coverage"])

    def test_rp06_absolute_low_admission_preserves_rp02_authority(self):
        producer = self.ftr["absolute_low_non_deal_producer"]
        admission = producer["route_variant_candidate_admission"]
        self.assertEqual(admission["package"], "RP-06")
        self.assertEqual(admission["source"], "already_acquired_canonical_exact_multi_city_results")
        self.assertEqual(admission["state"], "exact_revalidated_candidate")
        self.assertTrue(admission["dedicated_pool_membership_required"])
        self.assertTrue(admission["generic_signal_membership_is_not_authority"])
        self.assertTrue(admission["rp02_eligibility_probe_required_before_pool_admission"])
        self.assertTrue(admission["final_rp02_bounded_selection_required"])
        self.assertEqual(admission["provider_calls"], 0)
        self.assertEqual(producer["budget"]["new_provider_calls"], 0)
        self.assertEqual(producer["budget"]["max_selected_count"], 5)
        self.assertEqual(producer["anomaly_ranking_role"], "none")
        self.assertEqual(producer["ftr_weighted_score"], "forbidden")
        self.assertTrue(producer["normal_cfr_deal_ranking_unchanged"])
        self.assertEqual(producer["canonical_ftr_activation"], "retired_downstream_feed_removed")

    def test_scoped_persistence_points_at_scoped_search_store(self):
        persistence = self.ftr["scoped_search_acquisition"]["persistence"]
        self.assertEqual(
            persistence["immutable_snapshot"],
            "data/scoped-search/YYYY/MM/DD/{run_id}.json",
        )
        self.assertEqual(
            persistence["scoped_manifest"],
            "data/scoped-search/{run_id}.json",
        )
        self.assertTrue(persistence["checksum_required"])
        self.assertTrue(persistence["manifest_write_last"])


if __name__ == "__main__":
    unittest.main()
