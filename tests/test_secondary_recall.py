from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult
from cheap_flight_radar.production_runtime import run_once
from cheap_flight_radar.secondary_recall import SecondaryRecallAdapter

ROOT = Path(__file__).resolve().parents[1]
RUN_AT = datetime.fromisoformat("2026-08-13T02:00:00+08:00")


def record(*, record_id: str, provider: str, surface: str, origin: str, destination: str, country: str, price: int, return_date: str | None, typical: int | None = None, discount: float | None = None) -> AirfareRecord:
    legs = [AirfareLeg(origin, destination, "2026-09-10")]
    if return_date:
        legs.append(AirfareLeg(destination, origin, return_date))
    qualified = bool(return_date and typical and discount)
    return AirfareRecord(
        record_id=record_id,
        provider=provider,
        surface=surface,
        origin=AirportIdentity(origin),
        destination=AirportIdentity(destination, city=destination, country=country),
        legs=tuple(legs),
        current_price_twd=price,
        typical_price_twd=typical,
        discount_percent=discount,
        anomaly_authority="google_flight_deals" if qualified else None,
        observed_at=RUN_AT.isoformat(),
        verification_state="discovery" if qualified else "seed_only",
        evidence_class="qualified_round_trip_deal" if qualified else "weak_seed",
        complete_airfare=bool(return_date),
        reproducible_search={"origin": origin, "surface": surface},
    )


class FakeAdapter:
    def __init__(self) -> None:
        self.deal = record(record_id="fd-nrt", provider="gflights", surface="flight_deals", origin="TPE", destination="NRT", country="Japan", price=6500, return_date="2026-09-14", typical=10000, discount=35)
        self.cheapest_calls: list[tuple[str, str]] = []
        self.exact_calls: list[tuple[str, str]] = []

    async def flight_deals(self, *, origin, anchor_departure, anchor_return):
        rows = (self.deal,) if origin == "TPE" else ()
        return ProviderResult("gflights", "flight_deals", "complete", rows)

    async def explore(self, *, origin, **kwargs):
        return ProviderResult("gflights", "explore", "complete", ())

    async def cheapest_dates(self, *, origin, destination, start_date, months=3, trip_duration_days=None):
        self.cheapest_calls.append((origin, destination))
        country = "South Korea" if destination == "ICN" else "Japan"
        seed = record(record_id=f"flex-{origin}-{destination}", provider="gflights", surface="cheapest_dates", origin=origin, destination=destination, country=country, price=5200, return_date="2026-09-14")
        return ProviderResult("gflights", "cheapest_dates", "complete", (seed,))

    async def exact(self, *, origin, destination, departure_date, return_date=None, **kwargs):
        self.exact_calls.append((origin, destination))
        exact = AirfareRecord(
            record_id=f"exact-{origin}-{destination}", provider="gflights", surface="exact",
            origin=AirportIdentity(origin), destination=AirportIdentity(destination),
            legs=(AirfareLeg(origin, destination, departure_date, "06:00", "09:00"),),
            current_price_twd=5200 if destination == "ICN" else 6900,
            observed_at=RUN_AT.isoformat(), verification_state="revalidated",
            evidence_class="exact_revalidated_candidate", complete_airfare=True, booking_token="token",
            reproducible_search={"origin": origin, "destination": destination, "date": departure_date, "return_date": return_date},
        )
        return ProviderResult("gflights", "exact", "complete", (exact,))

    async def open_jaw(self, *, legs):
        return ProviderResult("gflights", "open_jaw", "empty")


class SecondaryRecallRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    async def test_canonical_run_once_expands_opportunistic_one_way_web_seed(self):
        base = FakeAdapter()
        web_seed = record(
            record_id="web-oneway-icn", provider="chatgpt_web", surface="public_web_one_way",
            origin="TPE", destination="ICN", country="South Korea", price=3200, return_date=None,
        )
        adapter = SecondaryRecallAdapter(base, (web_seed,))
        result = await run_once(policy=self.policy, adapter=adapter, run_at=RUN_AT)

        self.assertIn(("TPE", "ICN"), base.cheapest_calls)
        self.assertIn(("TPE", "ICN"), base.exact_calls)
        retained = [item for item in result.signals if item.discovery.record_id == "web-oneway-icn"]
        self.assertTrue(retained)
        self.assertEqual(retained[0].discovery.provider, "chatgpt_web")
        self.assertEqual(retained[0].discovery.surface, "public_web_one_way")
        self.assertIsNone(retained[0].discovery.anomaly_authority)


if __name__ == "__main__":
    unittest.main()
