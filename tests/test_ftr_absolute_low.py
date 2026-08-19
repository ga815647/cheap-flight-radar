from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult
from cheap_flight_radar.ftr_absolute_low import (
    FTRAbsoluteLowPolicyError,
    OUTPUT_STATE,
    SUPPORTED_INPUT_STATES,
    SUPPORTED_ORDERING,
    apply_absolute_low_selection,
    select_absolute_low_non_deals,
    validate_absolute_low_policy,
)
from cheap_flight_radar.production_radar import RadarItem, RadarRunResult
from cheap_flight_radar.production_runtime import run_once

ROOT = Path(__file__).resolve().parents[1]
RUN_AT = datetime.fromisoformat("2026-08-19T08:00:00+08:00")


def exact_record(
    record_id: str,
    *,
    price: int = 4200,
    origin: str = "TPE",
    destination: str = "KIX",
    return_gateway: str | None = None,
    outbound_date: str = "2026-10-05",
    return_date: str = "2026-10-09",
    observed_at: str = "2026-08-19T08:05:00+08:00",
    verification_state: str = "revalidated",
    evidence_class: str = "exact_revalidated_candidate",
    complete_airfare: bool = True,
    surface: str = "exact",
    booking_token: str | None = "token",
) -> AirfareRecord:
    if surface == "open_jaw":
        return_gateway = return_gateway or "KHH"
        legs = (
            AirfareLeg(origin, destination, outbound_date, "08:00+08:00", "12:00+09:00"),
            AirfareLeg("FUK", return_gateway, return_date, "13:00+09:00", "15:30+08:00"),
        )
        reproducible = {
            "legs": [(leg.origin, leg.destination, leg.date) for leg in legs],
            "currency": "TWD",
            "country": "TW",
        }
    else:
        legs = (AirfareLeg(origin, destination, outbound_date, "08:00+08:00", "12:00+09:00"),)
        reproducible = {
            "origin": origin,
            "destination": destination,
            "date": outbound_date,
            "return_date": return_date,
            "currency": "TWD",
            "country": "TW",
        }
    return AirfareRecord(
        record_id=record_id,
        provider="gflights",
        surface=surface,
        origin=AirportIdentity(origin, city=origin, country="Taiwan"),
        destination=AirportIdentity(destination, city=destination, country="Japan"),
        legs=legs,
        current_price_twd=price,
        observed_at=observed_at,
        verification_state=verification_state,
        evidence_class=evidence_class,
        complete_airfare=complete_airfare,
        booking_token=booking_token,
        reproducible_search=reproducible,
    )


def radar_item(
    record: AirfareRecord | None,
    *,
    state: str = "exact_revalidated_candidate",
    classification: str = "Signal",
    observation_id: str | None = None,
) -> RadarItem:
    base = record or exact_record("fallback")
    return RadarItem(
        classification=classification,
        state=state,
        discovery=base,
        exact=record,
        anomaly_source=None,
        anomaly_strength_percent=None,
        reason="fixture",
        observation_id=observation_id if observation_id is not None else (f"obs-{record.record_id}" if record else None),
    )


def run_result(*, pool=(), deals=()) -> RadarRunResult:
    return RadarRunResult(
        radar_run_id="production-radar-20260819T080000+0800",
        run_at=RUN_AT.isoformat(),
        deals=tuple(deals),
        signals=tuple(pool),
        coverage={},
        provider_failures=(),
        exact_non_deal_candidates=tuple(pool),
    )


class AbsoluteLowSelectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    def test_cheap_non_anomaly_exact_revalidated_complete_fare_is_selected(self):
        source = radar_item(exact_record("cheap-non-anomaly", price=3900))
        result = apply_absolute_low_selection(run_result(pool=(source,)), policy=deepcopy(self.policy))
        self.assertEqual([item.state for item in result.ftr_absolute_low_non_deals], [OUTPUT_STATE])
        self.assertEqual(result.ftr_absolute_low_non_deals[0].exact.record_id, "cheap-non-anomaly")
        self.assertEqual(result.signals[0].state, "exact_revalidated_candidate")

    def test_lower_looking_generic_or_weak_signal_is_not_selected(self):
        weak = radar_item(exact_record("weak-cheaper", price=1000), state="weak_seed")
        valid = radar_item(exact_record("valid", price=3900))
        selected = select_absolute_low_non_deals(run_result(pool=(weak, valid)), policy=deepcopy(self.policy))
        self.assertEqual([item.exact.record_id for item in selected], ["valid"])

    def test_formal_deal_is_not_relabelled_or_duplicated(self):
        record = exact_record("same-itinerary", price=3500)
        deal = radar_item(record, classification="Deal", state="deal")
        candidate = radar_item(record)
        result = apply_absolute_low_selection(run_result(pool=(candidate,), deals=(deal,)), policy=deepcopy(self.policy))
        self.assertEqual(result.deals, (deal,))
        self.assertEqual(result.ftr_absolute_low_non_deals, ())

    def test_incomplete_non_exact_failed_non_converged_and_stale_only_are_ineligible(self):
        base = exact_record("base")
        invalid = (
            radar_item(replace(base, record_id="incomplete", complete_airfare=False)),
            radar_item(replace(base, record_id="nonexact", verification_state="exact_search")),
            radar_item(replace(base, record_id="wrong-class", evidence_class="weak_seed")),
            radar_item(replace(base, record_id="failed"), state="exact_search_failed"),
            radar_item(replace(base, record_id="non-converged"), state="exact_search_non_converged"),
            radar_item(replace(base, record_id="stale", observed_at="2026-08-17T00:00:00+08:00")),
            radar_item(replace(base, record_id="no-provenance", booking_token=None, legs=(AirfareLeg("TPE", "KIX", "2026-10-05"),))),
            radar_item(None, state="weak_seed"),
        )
        self.assertEqual(select_absolute_low_non_deals(run_result(pool=invalid), policy=deepcopy(self.policy)), ())

    def test_budget_truncates_by_absolute_price_not_anomaly(self):
        policy = deepcopy(self.policy)
        policy["ftr_handoff"]["absolute_low_non_deal_producer"]["budget"]["max_selected_count"] = 2
        pool = (
            radar_item(exact_record("p3000", price=3000, destination="NRT")),
            radar_item(exact_record("p2000", price=2000, destination="KIX")),
            radar_item(exact_record("p2500", price=2500, destination="FUK")),
        )
        selected = select_absolute_low_non_deals(run_result(pool=pool), policy=policy)
        self.assertEqual([item.exact.record_id for item in selected], ["p2000", "p2500"])

    def test_equal_price_ties_have_stable_complete_order(self):
        first = exact_record("a-id", price=3000)
        second = replace(
            exact_record("z-id", price=3000),
            legs=(AirfareLeg("TPE", "KIX", "2026-10-05", "09:00+08:00", "13:00+09:00"),),
        )
        pool = (radar_item(second), radar_item(first))
        selected = select_absolute_low_non_deals(run_result(pool=pool), policy=deepcopy(self.policy))
        self.assertEqual([item.exact.record_id for item in selected], ["a-id", "z-id"])

    def test_identical_input_repeated_and_reordered_has_identical_selected_ids(self):
        first = radar_item(exact_record("first", price=2500, destination="FUK"))
        second = radar_item(exact_record("second", price=2600, destination="NRT"))
        third = radar_item(exact_record("third", price=2700, destination="KIX"))
        a = select_absolute_low_non_deals(run_result(pool=(first, second, third)), policy=deepcopy(self.policy))
        b = select_absolute_low_non_deals(run_result(pool=(third, first, second)), policy=deepcopy(self.policy))
        self.assertEqual([item.exact.record_id for item in a], [item.exact.record_id for item in b])

    def test_existing_open_jaw_identity_is_preserved_without_new_search_behavior(self):
        source = radar_item(exact_record("open-jaw", price=4100, surface="open_jaw", return_gateway="KHH"))
        selected = select_absolute_low_non_deals(run_result(pool=(source,)), policy=deepcopy(self.policy))
        self.assertEqual(len(selected), 1)
        exact = selected[0].exact
        self.assertEqual(exact.origin.iata, "TPE")
        self.assertEqual(exact.destination.iata, "KIX")
        self.assertEqual(exact.legs[-1].origin, "FUK")
        self.assertEqual(exact.legs[-1].destination, "KHH")

    def test_machine_ssot_and_implementation_contract_drift_fails_closed(self):
        producer = validate_absolute_low_policy(deepcopy(self.policy))
        self.assertEqual(tuple(producer["input_states"]), SUPPORTED_INPUT_STATES)
        self.assertEqual(tuple(producer["ordering"]), SUPPORTED_ORDERING)
        self.assertEqual(producer["budget"]["max_selected_count"], 5)
        self.assertFalse(self.policy["ftr_handoff"]["canonical_activation"]["enabled"])
        drift_cases = (
            ("source_collection", "generic_signals", "source_collection drifted"),
            ("ordering", ["record_id_asc"], "ordering drifted"),
        )
        for field, value, message in drift_cases:
            with self.subTest(field=field):
                drifted = deepcopy(self.policy)
                drifted["ftr_handoff"]["absolute_low_non_deal_producer"][field] = value
                with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, message):
                    validate_absolute_low_policy(drifted)


class NonAnomalyRuntimeAdapter:
    def __init__(self):
        self.seed = AirfareRecord(
            record_id="weak-floor-seed",
            provider="gflights",
            surface="flight_deals",
            origin=AirportIdentity("TPE"),
            destination=AirportIdentity("KIX", city="Osaka", country="Japan"),
            legs=(AirfareLeg("TPE", "KIX", "2026-10-05"), AirfareLeg("KIX", "TPE", "2026-10-09")),
            current_price_twd=4200,
            observed_at=RUN_AT.isoformat(),
            verification_state="discovery",
            evidence_class="weak_seed",
            complete_airfare=True,
            reproducible_search={"origin": "TPE", "currency": "TWD"},
        )

    async def flight_deals(self, *, origin, anchor_departure, anchor_return):
        return ProviderResult("gflights", "flight_deals", "complete", (self.seed,) if origin == "TPE" else ())

    async def explore(self, *, origin, **kwargs):
        return ProviderResult("gflights", "explore", "complete", ())

    async def exact(self, *, origin, destination, departure_date, return_date=None, **kwargs):
        record = exact_record(
            "runtime-exact-non-deal",
            price=4200,
            origin=origin,
            destination=destination,
            outbound_date=departure_date,
            return_date=return_date or "2026-10-09",
            observed_at="2026-08-19T08:05:00+08:00",
        )
        return ProviderResult("gflights", "exact", "complete", (record,))

    async def cheapest_dates(self, **kwargs):
        return ProviderResult("gflights", "cheapest_dates", "complete", ())

    async def open_jaw(self, **kwargs):
        return ProviderResult("gflights", "open_jaw", "empty", ())


class AbsoluteLowRuntimeIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_uses_existing_exact_non_deal_pool_without_rewriting_signal_truth(self):
        policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        result = await run_once(policy=policy, adapter=NonAnomalyRuntimeAdapter(), run_at=RUN_AT)
        self.assertEqual([item.exact.record_id for item in result.ftr_absolute_low_non_deals], ["runtime-exact-non-deal"])
        self.assertTrue(any(item.state == "exact_revalidated_candidate" for item in result.signals))
        self.assertFalse(any(item.state == OUTPUT_STATE for item in result.signals))


if __name__ == "__main__":
    unittest.main()
