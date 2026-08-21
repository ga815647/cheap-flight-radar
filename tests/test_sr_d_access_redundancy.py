from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib
import unittest

import yaml

from cheap_flight_radar.airfare import ProviderResult
from cheap_flight_radar.models import OriginSweepRequest, SearchRequest
from cheap_flight_radar.production_runtime import ProductionExecutionAdapter
from cheap_flight_radar.providers.kiwi_mcp import KiwiMCPAdapter
from cheap_flight_radar.source_router import build_source_plan


ROOT = Path(__file__).resolve().parents[1]


def kiwi_payload(price: int = 9168):
    return {
        "currency": "TWD",
        "resultsCount": 1,
        "itineraries": [
            {
                "id": "fixture-itinerary",
                "price": price,
                "bookingUrl": "https://kiwi.com/u/fixture",
                "outbound": {
                    "segments": [
                        {
                            "from": "TPE",
                            "to": "NRT",
                            "fromCity": "Taipei",
                            "toCity": "Tokyo",
                            "fromCountry": "Taiwan",
                            "toCountry": "Japan",
                            "departureTime": "2026-10-05T06:35:00",
                            "arrivalTime": "2026-10-05T11:00:00",
                            "carrier": "IT",
                            "carrierName": "Tigerair Taiwan",
                            "flightNumber": "IT200",
                        }
                    ]
                },
                "inbound": {
                    "segments": [
                        {
                            "from": "NRT",
                            "to": "TPE",
                            "fromCity": "Tokyo",
                            "toCity": "Taipei",
                            "fromCountry": "Japan",
                            "toCountry": "Taiwan",
                            "departureTime": "2026-10-09T19:30:00",
                            "arrivalTime": "2026-10-09T22:35:00",
                            "carrier": "IT",
                            "carrierName": "Tigerair Taiwan",
                            "flightNumber": "IT203",
                        }
                    ]
                },
            }
        ],
    }


class FakePrimary:
    def __init__(self, result: ProviderResult):
        self.result = result
        self.calls = 0

    async def exact(self, **kwargs):
        self.calls += 1
        return self.result

    async def cheapest_dates(self, **kwargs):
        self.calls += 1
        return self.result


class FakeFallback:
    provider = "kiwi_mcp"

    def __init__(self, result: ProviderResult):
        self.result = result
        self.calls = 0

    async def exact(self, **kwargs):
        self.calls += 1
        return self.result

    async def cheapest_dates(self, **kwargs):
        self.calls += 1
        return self.result


class SRDAccessRedundancyTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    def test_policy_routes_only_known_route_exact_flexible_to_kiwi_fallback(self):
        origin_plan = build_source_plan(
            OriginSweepRequest(origin="TPE", horizon_start="2026-08-21"),
            self.policy,
            {},
        )
        exact_plan = build_source_plan(
            SearchRequest(
                profile="world",
                search_stage="round_trip_benchmark",
                origin="TPE",
                destination="NRT",
                outbound_date="2026-10-05",
                return_date="2026-10-09",
                destination_country="JP",
            ),
            self.policy,
            {},
        )
        open_jaw_plan = build_source_plan(
            SearchRequest(
                profile="world",
                search_stage="round_trip_benchmark",
                origin="TPE",
                destination="NRT",
                outbound_date="2026-10-05",
                return_date="2026-10-09",
                destination_country="JP",
                open_jaw_required=True,
            ),
            self.policy,
            {},
        )
        self.assertEqual([entry.provider for entry in origin_plan.entries], ["gflights_google_flight_deals"])
        self.assertEqual(
            [entry.provider for entry in exact_plan.entries],
            ["gflights_google_exact", "kiwi_mcp_exact"],
        )
        self.assertEqual([entry.provider for entry in open_jaw_plan.entries], ["gflights_google_exact"])

    def test_dependency_and_ssot_mark_kiwi_as_qualified_credential_free_fallback(self):
        dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
        self.assertTrue(any(str(value).startswith("mcp>=1.29") for value in dependencies))
        routing = self.policy["source_routing"]
        self.assertEqual(routing["status"], "provider_execution_truth_converged_v4")
        provider = routing["providers"]["kiwi_mcp_exact"]
        self.assertEqual(provider["execution_plane"], "canonical_backend")
        self.assertEqual(provider["current_integration_state"], "integrated")
        self.assertTrue(provider["automatic_execution_supported"])
        self.assertFalse(provider["credential_required"])
        self.assertFalse(provider["anomaly_authority"])
        self.assertEqual(provider["endpoint"], "https://mcp.kiwi.com")

    async def test_kiwi_adapter_normalizes_exact_complete_twd_itinerary(self):
        calls = []

        async def caller(arguments):
            calls.append(dict(arguments))
            return kiwi_payload()

        result = await KiwiMCPAdapter(caller=caller).exact(
            origin="TPE",
            destination="NRT",
            departure_date="2026-10-05",
            return_date="2026-10-09",
        )
        self.assertEqual(result.coverage_state, "complete")
        self.assertEqual(result.provider, "kiwi_mcp")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["currency"], "TWD")
        self.assertEqual(calls[0]["departureDate"], "05/10/2026")
        exact = result.records[0]
        self.assertEqual(exact.current_price_twd, 9168)
        self.assertEqual(exact.origin.iata, "TPE")
        self.assertEqual(exact.destination.iata, "NRT")
        self.assertEqual(exact.return_date, "2026-10-09")
        self.assertTrue(exact.provider_segments_cover_complete_trip)
        self.assertEqual(exact.verification_state, "revalidated")
        self.assertEqual(exact.booking_url, "https://kiwi.com/u/fixture")

    async def test_kiwi_flexible_uses_one_native_range_call(self):
        calls = []

        async def caller(arguments):
            calls.append(dict(arguments))
            return kiwi_payload(8800)

        result = await KiwiMCPAdapter(caller=caller).cheapest_dates(
            origin="TPE",
            destination="NRT",
            start_date="2026-10-01",
            months=1,
            trip_duration_days=4,
        )
        self.assertEqual(result.coverage_state, "complete")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["departureDate"], "01/10/2026")
        self.assertEqual(calls[0]["departureDateTo"], "30/10/2026")
        self.assertEqual(calls[0]["nights_in_dst_from"], 4)
        self.assertEqual(calls[0]["nights_in_dst_to"], 4)
        self.assertEqual(result.records[0].current_price_twd, 8800)

    async def test_primary_failure_invokes_exact_fallback_once_and_records_truth(self):
        primary = FakePrimary(ProviderResult("gflights", "exact", "failed", error="primary down"))
        fallback = FakeFallback(ProviderResult("kiwi_mcp", "exact", "complete", ()))
        adapter = ProductionExecutionAdapter(primary=primary, multi_city=primary, known_route_fallback=fallback)
        result = await adapter.exact(origin="TPE", destination="NRT", departure_date="2026-10-05", return_date="2026-10-09")
        self.assertEqual(result.provider, "kiwi_mcp")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 1)
        self.assertEqual(len(adapter.fallback_events), 1)
        self.assertEqual(adapter.fallback_events[0]["primary_state"], "failed")
        self.assertEqual(adapter.fallback_events[0]["fallback_state"], "complete")

    async def test_complete_empty_primary_does_not_silently_fallback(self):
        primary = FakePrimary(ProviderResult("gflights", "exact", "complete", ()))
        fallback = FakeFallback(ProviderResult("kiwi_mcp", "exact", "complete", ()))
        adapter = ProductionExecutionAdapter(primary=primary, multi_city=primary, known_route_fallback=fallback)
        result = await adapter.exact(origin="TPE", destination="NRT", departure_date="2026-10-05", return_date="2026-10-09")
        self.assertEqual(result.provider, "gflights")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 0)
        self.assertEqual(adapter.fallback_events, [])

    def test_qualification_doc_records_both_workers_and_scoped_architecture(self):
        text = (ROOT / "docs" / "executable-redundancy-qualification-2026-08-21.md").read_text(encoding="utf-8")
        self.assertIn("Experiment PR #68", text)
        self.assertIn("Experiment PR: #69", text)
        self.assertIn("32492608693", text)
        self.assertIn("96803536401", text)
        self.assertIn("15 exact itineraries", text)
        self.assertIn("does **not** create destination-free Flight Deals/anomaly redundancy", text)


if __name__ == "__main__":
    unittest.main()
