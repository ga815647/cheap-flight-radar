from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cheap_flight_radar.ftr_handoff import CANONICAL_LATEST_PATH, FTRHandoffError, load_current_status, load_manifest_snapshot
from cheap_flight_radar.ftr_recovery import recovery_run_prefix
from ftr_recovery_fixtures import (
    APP_SHA, DAY, REQUEST_ID, RecoveryFixtureMixin,
    execution_row, healthy_execution, healthy_origins, run_result,
)


class FTRRecoveryTransactionTest(RecoveryFixtureMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.history, self.output = root / "history", root / "output"
        self.history.mkdir(); self.output.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def test_healthy_recovery_advances_exact_latest_and_clears_chronology(self):
        baseline, _ = self.activate_repair()
        trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
        self.claim(); staged = self.stage_cfr(); result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "success")
        latest = load_manifest_snapshot(history_dir=self.history)
        self.assertEqual((latest["run_id"], latest["mode"], latest["producer_commit_sha"]),
                         (result["radar_run_id"], "same_day_recovery", APP_SHA))
        status = load_current_status(history_dir=self.history)
        self.assertFalse(status["repair_required"])
        self.assertEqual(status["current_freshness_state"], "fresh")
        self.assertEqual(status["last_good"]["run_id"], result["radar_run_id"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)
        self.assertEqual(status["repair_incident"]["cleared_by"]["snapshot_sha256"], result["snapshot_sha256"])
        self.assertNotEqual(status["last_good"]["run_id"], baseline["radar_run_id"])
        self.assertTrue((self.history / result["transition_evidence_ref"]).exists())

    def test_healthy_recovery_can_create_first_latest_without_last_good(self):
        self.activate_repair(with_last_good=False)
        self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
        self.claim(); result = self.stage_ftr(self.stage_cfr())
        self.assertEqual(result["status"], "success")
        self.assertTrue((self.history / CANONICAL_LATEST_PATH).exists())
        self.assertEqual(load_current_status(history_dir=self.history)["last_good"]["run_id"], result["radar_run_id"])

    def _failed_health_payloads(self):
        degraded = healthy_origins(); degraded["RMQ"] = {
            "status": "degraded", "returned_flight_deals": 0, "explore_seeds": 1, "errors": ["fixture"]}
        yield run_result(f"{recovery_run_prefix(REQUEST_ID)}degraded", mode="same_day_recovery",
                         health="degraded", origins=degraded)
        failed_origins = {a: {"status": "failed", "returned_flight_deals": 0,
                              "explore_seeds": 0, "errors": ["failed"]}
                          for a in ("TPE", "TSA", "RMQ", "KHH")}
        failed_exec = healthy_execution()
        failed_exec["flight_deals"] = execution_row(4, 0, 0, 4)
        failed_exec["explore"] = execution_row(4, 0, 0, 4)
        payload = run_result(f"{recovery_run_prefix(REQUEST_ID)}provider-failed", mode="same_day_recovery",
                             health="provider_failed", origins=failed_origins, execution=failed_exec)
        payload["provider_failures"] = [{"provider": "gflights", "surface": "flight_deals", "error": "fixture"}]
        yield payload

    def test_degraded_incomplete_or_provider_failed_never_advance_or_clear(self):
        for index, payload in enumerate(self._failed_health_payloads()):
            with self.subTest(index=index):
                root = Path(self.tmp.name) / f"health-{index}"; root.mkdir()
                old_history, old_output = self.history, self.output
                self.history, self.output = root / "history", root / "output"; self.history.mkdir(); self.output.mkdir()
                try:
                    baseline, _ = self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
                    trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
                    self.claim(); result = self.stage_ftr(self.stage_cfr(payload=payload))
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)
                    status = load_current_status(history_dir=self.history)
                    self.assertTrue(status["repair_required"])
                    self.assertEqual(status["last_good"]["run_id"], baseline["radar_run_id"])
                    self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)
                    self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["mode"], "same_day_recovery")
                finally:
                    self.history, self.output = old_history, old_output

    def test_immutable_snapshot_collision_with_different_bytes_fails_closed(self):
        self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        self.claim(); staged = self.stage_cfr(); safe_run_id = staged["radar_run_id"].replace("+", "-")
        collision = self.history / f"data/ftr-feed/2026/08/20/{safe_run_id}.json"
        collision.parent.mkdir(parents=True, exist_ok=True); collision.write_bytes(b"different\n")
        result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)
        self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])

    def test_checksum_mismatch_restores_prior_latest(self):
        self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        self.claim(); staged = self.stage_cfr()
        from cheap_flight_radar import ftr_recovery as module
        real = module.stage_snapshot
        def bad(*args, **kwargs):
            value = dict(real(*args, **kwargs)); value["snapshot_sha256"] = "0" * 64; return value
        with mock.patch("cheap_flight_radar.ftr_recovery.stage_snapshot", side_effect=bad):
            result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertIn("checksum", result["failure_reason"])
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)

    def test_reload_run_mode_or_application_sha_mismatch_restores_first_latest_absence(self):
        for field, bad in (("run_id", "wrong"), ("mode", "canonical_daily"), ("producer_commit_sha", "c" * 40)):
            with self.subTest(field=field):
                root = Path(self.tmp.name) / f"reload-{field}"; root.mkdir()
                old_history, old_output = self.history, self.output
                self.history, self.output = root / "history", root / "output"; self.history.mkdir(); self.output.mkdir()
                try:
                    self.activate_repair(with_last_good=False); self.claim(); staged = self.stage_cfr()
                    from cheap_flight_radar import ftr_recovery as module
                    real = module.load_manifest_snapshot
                    def corrupted(*args, **kwargs):
                        value = dict(real(*args, **kwargs)); value[field] = bad; return value
                    with mock.patch("cheap_flight_radar.ftr_recovery.load_manifest_snapshot", side_effect=corrupted):
                        result = self.stage_ftr(staged)
                    self.assertEqual(result["status"], "failed")
                    self.assertFalse((self.history / CANONICAL_LATEST_PATH).exists())
                    self.assertTrue(load_current_status(history_dir=self.history)["repair_required"])
                finally:
                    self.history, self.output = old_history, old_output

    def test_post_latest_clear_failure_restores_prior_latest_and_status(self):
        self.activate_repair(); before = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        trigger = dict(load_current_status(history_dir=self.history)["repair_incident"]["trigger_attempt"])
        self.claim(); staged = self.stage_cfr()
        with mock.patch("cheap_flight_radar.ftr_recovery.clear_repair_required",
                        side_effect=FTRHandoffError("fixture post-latest clear failure")):
            result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), before)
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["repair_incident"]["trigger_attempt"], trigger)

    def test_legitimate_durable_cfr_recovery_evidence_survives_later_ftr_failure(self):
        self.activate_repair(); self.claim(); staged = self.stage_cfr()
        keys = ("history_snapshot_path", "run_result_path", "recovery_manifest_path", "recovery_acquisition_path")
        paths = [self.history / staged[key] for key in keys]; before = {p: p.read_bytes() for p in paths}
        with mock.patch("cheap_flight_radar.ftr_recovery.clear_repair_required", side_effect=FTRHandoffError("fixture")):
            result = self.stage_ftr(staged)
        self.assertEqual(result["status"], "failed")
        for path, content in before.items(): self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__": unittest.main()
