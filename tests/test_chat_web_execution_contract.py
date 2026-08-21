from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.models import SearchRequest
from cheap_flight_radar.source_router import build_source_plan


ROOT = Path(__file__).resolve().parents[1]


class ChatWebExecutionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        cls.routing = cls.policy["source_routing"]
        cls.contract = cls.routing["chat_web_execution_contract"]

    def test_machine_backend_and_chat_web_execution_planes_are_distinct(self):
        planes = self.routing["execution_planes"]
        self.assertTrue(planes["machine_backend"]["provider_search_coverage_authority"])
        self.assertTrue(planes["machine_backend"]["coverage_requires_actual_execution_evidence"])
        self.assertFalse(planes["chat_web_consumer_surface"]["provider_search_coverage_authority"])
        self.assertFalse(planes["chat_web_consumer_surface"]["machine_backend_coverage_authority"])
        self.assertEqual(self.contract["execution_plane"], "external_chatgpt_web_direct")
        self.assertEqual(self.contract["backend_integration_state"], "external_not_backend_integrated")

    def test_consumer_web_roles_separate_signal_from_exact_verification(self):
        roles = self.contract["roles"]
        self.assertIn("Signal", roles["opportunistic_discovery"]["evidence_may_establish"])
        self.assertFalse(roles["opportunistic_discovery"]["exact_fare_truth_without_revalidation"])
        exact = roles["exact_fare_itinerary_verification"]
        self.assertTrue(exact["allowed"])
        self.assertIn("current_complete_airfare", exact["requires"])
        self.assertIn("trusted_seller_or_metasearch_with_trusted_final_seller", exact["requires"])
        self.assertIn("exact_current_fare_evidence", exact["may_establish"])
        self.assertIn("existing_CFR_verification", exact["formal_deal_truth_role"])
        incomplete = roles["incomplete_or_lagged_observation"]
        self.assertEqual(incomplete["evidence_class"], "Signal")
        self.assertFalse(incomplete["formal_deal_eligible"])

    def test_provider_class_abstraction_has_evidence_backed_consumer_examples(self):
        classes = self.contract["provider_classes"]
        ota = classes["consumer_ota_web"]["qualified_examples"]
        meta = classes["consumer_metasearch_web"]["qualified_examples"]
        self.assertEqual(ota["trip_com"]["display_name"], "Trip.com")
        self.assertEqual(ota["expedia"]["display_name"], "Expedia")
        self.assertEqual(meta["skyscanner"]["display_name"], "Skyscanner")
        self.assertTrue(self.contract["example_membership_is_not_backend_qualification"])
        for examples in (ota, meta):
            for example in examples.values():
                self.assertEqual(example["disposition"], "seed_or_verification_only_under_current_access")
                self.assertTrue((ROOT / example["evidence"]).is_file())

    def test_web_browsing_never_establishes_exhaustive_or_backend_coverage(self):
        coverage = self.contract["coverage_semantics"]
        self.assertEqual(coverage["exhaustive_web_coverage_claim"], "forbidden")
        self.assertEqual(coverage["machine_backend_coverage_from_web_browsing"], "forbidden")
        self.assertEqual(coverage["canonical_provider_health_from_web_browsing"], "forbidden")
        self.assertFalse(coverage["web_attempt_satisfies_required_provider_search_slice"])
        self.assertEqual(coverage["no_usable_observation"], "no_observation_not_no_fare")
        self.assertEqual(coverage["inaccessible_or_restricted"], "access_unknown_not_fare_absence")
        self.assertEqual(coverage["unqueried_surface"], "not_attempted")
        self.assertEqual(coverage["scoped_window_success_without_actual_window_query"], "forbidden")

    def test_restricted_web_surfaces_route_to_typed_blind_spots_without_hidden_price(self):
        restricted = self.contract["roles"]["restricted_or_inaccessible_surface"]
        self.assertEqual(restricted["registry_authority"], "access_blind_spots")
        self.assertEqual(restricted["hidden_price_inference"], "forbidden")
        blind = self.policy["access_blind_spots"]
        self.assertTrue(blind["semantics"]["access_failure_does_not_prove_fare_absence"])
        self.assertEqual(blind["semantics"]["hidden_price_inference"], "forbidden")

    def test_contract_forbids_consumer_web_automation_and_preserves_machine_routing(self):
        access = self.contract["access_constraints"]
        self.assertTrue(access["public_without_login_required"])
        for key in (
            "login_or_member_session",
            "session_reuse_or_rotation",
            "captcha_bypass",
            "anti_bot_evasion",
            "browser_automation_subsystem",
            "crawler_subsystem",
        ):
            self.assertEqual(access[key], "forbidden")

        invariants = self.contract["routing_invariants"]
        self.assertEqual(invariants["machine_destination_free_primary"], "gflights_google_flight_deals")
        self.assertEqual(invariants["machine_known_route_primary"], "gflights_google_exact")
        self.assertEqual(invariants["machine_known_route_fallback"], "kiwi_mcp_exact")
        selected = self.routing["selected_routes"]["shared"]
        self.assertEqual(selected["origin_wide_discovery"]["primary_provider"], "gflights_google_flight_deals")
        self.assertIsNone(selected["origin_wide_discovery"]["automatic_executable_fallback"])
        self.assertEqual(selected["broad_discovery"]["primary_provider"], "gflights_google_exact")
        self.assertEqual(selected["broad_discovery"]["automatic_executable_fallback"], "kiwi_mcp_exact")

    def test_web_provider_cannot_be_promoted_to_automatic_route_plan_fallback(self):
        policy = deepcopy(self.policy)
        policy["source_routing"]["selected_routes"]["shared"]["broad_discovery"]["automatic_executable_fallback"] = (
            "chatgpt_web_public_fare_index"
        )
        request = SearchRequest(
            profile="world",
            search_stage="round_trip_benchmark",
            origin="TPE",
            destination="NRT",
            outbound_date="2026-10-05",
            return_date="2026-10-09",
            destination_country="JP",
        )
        plan = build_source_plan(request, policy, {})
        self.assertEqual(plan.coverage_state, "invalid_contract")
        self.assertEqual(plan.entries, ())
        self.assertIn("no canonical automatic fallback executor", plan.fallback_reason)

    def test_geography_ftr_contract_and_agents_authority_pointer_are_unchanged(self):
        self.assertEqual(self.policy["capability_state"]["current_runtime"]["destination_scope"], "asia_oceania")
        self.assertEqual(self.policy["search"]["destination_scope"], "asia_oceania")
        self.assertEqual(self.policy["search"]["origin_airports"], ["TPE", "TSA", "RMQ", "KHH"])
        self.assertEqual(self.policy["ftr_handoff"]["status"], "canonical_runtime_active_launch_ready")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("source_routing.chat_web_execution_contract", agents)


if __name__ == "__main__":
    unittest.main()
