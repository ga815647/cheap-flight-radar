from datetime import datetime, timedelta
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult
from cheap_flight_radar.ftr_absolute_low import apply_absolute_low_selection
from cheap_flight_radar.ftr_handoff import _variant_from_item
from cheap_flight_radar.production_radar import RadarItem, RadarRunResult, _item_json
from cheap_flight_radar.production_runtime import converge_rp06_route_variants


RUN_AT = datetime.fromisoformat("2026-08-20T10:00:00+08:00")


def load_policy():
    return yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))


def discovery(*, origin="TPE", destination="KIX", country="Japan", record_id="seed"):
    return AirfareRecord(
        record_id=record_id,
        provider="gflights",
        surface="flight_deals",
        origin=AirportIdentity(origin, city=origin, country="Taiwan"),
        destination=AirportIdentity(destination, city=destination, country=country),
        legs=(
            AirfareLeg(origin, destination, "2026-10-05"),
            AirfareLeg(destination, origin, "2026-10-09"),
        ),
        current_price_twd=6000,
        observed_at=RUN_AT.isoformat(),
        verification_state="discovery",
        evidence_class="weak_seed",
        complete_airfare=True,
        reproducible_search={"origin": origin, "currency": "TWD"},
    )


def exact_variant(
    *,
    record_id,
    legs,
    price=4200,
    verification_state="revalidated",
    evidence_class="exact_revalidated_candidate",
    complete_airfare=True,
    observed_at=None,
    booking_token="bookable",
):
    first = legs[0]
    return AirfareRecord(
        record_id=record_id,
        provider="gflights",
        surface="open_jaw",
        origin=AirportIdentity(first[0]),
        destination=AirportIdentity(first[1]),
        legs=tuple(AirfareLeg(*leg) for leg in legs),
        current_price_twd=price,
        observed_at=observed_at or RUN_AT.isoformat(),
        verification_state=verification_state,
        evidence_class=evidence_class,
        complete_airfare=complete_airfare,
        booking_token=booking_token,
        reproducible_search={"legs": [list(leg) for leg in legs], "currency": "TWD"},
    )


def base_result(*, seed=None, deals=(), signals=None):
    seed = seed or discovery()
    if signals is None:
        signals = (
            RadarItem(
                classification="Signal",
                state="weak_seed",
                discovery=seed,
                exact=None,
                anomaly_source=None,
                anomaly_strength_percent=None,
                reason="fixture provenance",
            ),
        )
    return RadarRunResult(
        radar_run_id="production-radar-rp06-fixture",
        run_at=RUN_AT.isoformat(),
        deals=tuple(deals),
        signals=tuple(signals),
        coverage={},
        provider_failures=(),
        exact_non_deal_candidates=(),
        ftr_absolute_low_non_deals=(),
    )


def capture(legs, record=None, *, request_sent=True, state="complete"):
    records = (record,) if record is not None else ()
    return (
        tuple(tuple(value for value in leg) for leg in legs),
        ProviderResult("gflights", "open_jaw", state, records, request_sent=request_sent),
    )


class RP06TypedRouteVariantAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def test_complete_mixed_return_exact_enters_dedicated_pool_without_signal_authority(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("KIX", "KHH", "2026-10-09"))
        exact = exact_variant(record_id="mixed", legs=legs, price=4100)
        result = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, exact),),
            policy=self.policy,
        )
        self.assertEqual([item.exact.record_id for item in result.exact_non_deal_candidates], ["mixed"])
        self.assertFalse(any(item.state == "exact_revalidated_candidate" for item in result.signals))

    def test_complete_destination_open_jaw_enters_dedicated_pool(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-09"))
        exact = exact_variant(record_id="open-jaw", legs=legs, price=3900)
        result = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, exact),),
            policy=self.policy,
        )
        self.assertEqual([item.exact.record_id for item in result.exact_non_deal_candidates], ["open-jaw"])

    def test_open_jaw_can_win_existing_rp02_price_first_selection(self):
        seed = discovery(destination="KIX")
        conventional = exact_variant(
            record_id="conventional-like",
            legs=(("TPE", "KIX", "2026-10-05"), ("KIX", "TPE", "2026-10-09")),
            price=5200,
        )
        conventional_item = RadarItem(
            classification="Signal",
            state="exact_revalidated_candidate",
            discovery=seed,
            exact=conventional,
            anomaly_source=None,
            anomaly_strength_percent=None,
            reason="fixture",
            observation_id="obs-conventional",
        )
        base = RadarRunResult(
            **{
                **base_result(seed=seed).__dict__,
                "exact_non_deal_candidates": (conventional_item,),
            }
        )
        open_legs = (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-09"))
        open_exact = exact_variant(record_id="cheaper-open-jaw", legs=open_legs, price=3300)
        converged = converge_rp06_route_variants(
            base,
            open_jaw_results=(capture(open_legs, open_exact),),
            policy=self.policy,
        )
        selected = apply_absolute_low_selection(converged, policy=self.policy)
        self.assertEqual(selected.ftr_absolute_low_non_deals[0].exact.record_id, "cheaper-open-jaw")
        self.assertEqual(selected.ftr_absolute_low_non_deals[0].state, "ftr_absolute_low_non_deal")

    def test_generic_signal_even_if_renamed_and_exact_never_becomes_selector_input(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-09"))
        exact = exact_variant(record_id="forged", legs=legs, price=1000)
        forged = RadarItem(
            classification="Signal",
            state="exact_revalidated_candidate",
            discovery=discovery(),
            exact=exact,
            anomaly_source=None,
            anomaly_strength_percent=None,
            reason="generic journal forgery",
            observation_id="obs-forged",
        )
        selected = apply_absolute_low_selection(
            base_result(signals=(forged,)),
            policy=self.policy,
        )
        self.assertEqual(selected.exact_non_deal_candidates, ())
        self.assertEqual(selected.ftr_absolute_low_non_deals, ())

    def test_weak_incomplete_stale_nonreproducible_and_24h_variants_do_not_enter_pool(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-09"))
        short_legs = (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-06"))
        cases = [
            (legs, exact_variant(record_id="weak", legs=legs, verification_state="exact_search")),
            (legs, exact_variant(record_id="incomplete", legs=legs, complete_airfare=False)),
            (legs, exact_variant(record_id="stale", legs=legs, observed_at=(RUN_AT - timedelta(hours=25)).isoformat())),
            (legs, exact_variant(record_id="nonrepro", legs=legs, booking_token=None)),
            (short_legs, exact_variant(record_id="exactly-24h", legs=short_legs)),
        ]
        cases[3] = (legs, AirfareRecord(**{**cases[3][1].__dict__, "reproducible_search": {}}))
        for requested_legs, record in cases:
            with self.subTest(record=record.record_id):
                result = converge_rp06_route_variants(
                    base_result(),
                    open_jaw_results=(capture(requested_legs, record),),
                    policy=self.policy,
                )
                self.assertEqual(result.exact_non_deal_candidates, ())

    def test_offshore_return_gateway_is_ineligible(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("KIX", "MZG", "2026-10-09"))
        exact = exact_variant(record_id="offshore", legs=legs)
        result = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, exact),),
            policy=self.policy,
        )
        self.assertEqual(result.exact_non_deal_candidates, ())

    def test_formal_deal_identity_is_not_relabelled_as_absolute_low(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-09"))
        exact = exact_variant(record_id="formal-deal-exact", legs=legs, price=3000)
        deal = RadarItem(
            classification="Deal",
            state="deal",
            discovery=discovery(record_id="deal-seed"),
            exact=exact,
            anomaly_source="google_flight_deals",
            anomaly_strength_percent=40.0,
            reason="formal deal fixture",
            observation_id="deal-observation",
        )
        result = converge_rp06_route_variants(
            base_result(deals=(deal,)),
            open_jaw_results=(capture(legs, exact),),
            policy=self.policy,
        )
        self.assertEqual(result.exact_non_deal_candidates, ())
        self.assertEqual(apply_absolute_low_selection(result, policy=self.policy).ftr_absolute_low_non_deals, ())

    def test_opportunistic_nonprimary_main_island_gateway_requires_live_exact_record(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("KIX", "TNN", "2026-10-09"))
        no_live = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, None, request_sent=False, state="failed"),),
            policy=self.policy,
        )
        self.assertEqual(no_live.exact_non_deal_candidates, ())
        row = no_live.coverage["return_gateway_expansion"]["seed_attempts"][0]
        self.assertFalse(row["live_route_evidence_observed"])
        self.assertEqual(row["attempted_mixed_return_gateways"], [])
        self.assertFalse(row["provider_request_sent"])

        with self.assertRaisesRegex(RuntimeError, "cannot be attempted without live route evidence"):
            converge_rp06_route_variants(
                base_result(),
                open_jaw_results=(capture(legs, None, request_sent=True),),
                policy=self.policy,
            )

        live = exact_variant(record_id="live-tnn", legs=legs)
        with_live = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, live),),
            policy=self.policy,
        )
        self.assertEqual([item.exact.record_id for item in with_live.exact_non_deal_candidates], ["live-tnn"])
        live_row = with_live.coverage["return_gateway_expansion"]["seed_attempts"][0]
        self.assertTrue(live_row["live_route_evidence_observed"])
        self.assertEqual(live_row["attempted_mixed_return_gateways"], ["TNN"])


class RP06RouteIdentityAndGatewayCoverageTest(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def _selected_variant(self, legs, record_id):
        exact = exact_variant(record_id=record_id, legs=legs)
        converged = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, exact),),
            policy=self.policy,
        )
        selected = apply_absolute_low_selection(converged, policy=self.policy)
        self.assertEqual(len(selected.ftr_absolute_low_non_deals), 1)
        return _variant_from_item(_item_json(selected.ftr_absolute_low_non_deals[0]))

    def test_mixed_return_retains_actual_gateway_and_round_trip_destination_shape(self):
        variant = self._selected_variant(
            (("TPE", "KIX", "2026-10-05"), ("KIX", "KHH", "2026-10-09")),
            "mixed-shape",
        )
        self.assertEqual(variant["destination_route_shape"], {"arrival_airport": "KIX", "departure_airport": "KIX"})
        self.assertEqual(variant["taiwan_origin_gateway"], "TPE")
        self.assertEqual(variant["taiwan_return_gateway"], "KHH")

    def test_destination_open_jaw_is_distinct_destination_route_shape(self):
        variant = self._selected_variant(
            (("TPE", "KIX", "2026-10-05"), ("FUK", "TPE", "2026-10-09")),
            "open-shape",
        )
        self.assertEqual(variant["destination_route_shape"], {"arrival_airport": "KIX", "departure_airport": "FUK"})
        self.assertEqual(variant["taiwan_origin_gateway"], "TPE")
        self.assertEqual(variant["taiwan_return_gateway"], "TPE")

    def test_gateway_evidence_names_exact_attempt_and_primary_not_attempted(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("KIX", "KHH", "2026-10-09"))
        result = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, exact_variant(record_id="coverage", legs=legs)),),
            policy=self.policy,
        )
        coverage = result.coverage["return_gateway_expansion"]
        self.assertFalse(coverage["search_exhaustive"])
        self.assertFalse(coverage["provider_call_budget_changed_by_rp06"])
        self.assertTrue(coverage["opportunistic_non_primary"]["allowed"])
        self.assertTrue(coverage["opportunistic_non_primary"]["requires_live_route_evidence"])
        row = coverage["seed_attempts"][0]
        self.assertEqual(row["selected_mixed_return_gateway"], "KHH")
        self.assertEqual(row["attempted_mixed_return_gateways"], ["KHH"])
        self.assertEqual(
            row["configured_primary_gateways_not_attempted"],
            ["TPE", "TSA", "RMQ"],
        )

    def test_suppressed_gateway_is_selected_but_not_falsely_claimed_attempted(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("KIX", "KHH", "2026-10-09"))
        result = converge_rp06_route_variants(
            base_result(),
            open_jaw_results=(capture(legs, None, request_sent=False, state="failed"),),
            policy=self.policy,
        )
        row = result.coverage["return_gateway_expansion"]["seed_attempts"][0]
        self.assertEqual(row["selected_mixed_return_gateway"], "KHH")
        self.assertEqual(row["attempted_mixed_return_gateways"], [])
        self.assertEqual(
            row["configured_primary_gateways_not_attempted"],
            ["TPE", "TSA", "RMQ", "KHH"],
        )
        self.assertFalse(row["provider_request_sent"])

    def test_duplicate_mixed_attempt_for_same_seed_fails_closed(self):
        legs = (("TPE", "KIX", "2026-10-05"), ("KIX", "KHH", "2026-10-09"))
        record = exact_variant(record_id="dup", legs=legs)
        with self.assertRaisesRegex(RuntimeError, "above one attempt per expansion seed"):
            converge_rp06_route_variants(
                base_result(),
                open_jaw_results=(capture(legs, record), capture(legs, record)),
                policy=self.policy,
            )


if __name__ == "__main__":
    unittest.main()
