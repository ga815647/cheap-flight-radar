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
from cheap_flight_radar.production_radar import ProductionRadar, _minimum_away_satisfied, build_run_artifacts, write_run_artifacts

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "flight-radar.yaml"
RUN_AT = datetime.fromisoformat("2026-08-13T02:00:00+08:00")


def deal(origin: str, destination: str, country: str, price: int, typical: int, discount: float, *, suffix: str = "") -> AirfareRecord:
    record_suffix = f"-{suffix}" if suffix else ""
    return AirfareRecord(
        record_id=f"deal-{origin}-{destination}{record_suffix}", provider="gflights", surface="flight_deals",
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


def exact(discovery: AirfareRecord, price: int, departure_date: str | None = None, return_date: str | None = None) -> AirfareRecord:
    dep = departure_date or discovery.outbound_date or "2026-09-10"
    ret = return_date or discovery.return_date or "2026-09-14"
    return AirfareRecord(
        record_id=f"exact-{discovery.origin.iata}-{discovery.destination.iata}-{dep}-{ret}", provider="gflights", surface="exact",
        origin=AirportIdentity(discovery.origin.iata), destination=AirportIdentity(discovery.destination.iata),
        legs=(AirfareLeg(discovery.origin.iata, discovery.destination.iata, dep, departure_time="06:00", arrival_time="09:00"),),
        current_price_twd=price, observed_at=RUN_AT.isoformat(), verification_state="revalidated",
        evidence_class="exact_revalidated_candidate", complete_airfare=True, booking_token="token",
        reproducible_search={"origin": discovery.origin.iata, "destination": discovery.destination.iata, "date": dep, "return_date": ret, "currency": "TWD"},
    )


def flexible_record(discovery: AirfareRecord, price: int, departure_date: str, return_date: str) -> AirfareRecord:
    return AirfareRecord(
        record_id=f"flex-{discovery.origin.iata}-{discovery.destination.iata}-{departure_date}-{return_date}",
        provider="gflights", surface="cheapest_dates", origin=AirportIdentity(discovery.origin.iata),
        destination=AirportIdentity(discovery.destination.iata, city=discovery.destination.city, country=discovery.destination.country),
        legs=(AirfareLeg(discovery.origin.iata, discovery.destination.iata, departure_date), AirfareLeg(discovery.destination.iata, discovery.origin.iata, return_date)),
        current_price_twd=price, observed_at=RUN_AT.isoformat(), verification_state="seed_only", evidence_class="weak_seed",
        complete_airfare=True, reproducible_search={"origin": discovery.origin.iata, "destination": discovery.destination.iata},
    )


class FakeAdapter:
    def __init__(self, records, exact_prices=None, fail_exact=()):
        self.records = records
        self.exact_prices = exact_prices or {}
        self.fail_exact = set(fail_exact)
        self.explore_records = {}
        self.flexible_overrides = {}
        self.flight_deal_calls = []
        self.explore_calls = []
        self.exact_calls = []
        self.cheapest_dates_calls = []
        self.open_jaw_calls = []

    def _source(self, origin, destination):
        return next(
            record
            for values in [*self.records.values(), *self.explore_records.values()]
            for record in values
            if record.origin.iata == origin and record.destination.iata == destination
        )

    async def flight_deals(self, *, origin, anchor_departure, anchor_return):
        self.flight_deal_calls.append((origin, anchor_departure, anchor_return))
        return ProviderResult("gflights", "flight_deals", "complete", tuple(self.records.get(origin, ())))

    async def explore(self, *, origin, month=None, duration="week", max_price=None):
        self.explore_calls.append(origin)
        return ProviderResult("gflights", "explore", "complete", tuple(self.explore_records.get(origin, ())))

    async def exact(self, *, origin, destination, departure_date, return_date=None, **kwargs):
        self.exact_calls.append((origin, destination, departure_date, return_date))
        if (origin, destination) in self.fail_exact:
            return ProviderResult("gflights", "exact", "failed", error="synthetic exact failure")
        source = self._source(origin, destination)
        override = self.exact_prices.get((origin, destination, departure_date, return_date))
        price = override if override is not None else self.exact_prices.get((origin, destination), source.current_price_twd)
        return ProviderResult("gflights", "exact", "complete", (exact(source, price, departure_date, return_date),))

    async def cheapest_dates(self, *, origin, destination, start_date, months=3, trip_duration_days=None):
        self.cheapest_dates_calls.append((origin, destination, start_date, months, trip_duration_days))
        source = self._source(origin, destination)
        override = self.flexible_overrides.get((origin, destination))
        if override is not None:
            departure_date, return_date, price = override
        else:
            departure_date = source.outbound_date or "2026-09-10"
            return_date = source.return_date or "2026-09-14"
            price = source.current_price_twd or 999999
        return ProviderResult("gflights", "cheapest_dates", "complete", (flexible_record(source, price, departure_date, return_date),))

    async def open_jaw(self, *, legs):
        self.open_jaw_calls.append(tuple(legs))
        first_origin, first_destination, _ = legs[0]
        return ProviderResult(
            "gflights", "open_jaw", "complete",
            (AirfareRecord(
                record_id=f"open-jaw-test-{len(self.open_jaw_calls)}", provider="gflights", surface="open_jaw",
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
        self.assertEqual(adapter.explore_calls, ["TPE", "TSA", "RMQ", "KHH"])

    async def test_formal_deals_recompute_current_anomaly_and_sort_anomaly_then_price(self):
        result = await ProductionRadar(policy=self.policy, adapter=self.full_adapter()).run(run_at=RUN_AT)
        routes = [(item.discovery.origin.iata, item.discovery.destination.iata) for item in result.deals]
        self.assertEqual(routes, [("RMQ", "KMG"), ("TPE", "NRT"), ("KHH", "SYD"), ("TSA", "GMP")])
        strengths = [round(item.anomaly_strength_percent or 0, 1) for item in result.deals]
        self.assertEqual(strengths, [36.7, 31.0, 22.5, 22.2])
        self.assertTrue(all(item.anomaly_source == "google_flight_deals" for item in result.deals))

    async def test_same_destination_uses_cheapest_origin_and_lowest_typical_baseline(self):
        adapter = FakeAdapter({
            "TPE": [],
            "TSA": [deal("TSA", "CJU", "South Korea", 17639, 63237, 72)],
            "RMQ": [deal("RMQ", "CJU", "South Korea", 9023, 11576, 22)],
            "KHH": [],
        })
        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)
        cju = next(item for item in result.deals if item.discovery.destination.iata == "CJU")
        self.assertEqual(cju.discovery.origin.iata, "RMQ")
        self.assertEqual(cju.current_complete_airfare_twd, 9023)
        self.assertEqual(cju.anomaly_baseline_twd, 11576)
        self.assertEqual(cju.anomaly_scope, "destination_airport_all_taiwan_origins")
        self.assertAlmostEqual(cju.anomaly_strength_percent or 0, (11576 - 9023) / 11576 * 100)
        self.assertIn(("RMQ", "CJU", "2026-09-10", "2026-09-14"), adapter.exact_calls)

    async def test_nonrepresentative_variant_is_retained_for_expansion(self):
        adapter = FakeAdapter({
            "TPE": [],
            "TSA": [deal("TSA", "CJU", "South Korea", 17639, 63237, 72)],
            "RMQ": [deal("RMQ", "CJU", "South Korea", 9023, 11576, 22)],
            "KHH": [],
        })
        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)
        flexible_routes = {(origin, destination) for origin, destination, *_ in adapter.cheapest_dates_calls}
        self.assertIn(("TSA", "CJU"), flexible_routes)
        self.assertIn(("RMQ", "CJU"), flexible_routes)
        self.assertEqual(result.coverage["destination_representative_count"], 1)
        self.assertEqual(result.coverage["expansion_seed_count"], 2)

    async def test_deep_search_budget_is_not_capped_by_publication_limit(self):
        policy = deepcopy(self.policy)
        policy["search"]["deep_search_candidate_limit"] = 3
        policy["search"]["final_shortlist_limit"] = 1
        adapter = FakeAdapter({
            "TPE": [
                deal("TPE", "NRT", "Japan", 6000, 10000, 40),
                deal("TPE", "KIX", "Japan", 6100, 10000, 39),
                deal("TPE", "FUK", "Japan", 6200, 10000, 38),
            ],
            "TSA": [], "RMQ": [], "KHH": [],
        })
        result = await ProductionRadar(policy=policy, adapter=adapter).run(run_at=RUN_AT)
        self.assertEqual(result.coverage["deep_search_candidate_limit"], 3)
        self.assertEqual(result.coverage["final_shortlist_limit"], 1)
        self.assertEqual(result.coverage["destination_representative_count"], 3)
        self.assertEqual(result.coverage["execution"]["conventional_exact"]["attempts"], 3)
        self.assertEqual(len(result.deals), 1)

    async def test_run_itself_exercises_flexible_mixed_return_and_open_jaw(self):
        adapter = self.full_adapter()
        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)
        execution = result.coverage["execution"]
        self.assertGreater(execution["flexible_dates"]["attempts"], 0)
        self.assertGreater(execution["mixed_taiwan_return"]["attempts"], 0)
        self.assertGreater(execution["open_jaw"]["attempts"], 0)
        self.assertGreater(len(adapter.cheapest_dates_calls), 0)
        self.assertGreater(len(adapter.open_jaw_calls), 0)
        self.assertTrue(any(item.state == "mixed_taiwan_return_alternative" for item in result.signals))
        self.assertTrue(any(item.state == "open_jaw_airfare_alternative" for item in result.signals))

    async def test_exact_failure_is_signal_and_never_guessed_into_deal(self):
        adapter = self.full_adapter()
        adapter.fail_exact.add(("TPE", "NRT"))
        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)
        self.assertNotIn(("TPE", "NRT"), [(item.discovery.origin.iata, item.discovery.destination.iata) for item in result.deals])
        failed = [item for item in result.signals if item.discovery.destination.iata == "NRT"]
        self.assertTrue(failed)
        self.assertTrue(any("failed" in item.reason for item in failed))

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

    def test_minimum_away_uses_actual_times_when_complete_provider_segments_exist(self):
        under_24 = AirfareRecord(
            record_id="timed-short", provider="test", surface="flight_deals",
            origin=AirportIdentity("TPE"), destination=AirportIdentity("NRT", country="Japan"),
            legs=(
                AirfareLeg("TPE", "NRT", "2026-09-10", departure_time="23:00", arrival_time="01:00"),
                AirfareLeg("NRT", "TPE", "2026-09-12", departure_time="00:30", arrival_time="03:30"),
            ),
            current_price_twd=5000, observed_at=RUN_AT.isoformat(), verification_state="revalidated",
            evidence_class="exact_revalidated_candidate", complete_airfare=True,
        )
        over_24 = AirfareRecord(
            **{**under_24.__dict__, "record_id": "timed-long", "legs": (
                under_24.legs[0],
                AirfareLeg("NRT", "TPE", "2026-09-12", departure_time="02:00", arrival_time="05:00"),
            )}
        )
        self.assertFalse(_minimum_away_satisfied(under_24))
        self.assertTrue(_minimum_away_satisfied(over_24))

    async def test_run_artifacts_are_immutable_history_plus_schema_v2_publication(self):
        result = await ProductionRadar(policy=self.policy, adapter=self.full_adapter()).run(run_at=RUN_AT)
        snapshot, manifest = build_run_artifacts(result, policy=self.policy)
        self.assertEqual(snapshot.schema_version, 1)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(len(manifest["deals"]), 4)
        self.assertTrue(snapshot.observations)
        self.assertGreater(manifest["coverage"]["execution"]["flexible_dates"]["attempts"], 0)
        self.assertTrue(any(item["state"] == "mixed_taiwan_return_alternative" for item in manifest["signals"]))
        self.assertTrue(any(item["state"] == "open_jaw_airfare_alternative" for item in manifest["signals"]))
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_run_artifacts(result, policy=self.policy, output_dir=Path(tmp))
            for value in paths.values():
                self.assertTrue(Path(value).exists())
            loaded = json.loads(Path(paths["publication_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(loaded["legacy_views_status"], "diagnostic_or_transition_only")


if __name__ == "__main__":
    unittest.main()
