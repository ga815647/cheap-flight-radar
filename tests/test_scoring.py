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

    def test_full_china_radar_requires_all_entry_modes_attempted(self):
        gate = self.policy["china"]["coverage_gate"]
        self.assertTrue(gate["enabled"])
        self.assertEqual(set(gate["required_modes"]), {"direct_air", "kinmen", "matsu"})
        self.assertTrue(gate["report_mode_coverage"])
        self.assertEqual(
            gate["incomplete_mode_coverage_action"],
            "mark_missing_and_do_not_claim_full_china_radar",
        )


if __name__ == "__main__":
    unittest.main()
