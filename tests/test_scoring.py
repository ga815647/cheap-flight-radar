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

    def test_v01_has_no_weekday_restriction(self):
        self.assertEqual(self.policy["search"]["weekday_restriction"], "none")

    def test_global_radar_requires_each_configured_origin_attempt(self):
        search = self.policy["search"]
        self.assertEqual(set(search["origin_airports"]), {"TPE", "TSA", "RMQ", "KHH"})
        self.assertTrue(search["coverage_gate"]["enabled"])
        self.assertTrue(search["coverage_gate"]["require_attempt_for_each_origin_airport"])
        self.assertTrue(search["coverage_gate"]["report_origin_coverage"])
        self.assertEqual(
            search["coverage_gate"]["incomplete_origin_coverage_action"],
            "mark_missing_and_do_not_claim_full_radar",
        )

    def test_return_to_taiwan_accepts_any_live_main_island_passenger_airport(self):
        return_policy = self.policy["search"]["return_to_taiwan"]
        self.assertEqual(
            return_policy["completion_scope"],
            "any_public_passenger_airport_on_taiwan_main_island",
        )
        self.assertTrue(return_policy["outbound_discovery_origin_scope_is_separate"])
        self.assertEqual(
            set(return_policy["primary_return_search_airports"]),
            {"TPE", "TSA", "RMQ", "KHH"},
        )
        self.assertTrue(return_policy["opportunistic_main_island_return_airports_allowed"])
        self.assertTrue(return_policy["live_route_evidence_required_for_non_primary_return_airport"])
        self.assertTrue(return_policy["different_return_airport_allowed"])
        self.assertTrue(return_policy["final_main_island_arrival_counts_as_trip_complete"])
        self.assertTrue(return_policy["post_arrival_main_island_ground_access_is_not_required_component"])
        self.assertTrue(return_policy["coverage_gate_applies_to_outbound_origins_not_every_possible_return_airport"])
        self.assertTrue(self.policy["fare_policy"]["allow_mixed_taiwan_airports"])

    def test_taiwan_airport_labels_are_airport_specific(self):
        display = self.policy["search"]["display_policy"]
        self.assertEqual(
            display["taiwan_airport_labels"],
            {"TPE": "桃園", "TSA": "松山", "RMQ": "台中", "KHH": "高雄"},
        )
        self.assertTrue(display["include_iata_with_airport_label"])
        self.assertTrue(display["require_airport_specific_taiwan_label"])
        self.assertTrue(display["forbid_taipei_alias_for_tpe_or_tsa"])
        self.assertEqual(
            set(display["forbidden_ambiguous_taiwan_origin_labels"]),
            {"台北", "Taipei"},
        )

    def test_daily_profiles_are_world_japan_korea_china(self):
        profiles = self.policy["search"]["daily_profiles"]
        self.assertTrue(profiles["enabled"])
        self.assertTrue(profiles["shared_origin_coverage"])
        self.assertTrue(profiles["unified_final_ranking"])
        self.assertEqual(set(profiles["profiles"]), {"world", "japan", "korea", "china"})
        self.assertEqual(profiles["profiles"]["world"]["mode"], "broad_discovery")
        self.assertEqual(profiles["profiles"]["japan"]["mode"], "specialist_deep")
        self.assertEqual(profiles["profiles"]["korea"]["mode"], "specialist_deep")
        self.assertEqual(profiles["profiles"]["china"]["mode"], "specialist_deep")

    def test_world_discovery_does_not_deep_expand_specialist_countries(self):
        world = self.policy["search"]["daily_profiles"]["profiles"]["world"]
        self.assertTrue(world["include_specialist_countries_in_discovery"])
        self.assertFalse(world["specialist_country_deep_expansion"])
        self.assertEqual(set(world["specialist_countries"]), {"JP", "KR", "CN"})

    def test_price_views_separate_near_term_from_horizon_floor(self):
        search = self.policy["search"]
        views = search["price_time_views"]
        self.assertTrue(views["near_term"]["enabled"])
        self.assertEqual(views["near_term"]["departure_within_days"], 30)
        self.assertTrue(views["horizon_absolute"]["enabled"])
        self.assertEqual(views["horizon_absolute"]["departure_within_days"], "inherit_search_horizon")
        self.assertTrue(views["do_not_treat_near_term_premium_as_horizon_floor"])
        self.assertTrue(views["do_not_stop_floor_search_after_coarse_target_band_hit"])
        self.assertIn("near_term_cheapest", self.policy["ranking"]["preserve_views"])
        self.assertIn("absolute_cheapest", self.policy["ranking"]["preserve_views"])

    def test_historical_price_comparison_uses_lead_time_buckets(self):
        history = self.policy["price_history"]
        self.assertEqual(
            [bucket["id"] for bucket in history["departure_lead_time_buckets_days"]],
            ["d0_14", "d15_30", "d31_60", "d61_120"],
        )
        self.assertIn("departure_lead_time_bucket", history["comparison_dimensions"])
        self.assertEqual(departure_lead_time_bucket(0, history), "d0_14")
        self.assertEqual(departure_lead_time_bucket(14, history), "d0_14")
        self.assertEqual(departure_lead_time_bucket(15, history), "d15_30")
        self.assertEqual(departure_lead_time_bucket(30, history), "d15_30")
        self.assertEqual(departure_lead_time_bucket(45, history), "d31_60")
        self.assertEqual(departure_lead_time_bucket(120, history), "d61_120")
        with self.assertRaises(ValueError):
            departure_lead_time_bucket(121, history)

    def test_korea_floor_scan_is_not_seoul_busan_only(self):
        korea = self.policy["search"]["daily_profiles"]["profiles"]["korea"]
        self.assertEqual(korea["floor_scan_policy"], "all_relevant_korean_airports_not_only_seoul_or_busan")
        self.assertFalse(korea["floor_scan_seed_list_exhaustive"])
        self.assertEqual(
            set(korea["floor_scan_seed_airports"]),
            {"ICN", "GMP", "PUS", "CJU", "TAE", "CJJ"},
        )

    def test_shared_broad_discovery_keeps_both_fare_floors(self):
        requirements = self.policy["source_routing"]["selected_routes"]["shared"]["broad_discovery"]["query_requirements"]
        self.assertTrue(requirements["retain_near_term_floor"])
        self.assertTrue(requirements["retain_horizon_absolute_floor"])
        self.assertTrue(requirements["continue_floor_scan_after_coarse_target_band_hit"])

    def test_long_haul_too_short_is_penalized(self):
        short = trip_length_fit(13.0, 3, self.policy)
        adequate = trip_length_fit(13.0, 10, self.policy)
        self.assertLess(short, 0.5)
        self.assertEqual(adequate, 1.0)

    def test_short_haul_three_nights_can_score_full_fit(self):
        self.assertEqual(trip_length_fit(2.0, 3, self.policy), 1.0)

    def test_excess_connection_time_reduces_efficiency(self):
        efficient = transport_efficiency(8.0, 9.0)
        inefficient = transport_efficiency(8.0, 20.0)
        self.assertGreater(efficient, inefficient)

    def test_verified_usable_stopover_reduces_wait_penalty_without_bonus(self):
        pure_wait = transport_efficiency(8.0, 20.0)
        partly_usable = transport_efficiency(8.0, 20.0, usable_stopover_hours=10.0)
        fully_credited = transport_efficiency(8.0, 20.0, usable_stopover_hours=20.0)
        self.assertAlmostEqual(pure_wait, 0.4)
        self.assertAlmostEqual(partly_usable, 0.8)
        self.assertEqual(fully_credited, 1.0)

    def test_usable_stopover_policy_requires_verified_excursion_not_duration_alone(self):
        usable = self.policy["usable_time"]["usable_stopover"]
        self.assertTrue(self.policy["usable_time"]["penalize_unusable_connection_time"])
        self.assertTrue(self.policy["usable_time"]["long_connection_duration_alone_is_not_penalty"])
        self.assertTrue(usable["enabled"])
        self.assertTrue(usable["verified_excursion_hours_reduce_connection_penalty"])
        self.assertTrue(usable["qualifying_hours_count_as_usable_trip_time"])
        self.assertTrue(usable["do_not_convert_entire_scheduled_layover_to_usable_time"])
        self.assertEqual(usable["uncertainty_action"], "treat_unverified_portion_as_connection_time")
        self.assertEqual(
            set(usable["qualification_requires"]),
            {
                "entry_and_document_requirements_feasible",
                "minimum_connection_and_recheck_buffers_preserved",
                "local_access_practically_allows_excursion",
                "baggage_and_recheck_constraints_compatible",
            },
        )
        connection_penalty = self.policy["penalties"]["excessive_connection_time"]
        self.assertEqual(
            connection_penalty["applies_to"],
            "unusable_connection_time_after_verified_usable_stopover_hours",
        )
        self.assertEqual(self.policy["penalties"]["usable_stopover"]["long_duration_alone_penalty"], "none")

    def test_overnight_lodging_is_not_effective_transport_cost(self):
        cost = self.policy["cost"]
        self.assertNotIn(
            "unavoidable_transport_caused_overnight_cost",
            cost["effective_total_transport_price_includes"],
        )
        self.assertIn(
            "lodging_including_transport_caused_overnight",
            cost["exclude_by_default"],
        )
        self.assertTrue(self.policy["penalties"]["usable_stopover"]["lodging_cost_is_not_transport_cost"])

    def test_usable_stopover_cannot_hide_self_transfer_risk(self):
        plain = transport_efficiency(8.0, 20.0, usable_stopover_hours=12.0)
        self_transfer = transport_efficiency(
            8.0,
            20.0,
            usable_stopover_hours=12.0,
            self_transfer_count=1,
        )
        self.assertEqual(plain, 1.0)
        self.assertLess(self_transfer, plain)

    def test_invalid_usable_stopover_hours_are_rejected(self):
        with self.assertRaises(ValueError):
            transport_efficiency(8.0, 10.0, usable_stopover_hours=-1.0)
        with self.assertRaises(ValueError):
            transport_efficiency(8.0, 10.0, usable_stopover_hours=11.0)

    def test_self_transfer_adds_friction_penalty(self):
        plain = transport_efficiency(8.0, 10.0)
        self_transfer = transport_efficiency(8.0, 10.0, self_transfer_count=1)
        self.assertGreater(plain, self_transfer)

    def test_composite_uses_ssot_weights(self):
        components = {
            "effective_total_price": 1.0,
            "route_value": 0.0,
            "trip_length_fit": 0.0,
            "transport_efficiency": 0.0,
        }
        score = composite_score(components, self.policy["ranking"])
        self.assertAlmostEqual(score, 35.0)

    def test_absolute_cheapest_view_is_preserved(self):
        self.assertIn("absolute_cheapest", self.policy["ranking"]["preserve_views"])

    def test_china_gateways_are_enabled(self):
        self.assertTrue(self.policy["china"]["gateway_modes"]["kinmen"]["enabled"])
        self.assertTrue(self.policy["china"]["gateway_modes"]["matsu"]["enabled"])

    def test_full_china_radar_requires_all_entry_modes_only_in_china_profile(self):
        china = self.policy["china"]
        gate = china["coverage_gate"]
        self.assertEqual(china["activation_profile"], "china")
        self.assertTrue(gate["enabled"])
        self.assertEqual(gate["applies_only_when_profile"], "china")
        self.assertEqual(set(gate["required_modes"]), {"direct_air", "kinmen", "matsu"})
        self.assertTrue(gate["report_mode_coverage"])
        self.assertEqual(
            gate["incomplete_mode_coverage_action"],
            "mark_missing_and_do_not_claim_full_china_radar",
        )

    def test_ferry_operational_data_is_live_not_constant(self):
        data_policy = self.policy["china"]["ferry_data_policy"]
        self.assertTrue(data_policy["static_route_topology_allowed"])
        self.assertTrue(data_policy["timetable_must_be_live"])
        self.assertTrue(data_policy["fare_must_be_live"])
        self.assertTrue(data_policy["operating_status_must_be_live"])
        self.assertTrue(data_policy["do_not_store_operational_timetable_as_constant"])

    def test_ferry_evaluation_accounts_for_time_and_disruption(self):
        ferry = self.policy["china"]["ferry_evaluation"]
        self.assertTrue(ferry["count_total_door_to_door_transport_time"])
        self.assertTrue(ferry["evaluate_savings_per_extra_transport_hour"])
        self.assertTrue(ferry["evaluate_extra_transport_time_share_of_usable_trip"])
        self.assertEqual(ferry["disruption_risk_model"], "qualitative_until_history_exists")
        self.assertEqual(set(ferry["qualitative_levels"]), {"low", "medium", "high"})
        self.assertTrue(ferry["penalize_missed_connection_cascade_risk"])
        self.assertTrue(ferry["never_invent_cancellation_probability"])


if __name__ == "__main__":
    unittest.main()
