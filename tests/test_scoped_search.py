import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult
from cheap_flight_radar.ftr_handoff import FTRHandoffError, load_manifest_snapshot
from cheap_flight_radar.scoped_search import (
    AvailabilityWindow,
    DurationConstraint,
    ScopedExecutionPolicy,
    ScopedSearchError,
    ScopedSearchRequest,
    acquire_scoped,
    build_scoped_plan,
    execute_scoped_search,
    validate_scoped_search_policy,
    validate_scoped_snapshot,
)


RUN_AT = datetime.fromisoformat("2026-08-20T08:00:00+08:00")
GENERATED_AT = "2026-08-20T08:05:00+08:00"


def load_policy():
    return yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))


def discovery_record(
    *,
    record_id,
    origin,
    destination,
    country,
    outbound,
    returned,
    price,
    qualified=False,
):
    return AirfareRecord(
        record_id=record_id,
        provider="gflights",
        surface="flight_deals",
        origin=AirportIdentity(origin, city=origin, country="Taiwan"),
        destination=AirportIdentity(destination, city=destination, country=country),
        legs=(
            AirfareLeg(origin, destination, outbound),
            AirfareLeg(destination, origin, returned),
        ),
        current_price_twd=price,
        typical_price_twd=price * 2 if qualified else None,
        discount_percent=50.0 if qualified else None,
        anomaly_authority="google_flight_deals" if qualified else None,
        observed_at=RUN_AT.isoformat(),
        verification_state="discovery",
        evidence_class="qualified_round_trip_deal" if qualified else "weak_seed",
        complete_airfare=True,
        booking_token=f"seed-{record_id}",
        reproducible_search={
            "origin": origin,
            "date": outbound,
            "return_date": returned,
            "currency": "TWD",
            "country": "TW",
        },
    )


def exact_record(
    seed,
    *,
    price=None,
    verification_state="revalidated",
    returned=None,
    return_departure_time="13:30:00",
):
    return_date = returned or seed.return_date
    return AirfareRecord(
        record_id="exact-" + seed.record_id,
        provider="gflights",
        surface="exact",
        origin=seed.origin,
        destination=seed.destination,
        legs=(
            AirfareLeg(
                seed.origin.iata,
                seed.destination.iata,
                seed.outbound_date,
                departure_time=f"{seed.outbound_date}T09:00:00",
                arrival_time=f"{seed.outbound_date}T12:00:00",
            ),
            AirfareLeg(
                seed.destination.iata,
                seed.origin.iata,
                return_date,
                departure_time=f"{return_date}T{return_departure_time}",
                arrival_time=f"{return_date}T16:00:00",
            ),
        ),
        current_price_twd=price if price is not None else seed.current_price_twd,
        observed_at=RUN_AT.isoformat(),
        verification_state=verification_state,
        evidence_class="exact_revalidated_candidate",
        complete_airfare=True,
        airlines=("Fixture Air",),
        booking_token="book-" + seed.record_id,
        reproducible_search={
            "origin": seed.origin.iata,
            "destination": seed.destination.iata,
            "date": seed.outbound_date,
            "return_date": return_date,
        },
    )


class FakeScopedAdapter:
    def __init__(self, *, discovery_factory=None, exact_factory=None, fail_discovery=False):
        self.discovery_factory = discovery_factory or (lambda **kwargs: ())
        self.exact_factory = exact_factory
        self.fail_discovery = fail_discovery
        self.flight_deals_calls = []
        self.exact_calls = []
        self.explore_calls = []
        self.cheapest_dates_calls = []
        self.open_jaw_calls = []

    async def flight_deals(self, **kwargs):
        self.flight_deals_calls.append(dict(kwargs))
        if self.fail_discovery:
            return ProviderResult("gflights", "flight_deals", "failed", error="fixture failure")
        records = tuple(self.discovery_factory(**kwargs))
        return ProviderResult("gflights", "flight_deals", "complete", records)

    async def exact(self, **kwargs):
        self.exact_calls.append(dict(kwargs))
        if self.exact_factory is None:
            return ProviderResult("gflights", "exact", "empty")
        record = self.exact_factory(**kwargs)
        if record is None:
            return ProviderResult("gflights", "exact", "empty")
        return ProviderResult("gflights", "exact", "complete", (record,))

    async def explore(self, **kwargs):
        self.explore_calls.append(dict(kwargs))
        raise AssertionError("scoped runtime must not call unconstrainable Explore")

    async def cheapest_dates(self, **kwargs):
        self.cheapest_dates_calls.append(dict(kwargs))
        raise AssertionError("scoped runtime must not call unconstrainable cheapest_dates")

    async def open_jaw(self, **kwargs):
        self.open_jaw_calls.append(dict(kwargs))
        raise AssertionError("RP-03 must not add RP-06 open-jaw expansion")


def request(
    *,
    request_id="req-a",
    windows=(("2026-10-01", "2026-10-05"),),
    discovery_calls=8,
    exact_calls=8,
    duration=None,
    max_budget_twd=None,
):
    return ScopedSearchRequest(
        request_id=request_id,
        availability_windows=tuple(AvailabilityWindow(*value) for value in windows),
        execution_policy=ScopedExecutionPolicy(
            max_discovery_calls=discovery_calls,
            max_exact_revalidations=exact_calls,
        ),
        duration=duration,
        max_budget_twd=max_budget_twd,
    )


class ScopedPlanningTest(unittest.TestCase):
    def test_single_window_plan_only_contains_supplied_window(self):
        plan = build_scoped_plan(request(discovery_calls=8), policy=load_policy())
        self.assertTrue(plan.discovery_tasks)
        for task in plan.discovery_tasks:
            self.assertGreaterEqual(task.anchor_departure, "2026-10-01")
            self.assertLessEqual(task.anchor_return, "2026-10-05")
            self.assertLess(task.anchor_departure, task.anchor_return)
        self.assertNotEqual(plan.discovery_tasks[0].anchor_departure, "2026-08-20")

    def test_multiple_windows_are_merged_but_never_crossed(self):
        req = request(
            windows=(("2026-10-10", "2026-10-13"), ("2026-10-01", "2026-10-04")),
            discovery_calls=16,
        )
        one = build_scoped_plan(req, policy=load_policy())
        two = build_scoped_plan(req, policy=load_policy())
        self.assertEqual(one, two)
        self.assertEqual(one.windows[0].start_date, "2026-10-01")
        window_map = {
            f"w-{window.start_date}-{window.end_date}": window
            for window in one.windows
        }
        self.assertEqual(set(task.window_id for task in one.discovery_tasks), set(window_map))
        for task in one.discovery_tasks:
            window = window_map[task.window_id]
            self.assertGreaterEqual(task.anchor_departure, window.start_date)
            self.assertLessEqual(task.anchor_return, window.end_date)

    def test_duration_supplied_constrains_and_absent_is_not_fixed(self):
        unconstrained = build_scoped_plan(
            request(
                windows=(("2026-10-01", "2026-10-04"),),
                discovery_calls=12,
                duration=None,
            ),
            policy=load_policy(),
        )
        unconstrained_durations = {
            (
                datetime.fromisoformat(task.anchor_return)
                - datetime.fromisoformat(task.anchor_departure)
            ).days
            for task in unconstrained.discovery_tasks
        }
        self.assertIn(1, unconstrained_durations)

        constrained = build_scoped_plan(
            request(
                windows=(("2026-10-01", "2026-10-04"),),
                discovery_calls=12,
                duration=DurationConstraint(min_nights=2),
            ),
            policy=load_policy(),
        )
        constrained_durations = {
            (
                datetime.fromisoformat(task.anchor_return)
                - datetime.fromisoformat(task.anchor_departure)
            ).days
            for task in constrained.discovery_tasks
        }
        self.assertTrue(constrained_durations)
        self.assertNotIn(1, constrained_durations)
        self.assertTrue(all(value >= 2 for value in constrained_durations))

    def test_budget_truncation_and_identity_are_deterministic(self):
        req = request(
            windows=(("2026-10-01", "2026-10-10"), ("2026-11-01", "2026-11-10")),
            discovery_calls=3,
            exact_calls=2,
        )
        one = build_scoped_plan(req, policy=load_policy())
        two = build_scoped_plan(req, policy=load_policy())
        self.assertEqual(one.plan_id, two.plan_id)
        self.assertEqual(one.request_fingerprint, two.request_fingerprint)
        self.assertEqual(one.discovery_tasks, two.discovery_tasks)
        self.assertEqual(len(one.discovery_tasks), 3)
        self.assertTrue(one.discovery_truncated)


class ScopedAcquisitionSemanticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_calls_are_window_constrained_and_unconstrainable_surfaces_not_called(self):
        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            return (
                discovery_record(
                    record_id=f"seed-{anchor_departure}",
                    origin=origin,
                    destination="KIX",
                    country="Japan",
                    outbound=anchor_departure,
                    returned=anchor_return,
                    price=5000,
                    qualified=True,
                ),
            )

        def exact_factory(origin, destination, departure_date, return_date):
            seed = discovery_record(
                record_id=f"seed-{departure_date}",
                origin=origin,
                destination=destination,
                country="Japan",
                outbound=departure_date,
                returned=return_date,
                price=5000,
                qualified=True,
            )
            return exact_record(seed, price=4500)

        adapter = FakeScopedAdapter(
            discovery_factory=discovery_factory,
            exact_factory=exact_factory,
        )
        _, result, evidence = await acquire_scoped(
            request=request(discovery_calls=4, exact_calls=2),
            policy=load_policy(),
            adapter=adapter,
            run_at=RUN_AT,
        )
        self.assertEqual(len(adapter.flight_deals_calls), 4)
        for call in adapter.flight_deals_calls:
            self.assertGreaterEqual(call["anchor_departure"], "2026-10-01")
            self.assertLessEqual(call["anchor_return"], "2026-10-05")
        self.assertTrue(adapter.exact_calls)
        self.assertEqual(adapter.explore_calls, [])
        self.assertEqual(adapter.cheapest_dates_calls, [])
        self.assertEqual(adapter.open_jaw_calls, [])
        self.assertEqual(evidence["unconstrainable_surfaces"]["explore"], "not_attempted")
        self.assertEqual(result.coverage["execution"]["explore"]["attempts"], 0)

    async def test_out_of_window_provider_rows_are_not_exact_revalidated(self):
        outside = discovery_record(
            record_id="outside",
            origin="TPE",
            destination="KIX",
            country="Japan",
            outbound="2026-12-01",
            returned="2026-12-05",
            price=3000,
            qualified=True,
        )
        adapter = FakeScopedAdapter(
            discovery_factory=lambda **kwargs: (outside,) if kwargs["origin"] == "TPE" else (),
            exact_factory=lambda **kwargs: (_ for _ in ()).throw(AssertionError("outside row must not reach exact")),
        )
        _, result, _ = await acquire_scoped(
            request=request(discovery_calls=4, exact_calls=4),
            policy=load_policy(),
            adapter=adapter,
            run_at=RUN_AT,
        )
        self.assertEqual(adapter.exact_calls, [])
        self.assertEqual(result.deals, ())
        self.assertEqual(result.ftr_absolute_low_non_deals, ())

    async def test_formal_deal_semantics_are_preserved(self):
        seeds = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            seed = discovery_record(
                record_id="qualified",
                origin=origin,
                destination="KIX",
                country="Japan",
                outbound=anchor_departure,
                returned=anchor_return,
                price=5000,
                qualified=True,
            )
            seeds[(origin, "KIX", anchor_departure, anchor_return)] = seed
            return (seed,)

        def exact_factory(origin, destination, departure_date, return_date):
            return exact_record(seeds[(origin, destination, departure_date, return_date)], price=4500)

        _, result, _ = await acquire_scoped(
            request=request(discovery_calls=4, exact_calls=4),
            policy=load_policy(),
            adapter=FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory),
            run_at=RUN_AT,
        )
        self.assertEqual(len(result.deals), 1)
        self.assertEqual(result.deals[0].classification, "Deal")
        self.assertEqual(result.deals[0].state, "deal")
        self.assertEqual(result.deals[0].anomaly_source, "google_flight_deals")
        self.assertEqual(result.ftr_absolute_low_non_deals, ())

    async def test_adjacent_date_exact_actual_stay_over_24h_can_pass_minimum_away(self):
        seeds = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            seed = discovery_record(
                record_id="adjacent-over-24",
                origin=origin,
                destination="KIX",
                country="Japan",
                outbound=anchor_departure,
                returned=anchor_return,
                price=5000,
                qualified=True,
            )
            seeds[(origin, anchor_departure, anchor_return)] = seed
            return (seed,)

        def exact_factory(origin, destination, departure_date, return_date):
            self.assertEqual((datetime.fromisoformat(return_date) - datetime.fromisoformat(departure_date)).days, 1)
            return exact_record(
                seeds[(origin, departure_date, return_date)],
                price=4500,
                return_departure_time="13:30:00",
            )

        _, result, _ = await acquire_scoped(
            request=request(
                windows=(("2026-10-01", "2026-10-02"),),
                discovery_calls=4,
                exact_calls=4,
                duration=None,
            ),
            policy=load_policy(),
            adapter=FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory),
            run_at=RUN_AT,
        )
        self.assertEqual(len(result.deals), 1)

    async def test_adjacent_date_exact_actual_stay_at_or_below_24h_is_excluded(self):
        seeds = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            seed = discovery_record(
                record_id="adjacent-under-24",
                origin=origin,
                destination="KIX",
                country="Japan",
                outbound=anchor_departure,
                returned=anchor_return,
                price=5000,
                qualified=True,
            )
            seeds[(origin, anchor_departure, anchor_return)] = seed
            return (seed,)

        def exact_factory(origin, destination, departure_date, return_date):
            return exact_record(
                seeds[(origin, departure_date, return_date)],
                price=4500,
                return_departure_time="11:00:00",
            )

        _, result, _ = await acquire_scoped(
            request=request(
                windows=(("2026-10-01", "2026-10-02"),),
                discovery_calls=4,
                exact_calls=4,
                duration=None,
            ),
            policy=load_policy(),
            adapter=FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory),
            run_at=RUN_AT,
        )
        self.assertEqual(result.deals, ())
        self.assertEqual(result.exact_non_deal_candidates, ())
        self.assertEqual(result.ftr_absolute_low_non_deals, ())

    async def test_exact_non_deal_reaches_only_rp02_absolute_low_collection(self):
        seeds = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            seed = discovery_record(
                record_id="weak",
                origin=origin,
                destination="BKK",
                country="Thailand",
                outbound=anchor_departure,
                returned=anchor_return,
                price=3600,
                qualified=False,
            )
            seeds[(origin, "BKK", anchor_departure, anchor_return)] = seed
            return (seed,)

        def exact_factory(origin, destination, departure_date, return_date):
            return exact_record(seeds[(origin, destination, departure_date, return_date)], price=3400)

        _, result, _ = await acquire_scoped(
            request=request(discovery_calls=4, exact_calls=4),
            policy=load_policy(),
            adapter=FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory),
            run_at=RUN_AT,
        )
        self.assertEqual(result.deals, ())
        self.assertEqual(len(result.exact_non_deal_candidates), 1)
        self.assertEqual(len(result.ftr_absolute_low_non_deals), 1)
        self.assertEqual(result.ftr_absolute_low_non_deals[0].state, "ftr_absolute_low_non_deal")

    async def test_weak_or_incomplete_evidence_is_not_promoted(self):
        seed_box = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            seed = discovery_record(
                record_id="weak",
                origin=origin,
                destination="BKK",
                country="Thailand",
                outbound=anchor_departure,
                returned=anchor_return,
                price=3600,
            )
            seed_box["seed"] = seed
            return (seed,)

        def exact_factory(**kwargs):
            return exact_record(seed_box["seed"], price=3300, verification_state="exact_search")

        _, result, _ = await acquire_scoped(
            request=request(discovery_calls=4, exact_calls=4),
            policy=load_policy(),
            adapter=FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory),
            run_at=RUN_AT,
        )
        self.assertEqual(result.deals, ())
        self.assertEqual(result.ftr_absolute_low_non_deals, ())

    async def test_query_max_budget_is_only_a_hard_filter(self):
        seed_box = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            seed = discovery_record(
                record_id="budget",
                origin=origin,
                destination="BKK",
                country="Thailand",
                outbound=anchor_departure,
                returned=anchor_return,
                price=6000,
            )
            seed_box["seed"] = seed
            return (seed,)

        def exact_factory(**kwargs):
            return exact_record(seed_box["seed"], price=5500)

        _, result, _ = await acquire_scoped(
            request=request(discovery_calls=4, exact_calls=4, max_budget_twd=5000),
            policy=load_policy(),
            adapter=FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory),
            run_at=RUN_AT,
        )
        self.assertEqual(result.deals, ())
        self.assertEqual(result.exact_non_deal_candidates, ())
        self.assertEqual(result.ftr_absolute_low_non_deals, ())


class ScopedHandoffIsolationTest(unittest.IsolatedAsyncioTestCase):
    def _mixed_adapter(self):
        seeds = {}

        def discovery_factory(origin, anchor_departure, anchor_return):
            if origin != "TPE":
                return ()
            qualified = discovery_record(
                record_id="deal",
                origin=origin,
                destination="KIX",
                country="Japan",
                outbound=anchor_departure,
                returned=anchor_return,
                price=5000,
                qualified=True,
            )
            weak = discovery_record(
                record_id="low",
                origin=origin,
                destination="BKK",
                country="Thailand",
                outbound=anchor_departure,
                returned=anchor_return,
                price=3500,
            )
            for seed in (qualified, weak):
                seeds[(seed.origin.iata, seed.destination.iata, seed.outbound_date, seed.return_date)] = seed
            return qualified, weak

        def exact_factory(origin, destination, departure_date, return_date):
            seed = seeds[(origin, destination, departure_date, return_date)]
            return exact_record(seed, price=4500 if destination == "KIX" else 3300)

        return FakeScopedAdapter(discovery_factory=discovery_factory, exact_factory=exact_factory)

    async def test_success_writes_immutable_scoped_snapshot_manifest_and_preserves_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            latest = history / "data/ftr-feed/latest.json"
            status = history / "data/ftr-feed/current-status.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_bytes(b"canonical-latest-fixture\n")
            status.write_bytes(b'{"repair_required":true,"fixture":"incident"}\n')
            latest_before = latest.read_bytes()
            status_before = status.read_bytes()

            outcome = await execute_scoped_search(
                request=request(request_id="handoff-success", discovery_calls=4, exact_calls=4),
                policy=load_policy(),
                adapter=self._mixed_adapter(),
                history_dir=history,
                producer_commit_sha="deadbeef",
                run_at=RUN_AT,
                generated_at=GENERATED_AT,
            )
            self.assertEqual(outcome.snapshot["mode"], "scoped_search")
            self.assertTrue(outcome.staged["manifest_path"].startswith("data/ftr-feed/scoped/"))
            self.assertNotEqual(outcome.staged["manifest_path"], "data/ftr-feed/latest.json")
            self.assertTrue((history / outcome.staged["snapshot_path"]).exists())
            loaded = load_manifest_snapshot(history_dir=history, manifest_path=outcome.staged["manifest_path"])
            validate_scoped_snapshot(loaded, plan=outcome.plan)
            self.assertEqual(latest.read_bytes(), latest_before)
            self.assertEqual(status.read_bytes(), status_before)
            self.assertEqual(loaded["candidate_counts"]["deals"], 1)
            self.assertEqual(loaded["candidate_counts"]["absolute_low_non_deals"], 1)
            self.assertEqual(
                loaded["coverage"]["windows"],
                loaded["scoped_search"]["execution"]["window_execution"],
            )

    async def test_duplicate_same_request_replays_without_provider_calls_and_changed_intent_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            first_adapter = self._mixed_adapter()
            req = request(request_id="replay", discovery_calls=4, exact_calls=4)
            first = await execute_scoped_search(
                request=req,
                policy=load_policy(),
                adapter=first_adapter,
                history_dir=history,
                producer_commit_sha="deadbeef",
                run_at=RUN_AT,
                generated_at=GENERATED_AT,
            )
            replay_adapter = FakeScopedAdapter()
            replay = await execute_scoped_search(
                request=req,
                policy=load_policy(),
                adapter=replay_adapter,
                history_dir=history,
                producer_commit_sha="different-sha-is-not-used-on-replay",
                run_at=datetime.fromisoformat("2026-08-20T09:00:00+08:00"),
                generated_at="2026-08-20T09:05:00+08:00",
            )
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.run_id, first.run_id)
            self.assertEqual(replay_adapter.flight_deals_calls, [])
            changed = request(
                request_id="replay",
                windows=(("2026-11-01", "2026-11-05"),),
                discovery_calls=4,
                exact_calls=4,
            )
            with self.assertRaisesRegex(FTRHandoffError, "different scoped intent"):
                await execute_scoped_search(
                    request=changed,
                    policy=load_policy(),
                    adapter=FakeScopedAdapter(),
                    history_dir=history,
                    producer_commit_sha="deadbeef",
                    run_at=RUN_AT,
                    generated_at=GENERATED_AT,
                )

    async def test_failure_does_not_touch_canonical_latest_or_repair_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            latest = history / "data/ftr-feed/latest.json"
            status = history / "data/ftr-feed/current-status.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_bytes(b"canonical-before\n")
            status.write_bytes(b"repair-required-before\n")
            before = (latest.read_bytes(), status.read_bytes())
            with self.assertRaisesRegex(FTRHandoffError, "not consumable"):
                await execute_scoped_search(
                    request=request(request_id="failure", discovery_calls=4, exact_calls=4),
                    policy=load_policy(),
                    adapter=FakeScopedAdapter(fail_discovery=True),
                    history_dir=history,
                    producer_commit_sha="deadbeef",
                    run_at=RUN_AT,
                    generated_at=GENERATED_AT,
                )
            self.assertEqual((latest.read_bytes(), status.read_bytes()), before)
            scoped_dir = history / "data/ftr-feed/scoped"
            self.assertFalse(scoped_dir.exists() and any(scoped_dir.iterdir()))

    async def test_checksum_mismatch_and_invalid_scoped_snapshot_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            outcome = await execute_scoped_search(
                request=request(request_id="tamper", discovery_calls=4, exact_calls=4),
                policy=load_policy(),
                adapter=self._mixed_adapter(),
                history_dir=history,
                producer_commit_sha="deadbeef",
                run_at=RUN_AT,
                generated_at=GENERATED_AT,
            )
            snapshot_path = history / outcome.staged["snapshot_path"]
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            payload["terminal_state"] = "failed"
            with self.assertRaisesRegex(FTRHandoffError, "terminal_state"):
                validate_scoped_snapshot(payload)
            payload["terminal_state"] = "success"
            payload["schema_version"] = "99.0"
            with self.assertRaisesRegex(FTRHandoffError, "unsupported schema major"):
                validate_scoped_snapshot(payload)

            snapshot_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FTRHandoffError, "checksum mismatch"):
                load_manifest_snapshot(history_dir=history, manifest_path=outcome.staged["manifest_path"])


class ScopedSSOTDriftTest(unittest.TestCase):
    def test_machine_ssot_matches_runtime_and_canonical_activation_remains_false(self):
        policy = load_policy()
        contract = validate_scoped_search_policy(policy)
        self.assertEqual(contract["mode"], "scoped_search")
        self.assertFalse(policy["ftr_handoff"]["canonical_activation"]["enabled"])
        self.assertEqual(contract["acquisition"]["broad_horizon_then_post_filter"], "forbidden")
        self.assertFalse(contract["bounded_execution"]["search_horizon_days_is_scoped_budget"])
        self.assertEqual(
            contract["windows"]["adjacent_date_pair_without_duration"],
            "allowed_pending_exact_minimum_away_truth",
        )
        self.assertFalse(contract["windows"]["planner_calendar_difference_is_minimum_away_truth"])
        self.assertTrue(contract["coverage"]["availability_window_is_terminal_dimension"])
        self.assertEqual(contract["coverage"]["zero_provider_call_status"], "not_attempted")
        self.assertTrue(contract["bounded_execution"]["truncation_must_not_hide_unattempted_window"])

    def test_machine_ssot_drift_fails_closed(self):
        policy = load_policy()
        drifted = copy.deepcopy(policy)
        drifted["ftr_handoff"]["scoped_search_acquisition"]["windows"]["cross_window_trip"] = "allowed"
        with self.assertRaisesRegex(ScopedSearchError, "cross-window"):
            validate_scoped_search_policy(drifted)

        drifted = copy.deepcopy(policy)
        drifted["ftr_handoff"]["scoped_search_acquisition"]["coverage"]["zero_provider_call_status"] = "succeeded"
        with self.assertRaisesRegex(ScopedSearchError, "zero_provider_call_status"):
            validate_scoped_search_policy(drifted)

        drifted = copy.deepcopy(policy)
        drifted["ftr_handoff"]["canonical_activation"]["enabled"] = True
        with self.assertRaisesRegex(ScopedSearchError, "must not activate"):
            validate_scoped_search_policy(drifted)


if __name__ == "__main__":
    unittest.main()
