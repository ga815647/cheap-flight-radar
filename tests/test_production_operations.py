import json
from pathlib import Path
import tempfile
import unittest

from cheap_flight_radar.production_operations import (
    claim_repository_path,
    inspect_daily_state,
    restore_publication_manifest,
    stage_success_evidence,
    write_daily_claim,
)


class ProductionOperationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.history = root / "history"
        self.publication = root / "publication"
        self.output = root / "output"
        self.history.mkdir()
        self.publication.mkdir()
        self.output.mkdir()
        self.day = "2026-08-15"

    def tearDown(self):
        self.tmp.cleanup()

    def claim(self):
        return write_daily_claim(
            history_dir=self.history,
            requested_date=self.day,
            claimed_at="2026-08-15T08:00:00+08:00",
            workflow_run_id="123",
            workflow_run_url="https://github.example/run/123",
            trigger_sha="abc",
        )

    def write_runtime_output(self, run_id="production-radar-20260815T080100+0800"):
        history_rel = f"data/price-history/2026/08/15/{run_id}.json"
        snapshot = {
            "schema_version": 1,
            "radar_run_id": run_id,
            "run_at": "2026-08-15T08:01:00+08:00",
            "observations": [],
        }
        snapshot_path = self.output / "history" / history_rel
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")

        manifest = {
            "schema_version": 2,
            "radar_run_id": run_id,
            "run_at": "2026-08-15T08:01:00+08:00",
            "history_snapshot_path": history_rel,
            "deals": [],
            "signals": [],
            "coverage": {},
            "provider_failures": [],
        }
        manifest_path = self.output / "publication" / "runs" / f"{run_id}.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

        result = {
            "radar_run_id": run_id,
            "run_at": "2026-08-15T08:01:00+08:00",
            "deal_count": 0,
            "signal_count": 0,
            "deals": [],
            "signals": [],
            "coverage": {},
            "provider_failures": [],
        }
        (self.output / "run-result.json").write_text(
            json.dumps(result) + "\n", encoding="utf-8"
        )
        return run_id, history_rel

    def test_fresh_day_can_acquire(self):
        state = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(state.status, "acquire")

    def test_claim_blocks_second_acquisition_after_failure(self):
        self.claim()
        state = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(state.status, "blocked_prior_acquisition_attempt")
        self.assertTrue((self.history / claim_repository_path(self.day)).exists())

    def test_success_stages_recovery_then_restores_publication(self):
        self.claim()
        run_id, history_rel = self.write_runtime_output()
        staged = stage_success_evidence(
            output_dir=self.output,
            history_dir=self.history,
            requested_date=self.day,
        )
        self.assertEqual(staged["radar_run_id"], run_id)
        self.assertTrue((self.history / history_rel).exists())

        state = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(state.status, "recover_publication")

        restored = restore_publication_manifest(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(restored["status"], "staged")
        self.assertTrue(
            (self.publication / "publication" / "runs" / f"{run_id}.json").exists()
        )

        published = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(published.status, "published")

    def test_stage_success_requires_matching_local_day(self):
        self.claim()
        self.write_runtime_output()
        result_path = self.output / "run-result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["run_at"] = "2026-08-16T00:01:00+08:00"
        result_path.write_text(json.dumps(result) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match request"):
            stage_success_evidence(
                output_dir=self.output,
                history_dir=self.history,
                requested_date=self.day,
            )

    def test_active_publication_without_recovery_evidence_fails_closed(self):
        run_id, history_rel = self.write_runtime_output()
        snapshot_source = self.output / "history" / history_rel
        snapshot_target = self.history / history_rel
        snapshot_target.parent.mkdir(parents=True)
        snapshot_target.write_bytes(snapshot_source.read_bytes())

        manifest_source = self.output / "publication" / "runs" / f"{run_id}.json"
        active = self.publication / "publication" / "runs" / f"{run_id}.json"
        active.parent.mkdir(parents=True)
        active.write_bytes(manifest_source.read_bytes())

        state = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(state.status, "blocked_missing_recovery_evidence")

    def test_manifest_divergence_fails_closed(self):
        self.claim()
        run_id, _ = self.write_runtime_output()
        stage_success_evidence(
            output_dir=self.output,
            history_dir=self.history,
            requested_date=self.day,
        )
        active = self.publication / "publication" / "runs" / f"{run_id}.json"
        active.parent.mkdir(parents=True)
        active.write_text('{"different": true}\n', encoding="utf-8")
        state = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(state.status, "blocked_manifest_divergence")

    def test_multiple_canonical_snapshots_block(self):
        base = self.history / "data" / "price-history" / "2026" / "08" / "15"
        base.mkdir(parents=True)
        for idx in (1, 2):
            (base / f"production-radar-{idx}.json").write_text(
                json.dumps({"radar_run_id": f"production-radar-{idx}"}),
                encoding="utf-8",
            )
        state = inspect_daily_state(
            history_dir=self.history,
            publication_dir=self.publication,
            requested_date=self.day,
        )
        self.assertEqual(state.status, "blocked_multiple_canonical_snapshots")


if __name__ == "__main__":
    unittest.main()
