from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult
from cheap_flight_radar.production_runtime import ProductionExecutionAdapter, run_once, write_run_artifacts

ROOT = Path(__file__).resolve().parents[1]
RUN_AT = datetime.fromisoformat("2026-08-13T02:00:00+08:00")


def discovery(record_id: str, destination: str, price: int, typical: int, discount: float) -> AirfareRecord:
    return AirfareRecord(
        record_id=record_id,
        provider="gflights",
        surface="flight_deals",
        origin=AirportIdentity("TPE"),
        destination=AirportIdentity(destination, city=destination, country="Japan"),
        legs=(
            AirfareLeg("TPE", destination, "2026-09-10"),
            AirfareLeg(destination, "TPE", "2026-09-14"),
        ),
        current_price_twd=price,
        typical_price_twd=typical,
        discount_percent=discount,
        anomaly_authority="google_flight_deals",
        observed_at=RUN_AT.isoformat(),
        verification_state="discovery",
        evidence_class="qualified_round_trip_deal",
        complete_airfare=True,
        reproducible_search={"origin": "TPE", "currency": "TWD"},
    )


class FakeAdapter:
    def __init__(self) -> None:
        self.rows = [
            discovery("deal-a", "NRT", 6000, 10000, 40),
            discovery("deal-b", "KIX", 6500, 10000, 35),
        ]
        self.open_jaw_calls = []
        self.exact_calls = []

    def _row(self, destination):
        return next(row for row in self.rows if row.destination.iata == destination)

    async def flight_deals(self, *, origin, anchor_departure, anchor_return):
        rows = self.rows if origin == "TPE" else []
        return ProviderResult("gflights", "flight_deals", "complete", tuple(rows))

    async def explore(self, *, origin, **kwargs):
        return ProviderResult("gflights", "explore", "complete", ())

    async def exact(self, *, origin, destination, departure_date, return_date=None, **kwargs):
        self.exact_calls.append((origin, destination, departure_date, return_date))
        source = self._row(destination)
        exact = AirfareRecord(
            record_id=f"exact-{destination}-{departure_date}-{return_date}",
            provider="gflights",
            surface="exact",
            origin=AirportIdentity(origin),
            destination=AirportIdentity(destination),
            legs=(AirfareLeg(origin, destination, departure_date, "06:00", "09:00"),),
            current_price_twd=source.current_price_twd,
            observed_at=RUN_AT.isoformat(),
            verification_state="revalidated",
            evidence_class="exact_revalidated_candidate",
            complete_airfare=True,
            booking_token="token",
            reproducible_search={
                "origin": origin,
                "destination": destination,
                "date": departure_date,
                "return_date": return_date,
                "currency": "TWD",
            },
        )
        return ProviderResult("gflights", "exact", "complete", (exact,))

    async def cheapest_dates(self, *, origin, destination, start_date, months=3, trip_duration_days=None):
        source = self._row(destination)
        record = AirfareRecord(
            record_id=f"flex-{destination}", provider="gflights", surface="cheapest_dates",
            origin=AirportIdentity(origin), destination=source.destination,
            legs=(AirfareLeg(origin, destination, "2026-09-10"), AirfareLeg(destination, origin, "2026-09-14")),
            current_price_twd=source.current_price_twd, observed_at=RUN_AT.isoformat(), verification_state="seed_only",
            evidence_class="weak_seed", complete_airfare=True,
        )
        return ProviderResult("gflights", "cheapest_dates", "complete", (record,))

    async def open_jaw(self, *, legs):
        self.open_jaw_calls.append(tuple(legs))
        first_origin, first_destination, _ = legs[0]
        record = AirfareRecord(
            record_id=f"oj-{first_destination}-{legs[-1][0]}-{legs[-1][1]}", provider="gflights", surface="open_jaw",
            origin=AirportIdentity(first_origin), destination=AirportIdentity(first_destination),
            legs=tuple(AirfareLeg(origin, destination, day) for origin, destination, day in legs),
            current_price_twd=7000, observed_at=RUN_AT.isoformat(), verification_state="revalidated",
            evidence_class="exact_revalidated_candidate", complete_airfare=True, booking_token="token",
        )
        return ProviderResult("gflights", "open_jaw", "complete", (record,))


class ProductionExecutionAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_city_uses_reserved_adapter_not_primary_client(self):
        multi_city = FakeAdapter()
        adapter = ProductionExecutionAdapter(primary=object(), multi_city=multi_city)
        legs = [("TPE", "NRT", "2026-09-10"), ("KIX", "TPE", "2026-09-14")]
        result = await adapter.open_jaw(legs=legs)
        self.assertEqual(result.coverage_state, "complete")
        self.assertEqual(multi_city.open_jaw_calls, [tuple(legs)])

    async def test_non_multi_city_surfaces_keep_primary_adapter(self):
        primary = FakeAdapter()
        adapter = ProductionExecutionAdapter(primary=primary, multi_city=object())
        result = await adapter.exact(
            origin="TPE",
            destination="NRT",
            departure_date="2026-09-10",
            return_date="2026-09-14",
        )
        self.assertEqual(result.coverage_state, "complete")
        self.assertEqual(
            primary.exact_calls,
            [("TPE", "NRT", "2026-09-10", "2026-09-14")],
        )


class ProductionRuntimeRetentionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    async def test_unselected_qualified_anomaly_is_retained_as_pending_signal(self):
        policy = deepcopy(self.policy)
        policy["search"]["deep_search_candidate_limit"] = 1
        policy["search"]["final_shortlist_limit"] = 1
        result = await run_once(policy=policy, adapter=FakeAdapter(), run_at=RUN_AT)
        self.assertEqual(len(result.deals), 1)
        pending = [
            item for item in result.signals
            if item.state == "qualified_anomaly_candidate_pending_exact"
        ]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].discovery.destination.iata, "KIX")
        self.assertEqual(pending[0].anomaly_source, "google_flight_deals")
        self.assertEqual(pending[0].anomaly_strength_percent, 35)
        self.assertIsNone(pending[0].exact)

    async def test_manifest_and_run_result_keep_pending_signal_evidence(self):
        policy = deepcopy(self.policy)
        policy["search"]["deep_search_candidate_limit"] = 1
        policy["search"]["final_shortlist_limit"] = 1
        result = await run_once(policy=policy, adapter=FakeAdapter(), run_at=RUN_AT)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_run_artifacts(result, policy=policy, output_dir=Path(tmp))
            run_result = json.loads(Path(paths["run_result"]).read_text(encoding="utf-8"))
            manifest = json.loads(Path(paths["publication_manifest"]).read_text(encoding="utf-8"))
            self.assertIn("signals", run_result)
            self.assertEqual(run_result["signal_states"]["qualified_anomaly_candidate_pending_exact"], 1)
            self.assertTrue(any(
                item["state"] == "qualified_anomaly_candidate_pending_exact"
                for item in run_result["signals"]
            ))
            self.assertTrue(any(
                item["state"] == "qualified_anomaly_candidate_pending_exact"
                for item in manifest["signals"]
            ))
            self.assertGreater(manifest["coverage"]["execution"]["flexible_dates"]["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
