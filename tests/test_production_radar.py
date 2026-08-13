from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult
from cheap_flight_radar.price_history import FareObservation
from cheap_flight_radar.production_radar import ProductionRadar, build_run_artifacts, write_run_artifacts

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "flight-radar.yaml"
RUN_AT = datetime.fromisoformat("2026-08-13T02:00:00+08:00")


def deal(origin: str, destination: str, country: str, price: int, typical: int, discount: float) -> AirfareRecord:
    return AirfareRecord(
        record_id=f"deal-{origin}-{destination}", provider="gflights", surface="flight_deals",
        origin=AirportIdentity(origin), destination=AirportIdentity(destination, city=destination, country=country),
        legs=(AirfareLeg(origin, destination, "2026-09-10"), AirfareLeg(destination, origin, "2026-09-14")),
        current_price_twd=price, typical_price_twd=typical, discount_percent=discount,
        anomaly_authority="google_flight_deals", observed_at=RUN_AT.isoformat(), verification_state="discovery",
        evidence_class="qualified_round_trip_deal", complete_airfare=True,
        reproducible_search={"origin": origin, "currency": "TWD"},
    )


def weak_explore(origin: str, destination: str, country: str, price: int = 5200) -> AirfareRecord:
    return AirfareRecord(
        record_id=f"explore-{origin}-{destination}", provider="gflights", surface="explore",
        origin=AirportIdentity(origin), destination=AirportIdentity(destination, city=destination, country=country),
        legs=(AirfareLeg(origin, destination, "2026-09-20"), AirfareLeg(destination, origin, "2026-09-24")),
        current_price_twd=price, observed_at=RUN_AT.isoformat(), verification_state="seed_only",
        evidence_class="weak_seed", complete_airfare=True, reproducible_search={"origin": origin, "currency": "TWD"},
    )


def exact(discovery: AirfareRecord, price: int) -> AirfareRecord:
    return AirfareRecord(
        record_id=f"exact-{discovery.origin.iata}-{discovery.destination.iata}", provider="gflights", surface="exact",
        origin=AirportIdentity(discovery.origin.iata), destination=AirportIdentity(discovery.destination.iata),
        legs=(AirfareLeg(discovery.origin.iata, discovery.destination.iata, discovery.outbound_date or "2026-09-10", departure_time="06:00", arrival_time="09:00"),),
        current_price_twd=price, observed_at=RUN_AT.isoformat(), verification_state="revalidated",
        evidence_class="exact_revalidated_candidate", complete_airfare=True, booking_token="token",
        reproducible_search={"origin": discovery.origin.iata, "destination": discovery.destination.iata, "date": discovery.outbound_date, "return_date": discovery.return_date, "currency": "TWD"},
    )


class FakeAdapter:
    def __init__(self, records, exact_prices=None, fail_exact=()):
        self.records = records
        self.exact_prices = exact_prices or {}
        self.fail_exact = set(fail_exact)
        self.explore_records = {}
        self.flight_deal_calls = []
        self.exact_calls = []

    async def flight_deals(self, *, origin, anchor_departure, anchor_return):
        self.flight_deal_calls.append((origin, anchor_departure, anchor_return))
        return ProviderResult("gflights", "flight_deals", "complete", tuple(self.records.get(origin, ())))

    async def explore(self, *, origin, month=None, duration="week", max_price=None):
        return ProviderResult("gflights", "explore", "complete", tuple(self.explore_records.get(origin, ())))

    async def exact(self, *, origin, destination, departure_date, return_date=None, **kwargs):
        self.exact_calls.append((origin, destination, departure_date, return_date))
        if (origin, destination) in self.fail_exact:
            return ProviderResult("gflights", "exact", "failed", error="synthetic exact failure")
        source = next(
            record
            for values in [*self.records.values(), *self.explore_records.values()]
            for record in values
            if record.origin.iata == origin and record.destination.iata == destination
        )
        return ProviderResult("gflights", "exact", "complete", (exact(source, self.exact_prices.get((origin, destination), source.current_price_twd)),))

    async def open_jaw(self, *, legs):
        first_origin, first_destination, _ = legs[0]
        return ProviderResult(
            "gflights", "open_jaw", "complete",
            (AirfareRecord(
                record_id="open-jaw-test", provider="gflights", surface="open_jaw",
                origin=AirportIdentity(first_origin), destination=AirportIdentity(first_destination),
                legs=tuple(AirfareLeg(o, d, dt) for o, d, dt in legs), current_price_twd=9000,
                observed_at=RUN_AT.isoformat(), verification_state="revalidated",
                evidence_class="exact_revalidated_candidate", complete_airfare=True, booking_token="open-jaw-token",
                reproducible_search={"legs": list(legs), "currency": "TWD"},
            ),),
        )


class ProductionRadarTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    def full_adapter(self):
        records = {
            "TPE": [deal("TPE", "NRT", "Japan", 6500, 10000, 35)],
            "TSA": [deal("TSA", "GMP", "South Korea", 6300, 9000, 30)],
            "RMQ": [deal("RMQ", "KMG", "China", 7200, 12000, 40)],
            "KHH": [deal("KHH", "SYD", "Australia", 15000, 20000, 25)],
        }
        prices = {("TPE", "NRT"): 6900, ("TSA", "GMP"): 7000, ("RMQ", "KMG"): 7600, ("KHH", "SYD"): 15500}
        return FakeAdapter(records, prices)

    async def test_shared_pipeline_covers_four_origins_and_all_priority_slices(self):
        adapter = self.full_adapter()
        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)
        self.assertTrue(result.coverage["all_origins_attempted"])
        self.assertEqual(set(result.coverage["origins"]), {"TPE", "TSA", "RMQ", "KHH"})
        for market in ("japan", "korea", "china", "other_asia_oceania"):
            self.assertGreaterEqual(result.coverage["markets"][market]["discovered"], 1)
            self.assertGreaterEqual(result.coverage["markets"][market]["revalidated"], 1)
        self.assertEqual(len(adapter.flight_deal_calls), 12)

    async def test_formal_deals_recompute_current_anomaly_and_sort_anomaly_then_price(self):
        result = await ProductionRadar(policy=self.policy, adapter=self.full_adapter()).run(run_at=RUN_AT)
        routes = [(item.discovery.origin.iata, item.discovery.destination.iata) for item in result.deals]
        self.assertEqual(routes, [("RMQ", "KMG"), ("TPE", "NRT"), ("KHH", "SYD"), ("TSA", "GMP")])
        strengths = [round(item.anomaly_strength_percent or 0, 1) for item in result.deals]
        self.assertEqual(strengths, [36.7, 31.0, 22.5, 22.2])
        self.assertTrue(all(item.anomaly_source == "google_flight_deals" for item in result.deals))

    async def test_exact_failure_is_signal_and_never_guessed_into_deal(self):
        adapter = self.full_adapter()
        adapter.fail_exact.add(("TPE", "NRT"))
        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)
        self.assertNotIn(("TPE", "NRT"), [(item.discovery.origin.iata, item.discovery.destination.iata) for item in result.deals])
        failed = [item for item in result.signals if item.discovery.destination.iata == "NRT"]
        self.assertEqual(len(failed), 1)
        self.assertIn("failed closed", failed[0].reason)

    async def test_weak_explore_seed_can_only_become_deal_via_lower_priority_history_truth(self):
        adapter = FakeAdapter({origin: [] for origin in ("TPE", "TSA", "RMQ", "KHH")})
        seed = weak_explore("TPE", "ICN", "South Korea")
        adapter.explore_records["TPE"] = [seed]
        adapter.exact_prices[("TPE", "ICN")] = 5000
        prior = []
        for index in range(10):
            observed = RUN_AT - timedelta(days=index + 1)
            prior.append(FareObservation(
                observation_id=f"prior-{index}", radar_run_id=f"prior-run-{index}", observed_at=observed.isoformat(),
                origin="TPE", destination="ICN", departure_date="2026-09-20", trip_type="round_trip",
                normalized_twd_price=7000 + index * 100, fare_scope="usable_complete_trip", availability_state="available",
                source_id="test", source_url=None, verification_state="revalidated", original_price=7000 + index * 100, original_currency="TWD",
            ))
        result = await ProductionRadar(policy=self.policy, adapter=adapter, prior_history=prior).run(run_at=RUN_AT)
        icn = next(item for item in result.deals if item.discovery.destination.iata == "ICN")
        self.assertEqual(icn.anomaly_source, "own_price_history")
        self.assertGreater(icn.anomaly_strength_percent or 0, 0)

    async def test_without_own_history_qualified_external_deal_is_not_blocked(self):
        result = await ProductionRadar(policy=self.policy, adapter=self.full_adapter(), prior_history=()).run(run_at=RUN_AT)
        self.assertEqual(len(result.deals), 4)

    async def test_source_router_contract_blocks_runtime_when_ssot_primary_changes(self):
        policy = deepcopy(self.policy)
        policy["source_routing"]["selected_routes"]["shared"]["origin_wide_discovery"]["primary_provider"] = "unexpected_provider"
        adapter = self.full_adapter()
        result = await ProductionRadar(policy=policy, adapter=adapter).run(run_at=RUN_AT)
        self.assertEqual(result.deals, ())
        self.assertEqual(adapter.flight_deal_calls, [])
        self.assertTrue(all(details["status"] == "failed" for details in result.coverage["origins"].values()))

    async def test_open_jaw_exact_is_available_selectively_not_mandatory(self):
        runtime = ProductionRadar(policy=self.policy, adapter=self.full_adapter())
        result = await runtime.revalidate_open_jaw(legs=[("TPE", "NRT", "2026-09-10"), ("KIX", "KHH", "2026-09-15")])
        self.assertEqual(result.coverage_state, "complete")
        self.assertEqual(result.records[0].surface, "open_jaw")
        self.assertEqual(result.records[0].current_price_twd, 9000)

    async def test_run_artifacts_are_immutable_history_plus_schema_v2_publication(self):
        result = await ProductionRadar(policy=self.policy, adapter=self.full_adapter()).run(run_at=RUN_AT)
        snapshot, manifest = build_run_artifacts(result, policy=self.policy)
        self.assertEqual(snapshot.schema_version, 1)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(len(manifest["deals"]), 4)
        self.assertTrue(snapshot.observations)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_run_artifacts(result, policy=self.policy, output_dir=Path(tmp))
            for value in paths.values():
                self.assertTrue(Path(value).exists())
            loaded = json.loads(Path(paths["publication_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(loaded["legacy_views_status"], "diagnostic_or_transition_only")


if __name__ == "__main__":
    unittest.main()
