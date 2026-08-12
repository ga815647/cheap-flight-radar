from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ChinaMixedRoutingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "flight-radar.yaml").open("r", encoding="utf-8") as handle:
            cls.policy = yaml.safe_load(handle)
        cls.mixed = cls.policy["china"]["mixed_routing"]
        cls.local_access = cls.policy["routing"]["short_local_access"]
        cls.cost = cls.policy["cost"]

    def test_legacy_mixed_routing_return_window_is_not_a_hard_rejection(self):
        self.assertEqual(
            self.mixed["return_window_semantics"],
            "search_and_scoring_reference_not_hard_rejection",
        )
        self.assertTrue(self.mixed["gateway_expansion"]["do_not_require_trip_within_default_return_window"])
        current = self.policy["return_windows_policy"]
        self.assertEqual(current["role"], "search_hints_only")
        self.assertTrue(current["trip_length_does_not_affect_deal_status_or_ranking"])

    def test_legacy_gateway_logic_is_retained_but_not_active_product_scope(self):
        triggers = set(self.mixed["gateway_expansion"]["trigger_when"])
        self.assertEqual(
            triggers,
            {
                "serious_gateway_seed_has_current_exact_fare_evidence",
                "verified_practical_onward_or_open_jaw_edge_exists",
            },
        )
        self.assertFalse(self.policy["china"]["ferry_in_product_scope"])
        self.assertFalse(self.policy["china"]["gateway_modes"]["kinmen"]["enabled"])
        self.assertFalse(self.policy["china"]["gateway_modes"]["matsu"]["enabled"])

    def test_short_local_access_is_not_formal_deal_airfare(self):
        self.assertEqual(self.local_access["normalization"], "ignore_cost_and_comparative_time")
        self.assertFalse(self.local_access["exact_fare_or_duration_required"])
        self.assertFalse(self.local_access["can_fail_closed"])
        includes = set(self.cost["effective_total_transport_price_includes"])
        self.assertEqual(includes, {"international_airfare", "required_domestic_airfare", "required_baggage"})
        self.assertNotIn("required_airport_or_port_transfer", includes)
        self.assertNotIn("material_required_airport_or_port_transfer_excluding_short_local_access", includes)
        self.assertEqual(self.cost["formal_deal_price_semantics"], "complete_airfare_only")

    def test_legacy_mixed_routing_still_stops_on_unverifiable_branches_if_researched(self):
        stop_rules = set(self.mixed["stop_expansion_when"])
        self.assertIn("next_required_component_cannot_be_currently_revalidated", stop_rules)
        self.assertIn(
            "candidate_no_longer_competes_with_round_trip_benchmark_or_existing_expansions",
            stop_rules,
        )
        final = self.mixed["final_revalidation"]
        self.assertTrue(final["exact_airport_and_date_required_for_air_segments"])
        self.assertTrue(final["current_price_required_for_all_priced_segments"])
        self.assertEqual(final["essential_unknown_action"], "exploratory_not_verified")


if __name__ == "__main__":
    unittest.main()
