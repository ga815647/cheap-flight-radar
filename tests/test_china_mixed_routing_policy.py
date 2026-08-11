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

    def test_return_window_is_not_a_hard_mixed_routing_rejection(self):
        self.assertEqual(
            self.mixed["return_window_semantics"],
            "search_and_scoring_reference_not_hard_rejection",
        )
        self.assertTrue(
            self.mixed["gateway_expansion"]["do_not_require_trip_within_default_return_window"]
        )

    def test_gateway_expansion_requires_current_fare_and_verified_edge(self):
        triggers = set(self.mixed["gateway_expansion"]["trigger_when"])
        self.assertEqual(
            triggers,
            {
                "serious_gateway_seed_has_current_exact_fare_evidence",
                "verified_practical_onward_or_open_jaw_edge_exists",
            },
        )
        second_city = self.mixed["second_city_selection"]
        self.assertTrue(second_city["require_verified_transport_edge"])
        self.assertTrue(second_city["geographic_proximity_alone_is_insufficient"])
        self.assertEqual(
            second_city["prefer_high_speed_rail_when"],
            "verified_rail_has_lower_required_transport_time_and_transfer_friction_than_domestic_flight",
        )
        self.assertEqual(
            second_city["use_domestic_flight_when"],
            "verified_rail_is_absent_or_materially_worse_for_total_required_transport_time",
        )
        self.assertIn("open_jaw", second_city["consider_open_jaw_when"])

    def test_mixed_routing_stops_on_unverifiable_or_noncompetitive_branches(self):
        stop_rules = set(self.mixed["stop_expansion_when"])
        self.assertIn("next_required_component_cannot_be_currently_revalidated", stop_rules)
        self.assertIn(
            "candidate_no_longer_competes_with_round_trip_benchmark_or_existing_expansions",
            stop_rules,
        )
        self.assertIn("deep_search_candidate_limit_reached", stop_rules)

        final = self.mixed["final_revalidation"]
        self.assertTrue(final["round_trip_benchmark_required"])
        self.assertTrue(final["exact_airport_and_date_required_for_air_segments"])
        self.assertTrue(final["current_price_required_for_all_priced_segments"])
        self.assertTrue(final["live_schedule_required_for_time_sensitive_ground_or_ferry_segments"])
        self.assertEqual(final["essential_unknown_action"], "exploratory_not_verified")


if __name__ == "__main__":
    unittest.main()
