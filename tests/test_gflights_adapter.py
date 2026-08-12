from __future__ import annotations

import json
from pathlib import Path
import unittest

from cheap_flight_radar.providers.gflights import GFlightsAdapter, PRODUCTION_USER_AGENT


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "gflights"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def _async_value(value):
    return value


class FakeClient:
    def __init__(self):
        self.fail_deals = False

    async def deals(self, **kwargs):
        if self.fail_deals:
            raise RuntimeError("provider down")
        return fixture("deals.json")

    async def explore(self, **kwargs):
        return fixture("explore.json")

    async def search(self, **kwargs):
        return fixture("exact.json")

    async def offer(self, **kwargs):
        return [{"airline_names": ["Tigerair Taiwan"], "price": 6900, "booking_url": "https://example.invalid/book"}]

    async def cheapest_dates(self, **kwargs):
        return [{"departure_date": "2026-09-10", "return_date": "2026-09-14", "price": 6400}]

    async def multi_city_search(self, legs):
        return fixture("open_jaw.json")


class GFlightsAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_client_is_fixed_twd_direct_no_proxy(self):
        captured = {}

        def factory(**kwargs):
            captured.update(kwargs)
            return FakeClient()

        GFlightsAdapter(client_factory=factory)
        self.assertEqual(captured["user_agent"], PRODUCTION_USER_AGENT)
        self.assertEqual(captured["proxy"], None)
        self.assertEqual(captured["currency"], "TWD")
        self.assertEqual(captured["country"], "TW")
        self.assertNotIn("Mozilla", captured["user_agent"])

    async def test_flight_deal_normalizes_anomaly_airport_and_twd(self):
        adapter = GFlightsAdapter(client=FakeClient(), observed_at=lambda: "2026-08-13T02:00:00+08:00")
        result = await adapter.flight_deals(origin="TPE", anchor_departure="2026-08-27", anchor_return="2026-09-03")
        self.assertEqual(result.coverage_state, "complete")
        japan = result.records[0]
        self.assertEqual(japan.origin.iata, "TPE")
        self.assertEqual(japan.destination.iata, "NRT")
        self.assertEqual(japan.destination.city, "Tokyo")
        self.assertEqual(japan.destination.country, "Japan")
        self.assertEqual(japan.current_price_twd, 6500)
        self.assertEqual(japan.typical_price_twd, 10000)
        self.assertEqual(japan.discount_percent, 35.0)
        self.assertEqual(japan.anomaly_authority, "google_flight_deals")
        self.assertEqual(japan.evidence_class, "qualified_round_trip_deal")
        self.assertTrue(japan.complete_airfare)
        self.assertEqual(japan.reproducible_search["currency"], "TWD")

    async def test_exact_revalidation_keeps_provider_leg_identity_and_offer_url(self):
        adapter = GFlightsAdapter(client=FakeClient(), observed_at=lambda: "2026-08-13T02:00:00+08:00")
        result = await adapter.exact(origin="TPE", destination="NRT", departure_date="2026-09-10", return_date="2026-09-14")
        self.assertEqual(result.coverage_state, "complete")
        record = result.records[0]
        self.assertEqual(record.current_price_twd, 6900)
        self.assertEqual(record.booking_token, "booking-token-123")
        self.assertEqual(record.booking_url, "https://example.invalid/book")
        self.assertEqual(record.verification_state, "revalidated")
        self.assertEqual(record.legs[0].origin, "TPE")
        self.assertEqual(record.legs[0].destination, "NRT")
        self.assertEqual(record.legs[0].departure_time, "06:35")
        self.assertEqual(record.reproducible_search["return_date"], "2026-09-14")
        self.assertEqual(record.return_date, "2026-09-14")
        self.assertTrue(record.is_round_trip)
        self.assertTrue(record.has_provider_leg_identity)
        self.assertFalse(record.provider_segments_cover_complete_trip)
        self.assertEqual(record.reproducible_search["search_price_twd"], 6800)

    async def test_explore_is_weak_seed_not_deal_truth(self):
        record = (await GFlightsAdapter(client=FakeClient()).explore(origin="TPE")).records[0]
        self.assertEqual(record.destination.iata, "ICN")
        self.assertEqual(record.current_price_twd, 5200)
        self.assertEqual(record.evidence_class, "weak_seed")
        self.assertIsNone(record.anomaly_authority)

    async def test_cheapest_dates_is_twd_flexible_seed(self):
        result = await GFlightsAdapter(client=FakeClient()).cheapest_dates(
            origin="TPE", destination="NRT", start_date="2026-08-20", months=3, trip_duration_days=4
        )
        self.assertEqual(result.records[0].current_price_twd, 6400)
        self.assertEqual(result.records[0].outbound_date, "2026-09-10")
        self.assertEqual(result.records[0].return_date, "2026-09-14")

    async def test_open_jaw_exact_preserves_multiple_airport_identities(self):
        result = await GFlightsAdapter(client=FakeClient()).open_jaw(
            legs=[("TPE", "NRT", "2026-09-10"), ("KIX", "KHH", "2026-09-15")]
        )
        record = result.records[0]
        self.assertEqual(record.current_price_twd, 9500)
        self.assertEqual([(leg.origin, leg.destination) for leg in record.legs], [("TPE", "NRT"), ("KIX", "KHH")])
        self.assertEqual(record.booking_token, "open-jaw-token")
        self.assertTrue(record.complete_airfare)

    async def test_empty_and_provider_failure_fail_closed(self):
        empty_client = FakeClient()
        empty_client.search = lambda **kwargs: _async_value([])
        exact = await GFlightsAdapter(client=empty_client).exact(
            origin="TPE", destination="NRT", departure_date="2026-09-10", return_date="2026-09-14"
        )
        self.assertEqual(exact.coverage_state, "empty")
        self.assertEqual(exact.records, ())
        failed = FakeClient()
        failed.fail_deals = True
        deals = await GFlightsAdapter(client=failed).flight_deals(
            origin="TPE", anchor_departure="2026-08-27", anchor_return="2026-09-03"
        )
        self.assertEqual(deals.coverage_state, "failed")
        self.assertIn("provider down", deals.error)
        self.assertEqual(deals.records, ())

    async def test_invalid_airport_identity_is_rejected_before_provider_call(self):
        with self.assertRaises(ValueError):
            await GFlightsAdapter(client=FakeClient()).exact(origin="Taipei", destination="NRT", departure_date="2026-09-10")


if __name__ == "__main__":
    unittest.main()
