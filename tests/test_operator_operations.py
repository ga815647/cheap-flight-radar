from pathlib import Path
import json
import tempfile
import unittest

from cheap_flight_radar.operator_operations import (
    inspect_operator_state,
    operator_claim_repository_path,
    restore_operator_publication_manifest,
    stage_operator_success_evidence,
    write_operator_claim,
)
from cheap_flight_radar.production_operations import inspect_daily_state
from cheap_flight_radar.production_runtime import retag_run_artifacts


class OperatorOperationsTest(unittest.TestCase):
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
        self.request_id = "provider-health-20260815"

    def tearDown(self):
        self.tmp.cleanup()

    def claim(self):
        return write_operator_claim(
            history_dir=self.history, requested_date=self.day, request_id=self.request_id,
            claimed_at="2026-08-15T10:00:00+08:00", workflow_run_id="456",
            workflow_run_url="https://github.example/run/456", trigger_sha="def",
        )

    def write_operator_output(self):
        run_id = f"operator-radar-{self.request_id}-20260815T100100+0800"
        safe_id = run_id.replace("+", "-")
        history_rel = f"data/price-history/2026/08/15/{safe_id}.json"
        snapshot_path = self.output / "history" / history_rel
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(json.dumps({"schema_version": 1, "radar_run_id": run_id, "run_at": "2026-08-15T10:01:00+08:00", "observations": []}) + "\n", encoding="utf-8")
        manifest_path = self.output / "publication" / "runs" / f"{run_id}.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps({"schema_version": 2, "radar_run_id": run_id, "run_at": "2026-08-15T10:01:00+08:00", "history_snapshot_path": history_rel, "execution_mode": "operator_requested_reacquisition", "deals": [], "signals": [], "coverage": {}, "provider_failures": []}) + "\n", encoding="utf-8")
        (self.output / "run-result.json").write_text(json.dumps({"radar_run_id": run_id, "run_at": "2026-08-15T10:01:00+08:00", "execution_mode": "operator_requested_reacquisition", "deal_count": 0, "signal_count": 0, "deals": [], "signals": [], "coverage": {}, "provider_failures": []}) + "\n", encoding="utf-8")
        return run_id, history_rel

    def test_operator_request_is_separate_from_canonical_daily_guard(self):
        self.claim()
        self.write_operator_output()
        stage_operator_success_evidence(output_dir=self.output, history_dir=self.history, requested_date=self.day, request_id=self.request_id)
        canonical = inspect_daily_state(history_dir=self.history, publication_dir=self.publication, requested_date=self.day)
        self.assertEqual(canonical.status, "acquire")

    def test_duplicate_operator_request_id_never_reacquires(self):
        self.claim()
        state = inspect_operator_state(history_dir=self.history, publication_dir=self.publication, requested_date=self.day, request_id=self.request_id)
        self.assertEqual(state.status, "blocked_prior_operator_attempt")
        self.assertTrue((self.history / operator_claim_repository_path(self.day, self.request_id)).exists())

    def test_operator_success_recovers_and_publishes(self):
        self.claim()
        run_id, history_rel = self.write_operator_output()
        staged = stage_operator_success_evidence(output_dir=self.output, history_dir=self.history, requested_date=self.day, request_id=self.request_id)
        self.assertEqual(staged["radar_run_id"], run_id)
        self.assertTrue((self.history / history_rel).exists())
        state = inspect_operator_state(history_dir=self.history, publication_dir=self.publication, requested_date=self.day, request_id=self.request_id)
        self.assertEqual(state.status, "recover_publication")
        restored = restore_operator_publication_manifest(history_dir=self.history, publication_dir=self.publication, requested_date=self.day, request_id=self.request_id)
        self.assertEqual(restored["status"], "staged")
        published = inspect_operator_state(history_dir=self.history, publication_dir=self.publication, requested_date=self.day, request_id=self.request_id)
        self.assertEqual(published.status, "published")

    def test_retag_run_artifacts_moves_out_of_canonical_namespace(self):
        old_id = "production-radar-20260815T100100+0800"
        old_safe = old_id.replace("+", "-")
        history_rel = f"data/price-history/2026/08/15/{old_safe}.json"
        snapshot_path = self.output / "history" / history_rel
        snapshot_path.parent.mkdir(parents=True)
        snapshot_path.write_text(json.dumps({"schema_version": 1, "radar_run_id": old_id, "run_at": "2026-08-15T10:01:00+08:00", "observations": []}) + "\n", encoding="utf-8")
        manifest_path = self.output / "publication" / "runs" / f"{old_id}.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps({"radar_run_id": old_id, "history_snapshot_path": history_rel, "deals": [], "signals": []}) + "\n", encoding="utf-8")
        result_path = self.output / "run-result.json"
        result_path.write_text(json.dumps({"radar_run_id": old_id, "run_at": "2026-08-15T10:01:00+08:00", "deal_count": 0, "signal_count": 0, "signal_states": {}, "coverage": {}, "provider_failures": []}) + "\n", encoding="utf-8")
        paths = retag_run_artifacts(output_dir=self.output, paths={"history_snapshot": snapshot_path.as_posix(), "publication_manifest": manifest_path.as_posix(), "run_result": result_path.as_posix()}, run_id_prefix="operator-radar-health-check", execution_mode="operator_requested_reacquisition")
        result = json.loads(Path(paths["run_result"]).read_text(encoding="utf-8"))
        manifest = json.loads(Path(paths["publication_manifest"]).read_text(encoding="utf-8"))
        snapshot = json.loads(Path(paths["history_snapshot"]).read_text(encoding="utf-8"))
        self.assertTrue(result["radar_run_id"].startswith("operator-radar-health-check-"))
        self.assertEqual(result["execution_mode"], "operator_requested_reacquisition")
        self.assertEqual(manifest["execution_mode"], "operator_requested_reacquisition")
        self.assertEqual(snapshot["radar_run_id"], result["radar_run_id"])
        self.assertFalse(snapshot_path.exists())

    def test_operator_workflow_is_explicit_and_unscheduled(self):
        workflow = Path(".github/workflows/operator-production-radar.yml").read_text(encoding="utf-8")
        canonical = Path(".github/workflows/canonical-production-radar.yml").read_text(encoding="utf-8")
        self.assertIn("ops/radar-operator-request", workflow)
        self.assertIn("operator_reacquisition", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("group: production-radar-acquisition", workflow)
        self.assertIn("group: production-radar-acquisition", canonical)


if __name__ == "__main__":
    unittest.main()
