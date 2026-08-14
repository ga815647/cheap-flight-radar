from datetime import datetime, timezone
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.price_history import (
    FareObservation,
    build_snapshot,
    compare_with_history,
    current_live_floors,
    snapshot_from_json,
    snapshot_repository_path,
    snapshot_to_json,
)


ROOT = Path(__file__).resolve().parents[1]


def obs(
    observation_id: str,
    *,
    radar_run_id: str = "run-current",
    observed_at: str = "2026-08-11T12:00:00+00:00",
    origin: str = "TPE",
    destination: str = "ICN",
    departure_date: str = "2026-08-21",
    price: float | None = 5000,
    availability_state: str = "available",
    fare_scope: str = "usable_complete_trip",
    trip_type: str = "round_trip",
    source_id: str = "web",
    verification_state: str = "discovery",
    related_observation_id: str | None = None,
) -> FareObservation:
    return FareObservation(
        observation_id=observation_id,
        radar_run_id=radar_run_id,
        observed_at=observed_at,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        trip_type=trip_type,
        normalized_twd_price=price,
        fare_scope=fare_scope,
        availability_state=availability_state,
        source_id=source_id,
        source_url=None,
        verification_state=verification_state,
        original_price=price,
        original_currency="TWD",
        related_observation_id=related_observation_id,
    )


class PriceHistoryPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "flight-radar.yaml").open("r", encoding="utf-8") as handle:
            cls.policy = yaml.safe_load(handle)["price_history"]

    def test_history_is_durable_in_github_not_chatgpt(self):
        persistence = self.policy["persistence"]
        self.assertEqual(persistence["durable_store"], "github_repository")
        self.assertEqual(persistence["repository"], "self")
        self.assertEqual(persistence["ref"], "history/price-observations")
        self.assertTrue(persistence["immutable_run_snapshots"])
        self.assertTrue(persistence["github_actions_is_not_durable_history_service"])
        self.assertEqual(persistence["artifact_role"], "transient_handoff_only")

    def test_history_policy_has_robust_windows_and_sparse_guards(self):
        self.assertEqual(self.policy["baseline"]["statistic"], "median")
        self.assertEqual(self.policy["baseline"]["moving_windows_days"], [7, 30, 90])
        self.assertEqual(self.policy["baseline"]["minimum_samples_per_window"], 3)
        self.assertEqual(self.policy["rolling_lows"]["windows_days"], [30, 90, 365])
        self.assertTrue(self.policy["rolling_lows"]["include_all_time"])
        self.assertEqual(self.policy["percentile"]["minimum_samples"], 10)
        self.assertEqual(self.policy["comparison_origin_airports"], ["TPE", "TSA", "RMQ", "KHH"])
        self.assertEqual(
            self.policy["percentile"]["insufficient_samples_action"],
            "return_unknown",
        )


class PriceHistoryComputationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "flight-radar.yaml").open("r", encoding="utf-8") as handle:
            cls.policy = yaml.safe_load(handle)["price_history"]

    def test_current_live_floors_separate_0_30_from_0_120(self):
        current = [
            obs("near", departure_date="2026-08-20", price=4800),
            obs("far", departure_date="2026-10-20", price=3200),
            obs("stale", departure_date="2026-08-19", price=2500, availability_state="stale"),
            obs("old-run", radar_run_id="run-old", departure_date="2026-08-18", price=2000),
        ]
        floors = current_live_floors(
            current,
            radar_run_id="run-current",
            run_at=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
            horizon_days=120,
        )
        self.assertEqual(floors.near_term.observation_id, "near")
        self.assertEqual(floors.horizon_absolute.observation_id, "far")

    def test_comparison_pools_allowed_origins_for_same_destination_trip_type_and_lead_bucket(self):
        current = obs("current", departure_date="2026-08-21", price=4000)
        history = [
            obs("same-1", radar_run_id="r1", origin="KHH", observed_at="2026-08-01T12:00:00+00:00", departure_date="2026-08-11", price=5000),
            obs("same-2", radar_run_id="r2", origin="RMQ", observed_at="2026-08-02T12:00:00+00:00", departure_date="2026-08-12", price=5200),
            obs("same-3", radar_run_id="r3", origin="TSA", observed_at="2026-08-03T12:00:00+00:00", departure_date="2026-08-13", price=5400),
            obs("wrong-destination", radar_run_id="r4", observed_at="2026-08-04T12:00:00+00:00", destination="PUS", departure_date="2026-08-14", price=1000),
            obs("wrong-origin", radar_run_id="r6", origin="KNH", observed_at="2026-08-04T12:00:00+00:00", departure_date="2026-08-14", price=900),
            obs("wrong-bucket", radar_run_id="r5", observed_at="2026-08-01T12:00:00+00:00", departure_date="2026-09-20", price=1000),
        ]
        result = compare_with_history(current, history, self.policy)
        self.assertEqual(result.sample_count, 3)
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.moving_medians_twd[30].sample_count, 3)
        self.assertEqual(result.moving_medians_twd[30].value, 5200)
        self.assertAlmostEqual(result.percent_below_baseline, (5200 - 4000) / 5200 * 100)
        self.assertIsNone(result.historical_percentile)

    def test_same_run_duplicate_sightings_do_not_inflate_confidence(self):
        current = obs("current", price=4000)
        history = [
            obs("r1-source-a", radar_run_id="r1", observed_at="2026-08-01T12:00:00+00:00", departure_date="2026-08-11", price=5200),
            obs("r1-source-b", radar_run_id="r1", observed_at="2026-08-01T12:05:00+00:00", departure_date="2026-08-11", price=5000),
            obs("r2", radar_run_id="r2", observed_at="2026-08-02T12:00:00+00:00", departure_date="2026-08-12", price=5400),
        ]
        result = compare_with_history(current, history, self.policy)
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.all_time_low_twd, 5000)
        self.assertEqual(result.confidence, "sparse")

    def test_sparse_history_does_not_invent_median_or_percentile(self):
        current = obs("current", price=4000)
        history = [
            obs("h1", radar_run_id="r1", observed_at="2026-08-01T12:00:00+00:00", departure_date="2026-08-11", price=5000),
            obs("h2", radar_run_id="r2", observed_at="2026-08-02T12:00:00+00:00", departure_date="2026-08-12", price=5500),
        ]
        result = compare_with_history(current, history, self.policy)
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.confidence, "sparse")
        self.assertIsNone(result.selected_baseline_twd)
        self.assertIsNone(result.percent_below_baseline)
        self.assertIsNone(result.historical_percentile)
        self.assertEqual(result.all_time_low_twd, 5000)
        self.assertIsNone(result.anomaly_label)

    def test_percentile_and_historical_floor_need_ten_prior_samples(self):
        current = obs("current", price=3900)
        history = [
            obs(
                f"h{i}",
                radar_run_id=f"r{i}",
                observed_at=f"2026-08-{i + 1:02d}T01:00:00+00:00",
                departure_date=f"2026-08-{i + 11:02d}",
                price=4000 + i * 100,
            )
            for i in range(10)
        ]
        result = compare_with_history(current, history, self.policy)
        self.assertEqual(result.sample_count, 10)
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.historical_percentile, 0.0)
        self.assertEqual(result.all_time_low_twd, 4000)
        self.assertEqual(result.distance_from_all_time_low_twd, -100)
        self.assertEqual(result.anomaly_label, "historical_floor")

    def test_stale_and_disappeared_events_are_provenance_not_price_samples(self):
        current = obs("current", price=4800)
        history = [
            obs("available", radar_run_id="r1", observed_at="2026-08-01T12:00:00+00:00", departure_date="2026-08-11", price=5000),
            obs("stale", radar_run_id="r2", observed_at="2026-08-02T12:00:00+00:00", departure_date="2026-08-12", price=3000, availability_state="stale", related_observation_id="available"),
            obs("gone", radar_run_id="r3", observed_at="2026-08-03T12:00:00+00:00", departure_date="2026-08-13", price=None, availability_state="disappeared", related_observation_id="available"),
        ]
        result = compare_with_history(current, history, self.policy)
        self.assertEqual(result.sample_count, 1)
        self.assertEqual(result.all_time_low_twd, 5000)

    def test_snapshot_path_and_payload_are_immutable_run_shaped(self):
        snapshot = build_snapshot(
            "run:jp/kr",
            datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
            [obs("a", radar_run_id="run:jp/kr")],
        )
        path = snapshot_repository_path(snapshot)
        self.assertEqual(path, "data/price-history/2026/08/11/run-jp-kr.json")
        self.assertEqual(snapshot.schema_version, 1)
        self.assertEqual(snapshot.radar_run_id, "run:jp/kr")
        self.assertEqual(len(snapshot.observations), 1)
        self.assertEqual(snapshot_from_json(snapshot_to_json(snapshot)), snapshot)


if __name__ == "__main__":
    unittest.main()
