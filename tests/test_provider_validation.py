import json
from pathlib import Path
import unittest

from cheap_flight_radar.provider_validation import (
    OPEN_JAW_LEGS,
    ROUND_TRIP_BASKET,
    aggregate_repeat_proxies,
    aggregate_snapshots,
    compare_repeat_query,
    exact_airport_date,
    itinerary_signature,
    semantic_key_paths,
    summarize_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "provider_validation"


def load_fixture(name):
    with (FIXTURES / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class ProviderValidationTests(unittest.TestCase):
    def test_fixed_basket_matches_issue_2(self):
        self.assertEqual(
            [case.case_id for case in ROUND_TRIP_BASKET],
            ["J1", "J2", "J3", "J4", "K1", "K2", "C1", "C2", "S1", "L1"],
        )
        self.assertEqual(
            [
                (case.case_id, case.origin, case.destination, case.outbound_date)
                for case in OPEN_JAW_LEGS
            ],
            [
                ("J5A", "TPE", "NRT", "2026-10-13"),
                ("J5B", "KIX", "TPE", "2026-10-18"),
            ],
        )

    def test_exact_gate_rejects_metro_airport_substitution(self):
        fixture = load_fixture("airport_integrity.json")
        case = next(case for case in ROUND_TRIP_BASKET if case.case_id == "C1")
        results = [exact_airport_date(item, case) for item in fixture["itineraries"]]
        self.assertEqual(results, [True, False, False])

        summary = summarize_snapshot(case, fixture["itineraries"])
        self.assertEqual(summary["returned_items"], 3)
        self.assertEqual(summary["exact_items"], 1)
        self.assertEqual(summary["airport_integrity_reject_items"], 2)
        self.assertAlmostEqual(summary["airport_integrity_reject_rate"], 2 / 3)

    def test_signature_uses_exact_airports_dates_and_flight_numbers(self):
        fixture = load_fixture("repeat_proxy.json")
        first = fixture["first"][0]
        changed = json.loads(json.dumps(first))
        changed["journeys"][0]["segments"][0]["marketing_flight_number"] = "MU9999"
        self.assertNotEqual(itinerary_signature(first), itinerary_signature(changed))

    def test_repeat_query_is_not_labeled_true_revalidation(self):
        fixture = load_fixture("repeat_proxy.json")
        case = next(case for case in ROUND_TRIP_BASKET if case.case_id == "C2")
        result = compare_repeat_query(case, fixture["first"], fixture["repeat"])
        self.assertTrue(result["same_selected_itinerary"])
        self.assertFalse(result["same_raw_price"])
        self.assertIsNone(result["true_revalidation_success"])
        self.assertIsNone(result["staleness_rate"])

    def test_disappearing_repeat_stays_proxy_only(self):
        fixture = load_fixture("repeat_disappeared.json")
        case = next(case for case in ROUND_TRIP_BASKET if case.case_id == "J4")
        result = compare_repeat_query(case, fixture["first"], fixture["repeat"])
        self.assertFalse(result["same_selected_itinerary"])
        self.assertFalse(result["same_raw_price"])
        self.assertIsNone(result["true_revalidation_success"])
        self.assertIsNone(result["staleness_rate"])

    def test_missing_semantics_remain_missing(self):
        fixture = load_fixture("semantic_fields.json")
        missing = semantic_key_paths(fixture["missing"])
        self.assertEqual(
            missing,
            {"currency": set(), "tax": set(), "baggage": set(), "fare": set()},
        )

        present = semantic_key_paths(fixture["present"])
        self.assertIn("price.currency", present["currency"])
        self.assertIn("price.taxIncluded", present["tax"])
        self.assertIn("fareFamily", present["fare"])
        self.assertIn("baggageAllowance", present["baggage"])

    def test_aggregate_keeps_case_and_item_coverage_separate(self):
        case_c1 = next(case for case in ROUND_TRIP_BASKET if case.case_id == "C1")
        case_c2 = next(case for case in ROUND_TRIP_BASKET if case.case_id == "C2")
        fixture = load_fixture("airport_integrity.json")
        snapshots = [
            summarize_snapshot(case_c1, fixture["itineraries"]),
            summarize_snapshot(case_c2, []),
        ]
        aggregate = aggregate_snapshots(snapshots)
        self.assertEqual(aggregate["cases_attempted"], 2)
        self.assertEqual(aggregate["cases_with_exact_result"], 1)
        self.assertEqual(aggregate["exact_case_coverage"], 0.5)
        self.assertEqual(aggregate["returned_items"], 3)
        self.assertEqual(aggregate["exact_items"], 1)

    def test_repeat_aggregate_preserves_unknown_revalidation(self):
        fixture = load_fixture("repeat_proxy.json")
        case = next(case for case in ROUND_TRIP_BASKET if case.case_id == "C2")
        proxy = compare_repeat_query(case, fixture["first"], fixture["repeat"])
        aggregate = aggregate_repeat_proxies([proxy])
        self.assertEqual(aggregate["same_selected_itinerary_rate"], 1.0)
        self.assertEqual(aggregate["same_itinerary_and_raw_price_rate"], 0.0)
        self.assertIsNone(aggregate["true_revalidation_success"])
        self.assertIsNone(aggregate["staleness_rate"])


if __name__ == "__main__":
    unittest.main()
