from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.scoring import composite_score, transport_efficiency, trip_length_fit


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
