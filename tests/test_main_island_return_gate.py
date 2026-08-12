import unittest

from cheap_flight_radar.models import LiveReturnAirport


class MainIslandReturnGateTests(unittest.TestCase):
    def test_live_main_island_extra_airport_is_allowed(self):
        airport = LiveReturnAirport("TNN", True, source_id="live-route")
        self.assertTrue(airport.live_route_evidence)

    def test_live_offshore_extra_airport_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Taiwan main island"):
            LiveReturnAirport("MZG", True, source_id="live-route")

    def test_non_live_airport_can_exist_as_unselected_evidence(self):
        airport = LiveReturnAirport("MZG", False, source_id="not-live")
        self.assertFalse(airport.live_route_evidence)


if __name__ == "__main__":
    unittest.main()
