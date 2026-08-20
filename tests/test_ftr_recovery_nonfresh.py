from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cheap_flight_radar.ftr_handoff import CANONICAL_LATEST_PATH, load_current_status
from ftr_recovery_fixtures import RecoveryFixtureMixin


class FTRRecoveryNonFreshTest(RecoveryFixtureMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.history, self.output = root / "history", root / "output"
        self.history.mkdir()
        self.output.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_fresh_recovery_cannot_advance_latest_or_clear(self):
        self.activate_repair()
        prior_latest = (self.history / CANONICAL_LATEST_PATH).read_bytes()
        self.claim()
        staged = self.stage_cfr()

        from cheap_flight_radar import ftr_recovery as module
        real_build = module.build_snapshot

        def non_fresh(*args, **kwargs):
            snapshot = real_build(*args, **kwargs)
            snapshot["freshness_state"] = "degraded"
            return snapshot

        with mock.patch("cheap_flight_radar.ftr_recovery.build_snapshot", side_effect=non_fresh):
            result = self.stage_ftr(staged)

        self.assertEqual(result["status"], "failed")
        self.assertIn("complete and fresh", result["failure_reason"])
        self.assertEqual((self.history / CANONICAL_LATEST_PATH).read_bytes(), prior_latest)
        status = load_current_status(history_dir=self.history)
        self.assertTrue(status["repair_required"])
        self.assertEqual(status["repair_incident"]["latest_failed_attempt"]["mode"], "same_day_recovery")


if __name__ == "__main__":
    unittest.main()
