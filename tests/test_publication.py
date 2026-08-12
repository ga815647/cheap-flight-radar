from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from cheap_flight_radar.price_history import (
    FareObservation,
    build_snapshot,
    snapshot_repository_path,
    snapshot_to_json,
)
from cheap_flight_radar.publication import build_site


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "publication"
POLICY = ROOT / "flight-radar.yaml"


def _write_snapshot(history_dir: Path, snapshot) -> Path:
    path = history_dir / snapshot_repository_path(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot_to_json(snapshot), encoding="utf-8")
    return path


def _minimal_manifest(run_id: str, run_at: str, snapshot_path: str, observation_id: str) -> dict:
    return {
        "schema_version": 1,
        "radar_run_id": run_id,
        "run_at": run_at,
        "history_snapshot_path": snapshot_path,
        "sections": {
            "best_short_break": observation_id,
            "unusual_long_haul_deal": None,
        },
        "markets": {"japan": [], "korea": [observation_id], "china": [], "world": []},
        "candidate_details": {observation_id: {"return_date": "2026-09-22"}},
        "failed_seeds": [],
        "coverage": {
            "origins": {"TPE": "attempted", "TSA": "attempted", "RMQ": "attempted", "KHH": "attempted"},
            "fixed_watch": {"status": "complete", "sources": []},
            "china": {"status": "not_activated", "modes": {}},
        },
    }


class PublicationPolicyTests(unittest.TestCase):
    def test_best_value_is_not_user_facing(self) -> None:
        policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        self.assertNotIn("best_value", policy["ranking"]["preserve_views"])
        self.assertEqual(
            policy["ranking"]["composite_score"]["role"],
            "internal_candidate_ordering_heuristic",
        )
        self.assertFalse(policy["ranking"]["composite_score"]["publish_winner"])
        self.assertEqual(policy["publication"]["platform"], "github_pages")
        self.assertFalse(policy["publication"]["orchestration"]["independent_github_cron"])


class PublicationGeneratorTests(unittest.TestCase):
    def _build_corrected_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        history = root / "history"
        manifest_dir = root / "manifests"
        site = root / "site"
        snapshot_target = history / "data" / "price-history" / "2026" / "08" / "12" / "corrected-radar-v1-20260812T125139-0800.json"
        snapshot_target.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "corrected-radar-v1-snapshot.json", snapshot_target)
        manifest_dir.mkdir(parents=True)
        shutil.copyfile(
            FIXTURES / "corrected-radar-v1-manifest.json",
            manifest_dir / "corrected-radar-v1-20260812T125139-0800.json",
        )
        build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifest_dir, site_dir=site)
        return history, manifest_dir, site

    def test_corrected_fixture_renders_required_views_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, _, site = self._build_corrected_fixture(Path(tmp))
            run_page = next((site / "runs").glob("*/index.html"))
            text = run_page.read_text(encoding="utf-8")
            for heading in (
                "Absolute Cheapest",
                "Near-Term Cheapest",
                "Best Short Break",
                "Unusual Long-Haul Deal",
                "Japan Notable Candidates",
                "Korea Notable Candidates",
                "China Notable Candidates",
                "World Notable Candidates",
                "Failed / Non-converged Cheap Seeds",
                "Coverage &amp; Freshness",
            ):
                self.assertIn(heading, text)
            self.assertNotIn("Best Value", text)
            self.assertIn("TWD 4,588", text)
            self.assertIn("due_not_refreshed", text)
            self.assertIn("China-mode coverage: partial", text)
            self.assertNotIn("Historical percentile:", text)
            self.assertEqual((site / "latest" / "index.html").read_bytes(), run_page.read_bytes())

    def test_future_history_does_not_change_old_run_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history, manifest_dir, site = self._build_corrected_fixture(root)
            run_page = next((site / "runs").glob("*/index.html"))
            before = run_page.read_bytes()

            future_time = datetime.fromisoformat("2026-08-13T12:51:39+08:00")
            future_id = "future-run-20260813"
            future = FareObservation(
                observation_id="future-tpe-pus",
                radar_run_id=future_id,
                observed_at=future_time.isoformat(),
                origin="TPE",
                destination="PUS",
                departure_date="2026-09-20",
                trip_type="round_trip",
                normalized_twd_price=1000,
                fare_scope="usable_complete_trip",
                availability_state="available",
                source_id="test",
                source_url=None,
                verification_state="revalidated",
                original_price=1000,
                original_currency="TWD",
            )
            _write_snapshot(history, build_snapshot(future_id, future_time, [future]))
            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifest_dir, site_dir=site)
            after = next((site / "runs").glob("*/index.html")).read_bytes()
            self.assertEqual(before, after)

    def test_percentile_is_rendered_only_after_policy_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history"
            manifests = root / "manifests"
            site = root / "site"
            manifests.mkdir(parents=True)

            current_time = datetime.fromisoformat("2026-08-12T12:00:00+08:00")
            departure = "2026-09-20"
            for index in range(10):
                observed = current_time - timedelta(days=10 - index)
                run_id = f"prior-{index:02d}"
                observation = FareObservation(
                    observation_id=f"prior-observation-{index:02d}",
                    radar_run_id=run_id,
                    observed_at=observed.isoformat(),
                    origin="TPE",
                    destination="PUS",
                    departure_date=departure,
                    trip_type="round_trip",
                    normalized_twd_price=5000 + index * 100,
                    fare_scope="usable_complete_trip",
                    availability_state="available",
                    source_id="test",
                    source_url=None,
                    verification_state="revalidated",
                    original_price=5000 + index * 100,
                    original_currency="TWD",
                )
                _write_snapshot(history, build_snapshot(run_id, observed, [observation]))

            run_id = "current-threshold-test"
            current = FareObservation(
                observation_id="current-tpe-pus",
                radar_run_id=run_id,
                observed_at=current_time.isoformat(),
                origin="TPE",
                destination="PUS",
                departure_date=departure,
                trip_type="round_trip",
                normalized_twd_price=4500,
                fare_scope="usable_complete_trip",
                availability_state="available",
                source_id="test",
                source_url=None,
                verification_state="revalidated",
                original_price=4500,
                original_currency="TWD",
            )
            snapshot = build_snapshot(run_id, current_time, [current])
            snapshot_path = _write_snapshot(history, snapshot)
            relative = snapshot_path.relative_to(history).as_posix()
            manifest = _minimal_manifest(run_id, current_time.isoformat(), relative, current.observation_id)
            (manifests / "current.json").write_text(json.dumps(manifest), encoding="utf-8")

            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifests, site_dir=site)
            text = (site / "runs" / run_id / "index.html").read_text(encoding="utf-8")
            self.assertIn("Comparable samples: 10", text)
            self.assertIn("Historical percentile:", text)
            self.assertIn("Recent baseline:", text)


if __name__ == "__main__":
    unittest.main()
