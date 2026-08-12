from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.scoring import (
    composite_score,
    departure_lead_time_bucket,
    transport_efficiency,
    trip_length_fit,
)


ROOT = Path(__file__).resolve().parents[1]


class ScoringPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "flight-radar.yaml").open("r", encoding="utf-8") as handle:
            cls.policy = yaml.safe_load(handle)

    def test_search_scope_origins_and_horizon_semantics(self):
        search = self.policy["search"]
        self.assertEqual(search["destination_scope"], "asia_oceania")
        self.assertEqual(set(search["origin_airports"]), {"TPE", "TSA", "RMQ", "KHH"})
        self.assertEqual(search["horizon_days"], 120)
        self.assertEqual(search["horizon_semantics"], "default_compute_budget_not_product_bound")
        self.assertTrue(search["horizon_extension_allowed_when_provider_surface_is_cheap"])
        self.assertEqual(search["weekday_restriction"], "none")

    def test_global_radar_requires_each_configured_origin_attempt(self):
        gate = self.policy["search"]["coverage_gate"]
        self.assertTrue(gate["enabled"])
        self.assertTrue(gate["require_attempt_for_each_origin_airport"])
        self.assertTrue(gate["report_origin_coverage"])
        self.assertEqual(gate["incomplete_origin_coverage_action"], "mark_missing_and_do_not_claim_full_radar")

    def test_return_to_taiwan_accepts_any_live_main_island_passenger_airport(self):
        return_policy = self.policy["search"]["return_to_taiwan"]
        self.assertEqual(return_policy["completion_scope"], "any_public_passenger_airport_on_taiwan_main_island")
        self.assertTrue(return_policy["outbound_discovery_origin_scope_is_separate"])
        self.assertEqual(set(return_policy["primary_return_search_airports"]), {"TPE", "TSA", "RMQ", "KHH"})
        self.assertTrue(return_policy["opportunistic_main_island_return_airports_allowed"])
        self.assertTrue(return_policy["different_return_airport_allowed"])
        self.assertTrue(return_policy["final_main_island_arrival_counts_as_trip_complete"])
        self.assertTrue(return_policy["post_arrival_main_island_ground_access_is_not_required_component"])
        self.assertTrue(self.policy["fare_policy"]["allow_mixed_taiwan_airports"])

    def test_taiwan_airport_labels_are_airport_specific(self):
        display = self.policy["search"]["display_policy"]
        self.assertEqual(
            display["taiwan_airport_labels"],
            {"TPE": "桃園", "TSA": "松山", "RMQ": "台中", "KHH": "高雄"},
        )
        self.assertTrue(display["include_iata_with_airport_label"])
        self.assertTrue(display["forbid_taipei_alias_for_tpe_or_tsa"])
        self.assertEqual(set(display["forbidden_ambiguous_taiwan_origin_labels"]), {"台北", "Taipei"})

    def test_market_profiles_are_priority_slices_on_shared_pipeline(self):
        profiles = self.policy["search"]["daily_profiles"]
        self.assertTrue(profiles["enabled"])
        self.assertTrue(profiles["shared_origin_coverage"])
        self.assertTrue(profiles["unified_final_ranking"])
        self.assertEqual(set(profiles["profiles"]), {"world", "japan", "korea", "china"})
        for name in ("world", "japan", "korea", "china"):
            self.assertEqual(profiles["profiles"][name]["mode"], "priority_coverage_with_shared_pipeline")
        self.assertEqual(profiles["profiles"]["world"]["destination_scope"], "asia_oceania")
        architecture = self.policy["search"]["search_architecture"]
        self.assertFalse(architecture["market_specialist_pipeline_required"])
        self.assertEqual(architecture["brute_force_city_date_city_matrix"], "forbidden_by_default")

    def test_direct_round_trip_deals_and_weak_seeds_are_both_first_class_inputs(self):
        architecture = self.policy["search"]["search_architecture"]
        self.assertIn("qualified_round_trip_deal", architecture["accepted_seed_kinds"])
        self.assertIn("one_way_fare", architecture["accepted_seed_kinds"])
        self.assertTrue(architecture["direct_qualified_round_trip_deal_can_skip_return_construction"])
        self.assertTrue(architecture["cheap_one_way_or_explore_seed_requires_endpoint_specific_completion"])
        self.assertTrue(architecture["expand_open_jaw_only_for_competitive_endpoints"])

    def test_formal_deal_ranking_is_anomaly_then_complete_airfare(self):
        ranking = self.policy["ranking"]
        self.assertEqual(
            ranking["formal_deal_order"],
            ["relative_anomaly_strength_desc", "current_complete_airfare_twd_asc"],
        )
        self.assertEqual(ranking["primary_user_facing_views"], ["deals", "signals"])
        self.assertEqual(ranking["legacy_absolute_price_views_status"], "diagnostic_only_not_first_class_deal_views")
        self.assertFalse(self.policy["penalties"]["applies_to_formal_deal_ranking"])
        self.assertFalse(self.policy["fare_policy"]["self_transfer_penalty"])
        self.assertIn("trip_length_fit", ranking["formal_deal_ignores"])
        self.assertIn("connection_count", ranking["formal_deal_ignores"])
        self.assertIn("self_transfer", ranking["formal_deal_ignores"])
        self.assertIn("airline_brand", ranking["formal_deal_ignores"])

    def test_legacy_price_views_are_retained_only_as_diagnostics(self):
        ranking = self.policy["ranking"]
        self.assertIn("near_term_cheapest", ranking["preserve_views"])
        self.assertIn("absolute_cheapest", ranking["preserve_views"])
        self.assertEqual(ranking["legacy_absolute_price_views_status"], "diagnostic_only_not_first_class_deal_views")

    def test_history_is_fallback_not_required_deal_truth(self):
        history = self.policy["price_history"]
        self.assertEqual(history["role"], "supplemental_evidence_and_fallback_anomaly_truth")
        self.assertFalse(history["required_for_formal_deal"])
        external = history["external_anomaly_truth"]
        self.assertTrue(external["preferred"])
        self.assertEqual(
            external["priority"],
            ["google_flight_deals", "google_flights_exact_price_insight", "own_price_history"],
        )
        self.assertEqual(external["conflict_resolution"], "explicit_source_priority_never_average")

    def test_historical_price_comparison_utility_still_uses_lead_time_buckets(self):
        history = self.policy["price_history"]
        self.assertEqual(
            [bucket["id"] for bucket in history["departure_lead_time_buckets_days"]],
            ["d0_14", "d15_30", "d31_60", "d61_120"],
        )
        self.assertEqual(departure_lead_time_bucket(0, history), "d0_14")
        self.assertEqual(departure_lead_time_bucket(15, history), "d15_30")
        self.assertEqual(departure_lead_time_bucket(45, history), "d31_60")
        self.assertEqual(departure_lead_time_bucket(120, history), "d61_120")
        with self.assertRaises(ValueError):
            departure_lead_time_bucket(121, history)

    def test_china_ferry_gateways_are_out_of_product_scope(self):
        china = self.policy["china"]
        self.assertFalse(china["ferry_in_product_scope"])
        self.assertFalse(china["coverage_gate"]["enabled"])
        self.assertEqual(china["coverage_gate"]["required_modes"], ["direct_air"])
        self.assertFalse(china["gateway_modes"]["kinmen"]["enabled"])
        self.assertFalse(china["gateway_modes"]["matsu"]["enabled"])
        self.assertEqual(china["ferry_data_policy"]["status"], "retained_historical_reference_not_active_product_policy")
        self.assertEqual(china["ferry_evaluation"]["status"], "retained_historical_reference_not_active_product_policy")
        self.assertFalse(self.policy["routing"]["ferry_in_product_scope"])
        self.assertNotIn("ferry", self.policy["routing"]["positioning_modes"])

    def test_internal_legacy_scoring_utilities_remain_available_but_not_formal_rank(self):
        short = trip_length_fit(13.0, 3, self.policy)
        adequate = trip_length_fit(13.0, 10, self.policy)
        self.assertLess(short, 0.5)
        self.assertEqual(adequate, 1.0)
        efficient = transport_efficiency(8.0, 9.0)
        inefficient = transport_efficiency(8.0, 20.0)
        self.assertGreater(efficient, inefficient)
        self.assertEqual(
            self.policy["ranking"]["composite_score"]["role"],
            "internal_discovery_ordering_only_not_formal_deal_ranking",
        )

    def test_usable_stopover_math_remains_descriptive_not_deal_rank(self):
        pure_wait = transport_efficiency(8.0, 20.0)
        partly_usable = transport_efficiency(8.0, 20.0, usable_stopover_hours=10.0)
        self.assertAlmostEqual(pure_wait, 0.4)
        self.assertAlmostEqual(partly_usable, 0.8)
        self.assertEqual(self.policy["usable_time"]["formal_deal_ranking_role"], "none")

    def test_composite_score_function_remains_for_internal_candidate_ordering(self):
        components = {
            "effective_total_price": 1.0,
            "route_value": 0.0,
            "trip_length_fit": 0.0,
            "transport_efficiency": 0.0,
        }
        score = composite_score(components, self.policy["ranking"])
        self.assertAlmostEqual(score, 35.0)

    def test_formal_deal_cost_is_complete_airfare_not_lodging_or_local_transfer(self):
        cost = self.policy["cost"]
        self.assertEqual(cost["formal_deal_price_semantics"], "complete_airfare_only")
        self.assertEqual(
            cost["effective_total_transport_price_includes"],
            ["international_airfare", "required_domestic_airfare", "required_baggage"],
        )
        self.assertIn("lodging_including_transport_caused_overnight", cost["exclude_by_default"])


if __name__ == "__main__":
    unittest.main()
