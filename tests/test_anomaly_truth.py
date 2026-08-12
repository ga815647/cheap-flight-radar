import unittest

from cheap_flight_radar.anomaly_truth import (
    AnomalyEvidence,
    formal_deal_sort_key,
    select_anomaly_truth,
)


PRIORITY = [
    "google_flight_deals",
    "google_flights_exact_price_insight",
    "own_price_history",
]


class AnomalyTruthTests(unittest.TestCase):
    def test_external_google_deal_beats_conflicting_own_history_by_priority(self):
        selected = select_anomaly_truth(
            [
                AnomalyEvidence(
                    source="own_price_history",
                    current_price_twd=6000,
                    typical_price_twd=10000,
                    reproducible=True,
                    qualified=True,
                    evidence_kind="history_fallback",
                ),
                AnomalyEvidence(
                    source="google_flight_deals",
                    current_price_twd=6000,
                    typical_price_twd=8000,
                    discount_percent=25,
                    reproducible=True,
                    qualified=True,
                ),
            ],
            PRIORITY,
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.source, "google_flight_deals")
        self.assertEqual(selected.normalized_discount_percent(), 25)

    def test_conflicting_sources_are_not_averaged(self):
        selected = select_anomaly_truth(
            [
                AnomalyEvidence("google_flight_deals", 5000, 10000, 50, True, True),
                AnomalyEvidence("own_price_history", 5000, 6250, 20, True, True),
            ],
            PRIORITY,
        )
        self.assertEqual(selected.normalized_discount_percent(), 50)

    def test_own_history_is_fallback_when_external_truth_is_unqualified(self):
        selected = select_anomaly_truth(
            [
                AnomalyEvidence("google_flight_deals", 5000, 9000, 44, False, True),
                AnomalyEvidence("own_price_history", 5000, 6250, None, True, True),
            ],
            PRIORITY,
        )
        self.assertEqual(selected.source, "own_price_history")
        self.assertAlmostEqual(selected.normalized_discount_percent(), 20.0)

    def test_cheap_seed_without_anomaly_context_is_not_formal_truth(self):
        selected = select_anomaly_truth(
            [AnomalyEvidence("expedia_seed", 2999, reproducible=True, qualified=True)],
            PRIORITY,
        )
        self.assertIsNone(selected)

    def test_formal_ranking_is_anomaly_first_then_complete_airfare(self):
        stronger_but_pricier = AnomalyEvidence(
            "google_flight_deals", 9000, 18000, 50, True, True
        )
        weaker_but_cheaper = AnomalyEvidence(
            "google_flight_deals", 3000, 5000, 40, True, True
        )
        equal_anomaly_cheaper = AnomalyEvidence(
            "google_flight_deals", 2500, 5000, 50, True, True
        )
        ranked = sorted(
            [weaker_but_cheaper, stronger_but_pricier, equal_anomaly_cheaper],
            key=formal_deal_sort_key,
        )
        self.assertEqual(ranked, [equal_anomaly_cheaper, stronger_but_pricier, weaker_but_cheaper])


if __name__ == "__main__":
    unittest.main()
