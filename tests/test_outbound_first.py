from pathlib import Path
import json
import unittest

import yaml

from cheap_flight_radar.models import (
    LiveReturnAirport,
    OriginSweepRequest,
    OutboundProbe,
    ReturnFare,
    RoundTripBenchmark,
    SeriousOutbound,
)
from cheap_flight_radar.outbound_first import (
    build_return_expansion_requests,
    complete_candidate,
    downstream_expansion_modes,
    make_outbound_seed,
    outbound_first_coverage,
    outbound_probe_request,
    public_indexed_social_seed,
    seed_one_way_price_twd,
    select_stage_a_candidates,
    validate_outbound_probe,
)


ROOT = Path(__file__).resolve().parents[1]


class OutboundFirstContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "flight-radar.yaml").open("r", encoding="utf-8") as handle:
            cls.policy = yaml.safe_load(handle)
        with (ROOT / "tests/fixtures/outbound_first/expedia_tpe_origin_surface.json").open(
            "r", encoding="utf-8"
        ) as handle:
            cls.expedia_fixture = json.load(handle)

    def sweep(self, origin="TPE"):
        return OriginSweepRequest(origin=origin, horizon_start="2026-08-12")

    def probe(
        self,
        *,
        seed_id,
        market,
        origin="TPE",
        destination,
        outbound_date,
        price,
        one_way_hours=3.5,
    ):
        return OutboundProbe(
            seed_id=seed_id,
            profile=market if market in {"japan", "korea", "china"} else "world",
            origin=origin,
            destination=destination,
            market=market,
            outbound_date=outbound_date,
            price_twd=price,
            one_way_hours=one_way_hours,
            source_id="exact_web_probe",
            source_url="https://example.test/exact",
            observed_at="2026-08-12T20:30:00+08:00",
        )

    def serious(self, probe):
        return SeriousOutbound(probe=probe, selection_reasons=("test_selected",))

    def test_expedia_fixture_preserves_evidence_scope_without_rt_division(self):
        request = self.sweep()
        normalized = []
        for row in self.expedia_fixture["observations"]:
            normalized.append(
                make_outbound_seed(
                    request,
                    seed_id=row["seed_id"],
                    destination=row["destination"],
                    market=row["market"],
                    source_id=self.expedia_fixture["source_id"],
                    source_url=self.expedia_fixture["source_url"],
                    observed_at=self.expedia_fixture["observed_at"],
                    evidence_kind=row["evidence_kind"],
                    outbound_date_hint=row.get("outbound_date_hint"),
                    return_date_hint=row.get("return_date_hint"),
                    displayed_price_twd=row.get("displayed_price_twd"),
                )
            )
        one_way, round_trip, destination_only = normalized
        self.assertEqual(seed_one_way_price_twd(one_way), 2442)
        self.assertIsNone(seed_one_way_price_twd(round_trip))
        self.assertEqual(round_trip.displayed_price_twd, 5556)
        self.assertIsNone(seed_one_way_price_twd(destination_only))

    def test_origin_sweep_is_structurally_destination_free_and_covers_all_origins(self):
        requests = [self.sweep(origin) for origin in ("TPE", "TSA", "RMQ", "KHH")]
        self.assertNotIn("destination", OriginSweepRequest.__dataclass_fields__)
        coverage = outbound_first_coverage(requests, self.policy["search"]["origin_airports"])
        self.assertTrue(coverage.can_claim_outbound_first)
        self.assertEqual(coverage.missing_origins, ())

    def test_seed_creates_first_known_destination_probe(self):
        seed = make_outbound_seed(
            self.sweep(),
            seed_id="expedia:tpe:icn",
            destination="ICN",
            market="korea",
            source_id="expedia_tw_airport_origin_surface",
            source_url="https://www.expedia.com.tw/en/lp/airports/tpe/flights-from-taoyuan-intl-airport",
            observed_at="2026-08-12T20:30:00+08:00",
            evidence_kind="one_way_fare",
            displayed_price_twd=2442,
        )
        request = outbound_probe_request(seed, "2026-09-30")
        self.assertEqual(request.destination, "ICN")
        self.assertEqual(request.search_stage, "outbound_probe")

    def test_stage_a_keeps_near_and_horizon_floors_and_market_diversity(self):
        probes = [
            self.probe(seed_id="k1", market="korea", destination="ICN", outbound_date="2026-08-25", price=2300),
            self.probe(seed_id="k2", market="korea", destination="PUS", outbound_date="2026-09-20", price=2100),
            self.probe(seed_id="k3", market="korea", destination="CJU", outbound_date="2026-10-20", price=1800),
            self.probe(seed_id="j1", market="japan", destination="KIX", outbound_date="2026-08-26", price=3200),
            self.probe(seed_id="c1", market="china", destination="PVG", outbound_date="2026-09-10", price=3300),
            self.probe(seed_id="w1", market="world", destination="DMK", outbound_date="2026-09-11", price=3400),
        ]
        selection = select_stage_a_candidates(probes, run_date="2026-08-12", candidate_limit=6)
        serious_markets = {item.probe.market for item in selection.serious_outbounds}
        self.assertEqual(serious_markets, {"japan", "korea", "china", "world"})
        korea_near = [
            floor for floor in selection.near_term_floors
            if floor.market == "korea" and floor.origin == "TPE"
        ][0]
        korea_horizon = [
            floor for floor in selection.horizon_floors
            if floor.market == "korea" and floor.origin == "TPE"
        ][0]
        self.assertEqual(korea_near.probe.seed_id, "k1")
        self.assertEqual(korea_horizon.probe.seed_id, "k3")

    def test_only_exact_one_way_probe_can_qualify(self):
        seed = make_outbound_seed(
            self.sweep(),
            seed_id="s1",
            destination="ICN",
            market="korea",
            source_id="origin",
            source_url="https://example.test/origin",
            observed_at="2026-08-12T20:30:00+08:00",
            evidence_kind="round_trip_deal",
            displayed_price_twd=4935,
        )
        probe = self.probe(
            seed_id="s1",
            market="korea",
            destination="ICN",
            outbound_date="2026-09-30",
            price=2442,
        )
        validate_outbound_probe(seed, probe)
        bad = OutboundProbe(**{**probe.__dict__, "fare_scope": "round_trip"})
        with self.assertRaises(ValueError):
            validate_outbound_probe(seed, bad)

    def test_return_expansion_searches_multiple_dates_and_only_live_extra_airports(self):
        outbound = self.probe(
            seed_id="s1",
            market="korea",
            destination="ICN",
            outbound_date="2026-09-30",
            price=2442,
            one_way_hours=2.5,
        )
        requests = build_return_expansion_requests(
            self.serious(outbound),
            self.policy,
            additional_return_airports=(
                LiveReturnAirport("TNN", True, source_id="live-route"),
                LiveReturnAirport("HUN", False, source_id="not-live"),
            ),
        )
        dates = {request.return_date for request in requests}
        airports = {request.taiwan_return_airport for request in requests}
        self.assertGreaterEqual(len(dates), 2)
        self.assertTrue({"TPE", "TSA", "RMQ", "KHH", "TNN"}.issubset(airports))
        self.assertNotIn("HUN", airports)

    def test_round_trip_benchmark_is_mandatory_and_can_win(self):
        outbound = self.probe(
            seed_id="s1",
            market="korea",
            destination="ICN",
            outbound_date="2026-09-30",
            price=2442,
        )
        return_fare = ReturnFare(
            seed_id="s1",
            foreign_origin="ICN",
            taiwan_return_airport="KHH",
            return_date="2026-10-04",
            price_twd=2800,
            source_id="return-web",
            source_url="https://example.test/return",
            observed_at="2026-08-12T20:30:00+08:00",
        )
        benchmark = RoundTripBenchmark(
            origin="TPE",
            destination="ICN",
            outbound_date="2026-09-30",
            return_date="2026-10-04",
            price_twd=4935,
            source_id="rt-web",
            source_url="https://example.test/rt",
            observed_at="2026-08-12T20:30:00+08:00",
        )
        candidate = complete_candidate(self.serious(outbound), return_fare, benchmark)
        self.assertEqual(candidate.constructed_total_twd, 5242)
        self.assertEqual(candidate.selected_kind, "conventional_round_trip")
        self.assertEqual(candidate.selected_total_twd, 4935)

    def test_open_jaw_and_china_specialist_are_post_benchmark_modes(self):
        outbound = self.probe(
            seed_id="c1",
            market="china",
            destination="PVG",
            outbound_date="2026-09-30",
            price=2200,
        )
        return_fare = ReturnFare(
            seed_id="c1",
            foreign_origin="PVG",
            taiwan_return_airport="KHH",
            return_date="2026-10-04",
            price_twd=2500,
            source_id="return",
            source_url="https://example.test/return",
            observed_at="2026-08-12T20:30:00+08:00",
        )
        benchmark = RoundTripBenchmark(
            origin="TPE",
            destination="PVG",
            outbound_date="2026-09-30",
            return_date="2026-10-04",
            price_twd=5000,
            source_id="rt",
            source_url="https://example.test/rt",
            observed_at="2026-08-12T20:30:00+08:00",
        )
        candidate = complete_candidate(self.serious(outbound), return_fare, benchmark)
        modes = downstream_expansion_modes(candidate, profile="china")
        self.assertIn("open_jaw", modes)
        self.assertIn("mixed_taiwan_return", modes)
        self.assertIn("mainland_high_speed_rail", modes)
        self.assertIn("kinmen_gateway", modes)
        self.assertNotIn("kinmen_gateway", downstream_expansion_modes(candidate, profile="world"))

    def test_public_indexed_facebook_signal_is_seed_only(self):
        signal = public_indexed_social_seed(
            source_id="facebook_public_index",
            source_url="https://www.facebook.com/public-example",
            observed_at="2026-08-12T20:30:00+08:00",
            route_signal="TPE-KIX",
            date_signal="September",
            promo_signal="sale",
            price_text="NT$2,999",
            publicly_indexed_without_login=True,
        )
        self.assertEqual(signal.role, "opportunistic")
        self.assertEqual(signal.verification_state, "seed_only")
        self.assertFalse(signal.can_establish_verified_fare)
        with self.assertRaises(ValueError):
            public_indexed_social_seed(
                source_id="private",
                source_url="https://www.facebook.com/private",
                observed_at="2026-08-12T20:30:00+08:00",
                route_signal="TPE-KIX",
                publicly_indexed_without_login=False,
            )


if __name__ == "__main__":
    unittest.main()
