import json
from pathlib import Path
import tempfile
import unittest

from cheap_flight_radar.ftr_handoff import (
    CANONICAL_LATEST_PATH,
    FTRHandoffError,
    build_snapshot,
    load_manifest_snapshot,
    manifest_repository_path,
    snapshot_repository_path,
    stage_snapshot,
    validate_snapshot,
)


def record(
    record_id,
    *,
    origin="TPE",
    destination="KIX",
    return_gateway=None,
    outbound_date="2026-10-05",
    return_date="2026-10-09",
    price=5000,
    surface="exact",
    observed_at="2026-08-19T08:00:00+08:00",
):
    return_gateway = return_gateway or origin
    if surface == "open_jaw":
        legs = [
            {
                "origin": origin,
                "destination": destination,
                "date": outbound_date,
                "departure_time": "08:00+08:00",
                "arrival_time": "12:00+09:00",
            },
            {
                "origin": destination,
                "destination": return_gateway,
                "date": return_date,
                "departure_time": "13:00+09:00",
                "arrival_time": "15:30+08:00",
            },
        ]
        reproducible = {}
    else:
        legs = [
            {
                "origin": origin,
                "destination": destination,
                "date": outbound_date,
                "departure_time": "08:00+08:00",
                "arrival_time": "12:00+09:00",
            }
        ]
        reproducible = {"return_date": return_date}
    return {
        "record_id": record_id,
        "provider": "gflights",
        "surface": surface,
        "origin": {"iata": origin, "city": origin, "country": "Taiwan"},
        "destination": {"iata": destination, "city": destination, "country": "Japan"},
        "legs": legs,
        "current_price_twd": price,
        "observed_at": observed_at,
        "verification_state": "revalidated",
        "evidence_class": "qualified_round_trip_deal",
        "complete_airfare": True,
        "airlines": ["Example Air"],
        "evidence_url": "https://example.invalid/evidence",
        "reproducible_search": reproducible,
    }


def item(record_payload, *, classification="Deal", state="deal", price=None):
    return {
        "classification": classification,
        "state": state,
        "reason": "fixture",
        "observation_id": "obs-" + record_payload["record_id"],
        "current_complete_airfare_twd": price or record_payload["current_price_twd"],
        "discovery": record_payload,
        "exact": record_payload,
    }


def run_result(*, deals=(), signals=(), health="healthy"):
    return {
        "radar_run_id": "production-radar-20260819T080000+0800",
        "run_at": "2026-08-19T08:00:00+08:00",
        "deals": list(deals),
        "signals": list(signals),
        "coverage": {
            "origins": {
                "TPE": {"status": "complete", "returned_flight_deals": 2, "explore_seeds": 0},
                "KHH": {"status": "complete", "returned_flight_deals": 1, "explore_seeds": 0},
            },
            "markets": {
                "japan": {"discovered": 2, "qualified": 2, "revalidated": 2, "deals": 1},
                "korea": {"discovered": 0, "qualified": 0, "revalidated": 0, "deals": 0},
            },
            "provider_health": {
                "status": health,
                "technical_failure_count": 0 if health == "healthy" else 1,
                "reasons": [] if health == "healthy" else ["partial provider failure"],
            },
        },
        "provider_health": {
            "status": health,
            "technical_failure_count": 0 if health == "healthy" else 1,
            "reasons": [] if health == "healthy" else ["partial provider failure"],
        },
        "provider_failures": [] if health == "healthy" else [{"surface": "exact", "error": "fixture"}],
    }


class FTRHandoffTest(unittest.TestCase):
    def test_groups_taiwan_gateway_variants_under_destination_route_shape(self):
        tpe = item(record("tpe-kix", origin="TPE", destination="KIX", price=5000))
        khh = item(record("khh-kix", origin="KHH", destination="KIX", price=4700))
        snapshot = build_snapshot(
            run_result(deals=(tpe, khh)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(len(snapshot["opportunities"]), 1)
        opportunity = snapshot["opportunities"][0]
        self.assertEqual(
            opportunity["destination_route_shape"],
            {"arrival_airport": "KIX", "departure_airport": "KIX"},
        )
        self.assertEqual(
            {variant["taiwan_origin_gateway"] for variant in opportunity["variants"]},
            {"TPE", "KHH"},
        )
        self.assertEqual(opportunity["variants"][0]["complete_airfare_twd"], 4700)

    def test_destination_side_open_jaw_is_separate_opportunity(self):
        round_trip = item(record("kix-rt", destination="KIX", price=5000))
        open_jaw_record = record(
            "kix-fuk",
            destination="KIX",
            return_gateway="TPE",
            price=5300,
            surface="open_jaw",
        )
        open_jaw_record["legs"][-1]["origin"] = "FUK"
        open_jaw = item(open_jaw_record)
        snapshot = build_snapshot(
            run_result(deals=(round_trip, open_jaw)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        shapes = {
            (
                value["destination_route_shape"]["arrival_airport"],
                value["destination_route_shape"]["departure_airport"],
            )
            for value in snapshot["opportunities"]
        }
        self.assertEqual(shapes, {("KIX", "KIX"), ("KIX", "FUK")})

    def test_only_explicit_absolute_low_signal_is_promoted(self):
        generic = item(
            record("generic-signal", price=4300),
            classification="Signal",
            state="exact_revalidated_candidate",
        )
        absolute = item(
            record("absolute-low", price=4200),
            classification="Signal",
            state="ftr_absolute_low_non_deal",
        )
        snapshot = build_snapshot(
            run_result(signals=(generic, absolute)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(snapshot["candidate_counts"]["variants"], 1)
        self.assertEqual(snapshot["candidate_counts"]["absolute_low_non_deals"], 1)
        self.assertEqual(
            snapshot["opportunities"][0]["variants"][0]["variant_id"],
            "absolute-low",
        )

    def test_degraded_run_is_truthfully_consumable_but_provider_failed_is_not(self):
        degraded = build_snapshot(
            run_result(deals=(item(record("deal")),), health="degraded"),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(degraded["coverage_state"], "degraded")
        self.assertEqual(degraded["freshness_state"], "degraded")
        with self.assertRaisesRegex(FTRHandoffError, "not consumable"):
            build_snapshot(
                run_result(deals=(item(record("deal")),), health="provider_failed"),
                producer_commit_sha="abc123",
                generated_at="2026-08-19T08:05:00+08:00",
            )

    def test_stage_writes_snapshot_before_manifest_and_scoped_never_moves_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            canonical = build_snapshot(
                run_result(deals=(item(record("canonical")),)),
                producer_commit_sha="abc123",
                generated_at="2026-08-19T08:05:00+08:00",
            )
            staged = stage_snapshot(history_dir=history, snapshot=canonical)
            self.assertEqual(staged["manifest_path"], CANONICAL_LATEST_PATH)
            self.assertTrue((history / staged["snapshot_path"]).exists())
            self.assertTrue((history / CANONICAL_LATEST_PATH).exists())
            latest_before = (history / CANONICAL_LATEST_PATH).read_bytes()
            loaded = load_manifest_snapshot(history_dir=history)
            self.assertEqual(loaded["run_id"], canonical["run_id"])

            scoped_run = dict(run_result(deals=(item(record("scoped")),)))
            scoped_run["radar_run_id"] = "ftr-scoped-20260819T090000+0800"
            scoped_run["run_at"] = "2026-08-19T09:00:00+08:00"
            scoped = build_snapshot(
                scoped_run,
                producer_commit_sha="def456",
                mode="scoped_search",
                generated_at="2026-08-19T09:05:00+08:00",
            )
            scoped_staged = stage_snapshot(history_dir=history, snapshot=scoped)
            self.assertNotEqual(scoped_staged["manifest_path"], CANONICAL_LATEST_PATH)
            self.assertEqual((history / CANONICAL_LATEST_PATH).read_bytes(), latest_before)
            self.assertEqual(
                scoped_staged["manifest_path"],
                manifest_repository_path(scoped),
            )

    def test_consumer_fails_closed_on_checksum_or_unknown_major(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            snapshot = build_snapshot(
                run_result(deals=(item(record("deal")),)),
                producer_commit_sha="abc123",
                generated_at="2026-08-19T08:05:00+08:00",
            )
            staged = stage_snapshot(history_dir=history, snapshot=snapshot)
            snapshot_file = history / staged["snapshot_path"]
            payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
            payload["candidate_counts"]["variants"] = 999
            snapshot_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(FTRHandoffError, "checksum mismatch"):
                load_manifest_snapshot(history_dir=history)

            unsupported = dict(snapshot)
            unsupported["schema_version"] = "2.0"
            with self.assertRaisesRegex(FTRHandoffError, "unsupported schema major"):
                validate_snapshot(unsupported)

    def test_snapshot_path_is_immutable_run_scoped(self):
        snapshot = build_snapshot(
            run_result(deals=(item(record("deal")),)),
            producer_commit_sha="abc123",
            generated_at="2026-08-19T08:05:00+08:00",
        )
        self.assertEqual(
            snapshot_repository_path(snapshot),
            "data/ftr-feed/2026/08/19/production-radar-20260819T080000-0800.json",
        )


if __name__ == "__main__":
    unittest.main()
