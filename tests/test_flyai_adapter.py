import json
from pathlib import Path
import unittest

from cheap_flight_radar.models import SearchRequest
from cheap_flight_radar.providers.flyai import FlyAIAdapter


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "flyai"


class FlyAIAdapterTests(unittest.TestCase):
    def request(self, **overrides):
        values = {
            "profile": "china",
            "search_stage": "deep_search",
            "origin": "TSA",
            "destination": "SHA",
            "outbound_date": "2026-10-13",
            "return_date": "2026-10-17",
            "destination_country": "CN",
        }
        values.update(overrides)
        return SearchRequest(**values)

    def fixture_text(self):
        return (FIXTURES / "exact_with_substitution.json").read_text(encoding="utf-8")

    def test_strict_airport_gate_rejects_substitution(self):
        calls = []

        def runner(args, timeout):
            calls.append((list(args), timeout))
            return 0, self.fixture_text(), ""

        result = FlyAIAdapter(runner=runner).collect(
            self.request(), "2026-08-10T23:00:00+08:00"
        )
        self.assertEqual(result.health, "ok")
        self.assertEqual(result.coverage_state, "exact_results")
        self.assertEqual(result.returned_items, 2)
        self.assertEqual(result.rejected_items, 1)
        self.assertEqual(len(result.offers), 1)
        offer = result.offers[0]
        self.assertTrue(offer.exact_airport_date)
        self.assertEqual(offer.journeys[0].segments[0].origin, "TSA")
        self.assertEqual(offer.journeys[0].segments[-1].destination, "SHA")
        self.assertEqual(offer.journeys[1].segments[0].origin, "SHA")
        self.assertEqual(offer.journeys[1].segments[-1].destination, "TSA")
        self.assertIn("--origin", calls[0][0])
        self.assertIn("--back-date", calls[0][0])

    def test_unknown_fare_semantics_are_not_invented(self):
        result = FlyAIAdapter(
            runner=lambda args, timeout: (0, self.fixture_text(), "")
        ).collect(self.request(), "2026-08-10T23:00:00+08:00")
        offer = result.offers[0]
        self.assertEqual(offer.raw_price, "2713.00")
        self.assertIsNone(offer.original_currency)
        self.assertEqual(offer.tax_semantics, "unknown")
        self.assertEqual(offer.baggage_state, "unknown")
        self.assertIsNone(offer.fare_family)
        self.assertEqual(offer.verification_state, "discovery")
        self.assertEqual(offer.freshness, "provider_live_search")
        self.assertEqual(offer.source_url, "https://example.invalid/flyai/exact")

    def test_open_jaw_is_not_split_into_fake_combined_fare(self):
        result = FlyAIAdapter(
            runner=lambda args, timeout: self.fail("runner must not be called")
        ).collect(
            self.request(open_jaw_required=True),
            "2026-08-10T23:00:00+08:00",
        )
        self.assertEqual(result.coverage_state, "unsupported_query")
        self.assertEqual(result.offers, ())

    def test_missing_return_date_is_unsupported(self):
        result = FlyAIAdapter(
            runner=lambda args, timeout: self.fail("runner must not be called")
        ).collect(
            self.request(return_date=None),
            "2026-08-10T23:00:00+08:00",
        )
        self.assertEqual(result.coverage_state, "unsupported_query")

    def test_nonzero_cli_exit_is_provider_failure(self):
        result = FlyAIAdapter(
            runner=lambda args, timeout: (2, "", "credential rejected")
        ).collect(self.request(), "2026-08-10T23:00:00+08:00")
        self.assertEqual(result.health, "failed")
        self.assertEqual(result.coverage_state, "failed")
        self.assertIn("command_exit=2", result.error)

    def test_malformed_json_is_provider_failure(self):
        result = FlyAIAdapter(
            runner=lambda args, timeout: (0, "not-json", "")
        ).collect(self.request(), "2026-08-10T23:00:00+08:00")
        self.assertEqual(result.health, "failed")
        self.assertEqual(result.error, "invalid_json")

    def test_provider_error_status_is_failure(self):
        payload = json.dumps({"status": 7, "message": "upstream unavailable"})
        result = FlyAIAdapter(
            runner=lambda args, timeout: (0, payload, "")
        ).collect(self.request(), "2026-08-10T23:00:00+08:00")
        self.assertEqual(result.health, "failed")
        self.assertIn("provider_status=7", result.error)

    def test_no_exact_result_keeps_reject_count_visible(self):
        payload = json.loads(self.fixture_text())
        payload["data"]["itemList"] = [payload["data"]["itemList"][1]]
        result = FlyAIAdapter(
            runner=lambda args, timeout: (0, json.dumps(payload), "")
        ).collect(self.request(), "2026-08-10T23:00:00+08:00")
        self.assertEqual(result.coverage_state, "no_exact_result")
        self.assertEqual(result.returned_items, 1)
        self.assertEqual(result.rejected_items, 1)
        self.assertEqual(result.offers, ())


if __name__ == "__main__":
    unittest.main()
