from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from cheap_flight_radar.airfare import AirfareLeg, AirfareRecord, AirportIdentity
from cheap_flight_radar.price_history import FareObservation, build_snapshot, snapshot_repository_path, snapshot_to_json
from cheap_flight_radar.production_publication import build_site

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "flight-radar.yaml"
LEGACY_FIXTURES = ROOT / "tests" / "fixtures" / "publication"


class ProductionPublicationTests(unittest.TestCase):
    def _write_v2(self, root: Path):
        history, manifests, site = root / "history", root / "manifests", root / "site"
        run_at = datetime.fromisoformat("2026-08-13T02:00:00+08:00")
        run_id = "production-radar-v2-test"
        observation = FareObservation(
            observation_id="v2-tpe-nrt", radar_run_id=run_id, observed_at=run_at.isoformat(), origin="TPE", destination="NRT",
            departure_date="2026-09-10", trip_type="round_trip", normalized_twd_price=6900,
            fare_scope="usable_complete_trip", availability_state="available", source_id="gflights_google_exact",
            source_url="https://example.invalid/book", verification_state="revalidated", original_price=6900, original_currency="TWD",
        )
        snapshot = build_snapshot(run_id, run_at, [observation])
        relative = Path(snapshot_repository_path(snapshot))
        target = history / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(snapshot_to_json(snapshot), encoding="utf-8")
        discovery = AirfareRecord(
            record_id="deal-tpe-nrt", provider="gflights", surface="flight_deals", origin=AirportIdentity("TPE"),
            destination=AirportIdentity("NRT", city="Tokyo", country="Japan"),
            legs=(AirfareLeg("TPE", "NRT", "2026-09-10"), AirfareLeg("NRT", "TPE", "2026-09-14")),
            current_price_twd=6500, typical_price_twd=10000, discount_percent=35, anomaly_authority="google_flight_deals",
            observed_at=run_at.isoformat(), verification_state="discovery", evidence_class="qualified_round_trip_deal",
            complete_airfare=True, airlines=("Tigerair Taiwan",), reproducible_search={"origin": "TPE", "currency": "TWD"},
        )
        exact = AirfareRecord(
            record_id="exact-tpe-nrt", provider="gflights", surface="exact", origin=AirportIdentity("TPE"), destination=AirportIdentity("NRT"),
            legs=(AirfareLeg("TPE", "NRT", "2026-09-10", "06:35", "10:45"),), current_price_twd=6900,
            observed_at=run_at.isoformat(), verification_state="revalidated", evidence_class="exact_revalidated_candidate",
            complete_airfare=True, airlines=("Tigerair Taiwan",), booking_url="https://example.invalid/book", booking_token="token",
            reproducible_search={"origin": "TPE", "destination": "NRT", "return_date": "2026-09-14", "currency": "TWD"},
        )
        item = {
            "classification": "Deal", "state": "deal", "reason": "qualified anomaly authority plus current exact complete airfare",
            "observation_id": observation.observation_id, "anomaly_source": "google_flight_deals", "anomaly_strength_percent": 31.0,
            "anomaly_baseline_twd": 10000, "anomaly_scope": "destination_airport_all_taiwan_origins",
            "current_complete_airfare_twd": 6900, "discovery": asdict(discovery), "exact": asdict(exact),
        }
        manifest = {
            "schema_version": 2, "radar_run_id": run_id, "run_at": run_at.isoformat(), "history_snapshot_path": relative.as_posix(),
            "deals": [item], "signals": [{**item, "classification": "Signal", "state": "weak_seed", "reason": "fixture weak signal"}],
            "coverage": {
                "origins": {origin: {"status": "attempted", "returned_flight_deals": 1, "qualified_deals": 1} for origin in ("TPE", "TSA", "RMQ", "KHH")},
                "markets": {
                    "japan": {"discovered": 1, "deals": 1}, "korea": {"discovered": 0, "deals": 0},
                    "china": {"discovered": 0, "deals": 0}, "other_asia_oceania": {"discovered": 0, "deals": 0},
                },
            },
            "provider_failures": [],
        }
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / f"{run_id}.json").write_text(json.dumps(manifest), encoding="utf-8")
        return history, manifests, site, run_id

    def test_v2_renders_deals_and_signals_as_primary_without_history_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            history, manifests, site, run_id = self._write_v2(Path(tmp))
            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifests, site_dir=site)
            text = (site / "runs" / run_id / "index.html").read_text(encoding="utf-8")
            self.assertIn("<h2>Deals</h2>", text)
            self.assertIn("<h2>Signals &amp; airfare alternatives</h2>", text)
            self.assertIn("31.0% below baseline", text)
            self.assertIn("Destination baseline", text)
            self.assertIn("TWD 6,900", text)
            self.assertIn("google_flight_deals", text)
            self.assertIn("sparse history cannot block a Deal", text)
            self.assertNotIn('class="view-label">Absolute Cheapest', text)
            self.assertNotIn("Best Value", text)

    def test_wrapper_still_renders_legacy_schema_v1_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history, manifests, site, run_id = self._write_v2(root)
            legacy_snapshot = history / "data" / "price-history" / "2026" / "08" / "12" / "corrected-radar-v1-20260812T125139-0800.json"
            legacy_snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(LEGACY_FIXTURES / "corrected-radar-v1-snapshot.json", legacy_snapshot)
            shutil.copyfile(LEGACY_FIXTURES / "corrected-radar-v1-manifest.json", manifests / "corrected-radar-v1-20260812T125139-0800.json")
            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifests, site_dir=site)
            legacy_text = (site / "runs" / "corrected-radar-v1-20260812T125139-0800" / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="view-label">Absolute Cheapest', legacy_text)
            self.assertNotIn("Best Value", legacy_text)
            self.assertEqual((site / "latest" / "index.html").read_bytes(), (site / "runs" / run_id / "index.html").read_bytes())


if __name__ == "__main__":
    unittest.main()
