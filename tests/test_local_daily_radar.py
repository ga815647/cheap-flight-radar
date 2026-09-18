import fcntl
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "local_daily_radar", ROOT / "scripts" / "local_daily_radar.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class LocalRunnerPolicyTest(unittest.TestCase):
    def test_local_runtime_ssot_matches_runner(self):
        policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        orchestration = policy["publication"]["orchestration"]
        self.assertEqual(orchestration["primary_scheduler"], "openchamber_scheduled_local_run")
        local = orchestration["local_runtime"]
        self.assertEqual(local["runner"], "scripts/local_daily_radar.py")
        self.assertTrue((ROOT / local["runner"]).exists())
        loop = (ROOT / ".agents" / "loops" / "daily-radar.md").read_text(encoding="utf-8")
        self.assertIn("scripts/local_daily_radar.py", loop)
        self.assertNotIn("ops/radar-request", loop)
        self.assertNotIn("workflow_dispatch", loop)

    def test_production_github_workflows_are_retired(self):
        remaining = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual([path.name for path in remaining], ["ci.yml"])


class LocalRunnerBehaviorTest(unittest.TestCase):
    def test_stale_or_future_date_is_refused_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = RUNNER.main(["--local-root", tmp, "--date", "2099-01-01"])
            self.assertEqual(code, 1)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_overlapping_run_exits_without_touching_state(self):
        today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "locks").mkdir(parents=True)
            with (root / "locks" / "daily.lock").open("w") as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                code = RUNNER.main(["--local-root", tmp, "--date", today])
                self.assertEqual(code, 2)
            self.assertFalse((root / "history").exists())

    def test_blocked_prior_claim_fails_closed_without_provider_calls(self):
        today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
        year, month, day = today.split("-")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claim = root / "history" / "data" / "production-attempts" / year / month / day / "canonical.json"
            claim.parent.mkdir(parents=True)
            claim.write_text(json.dumps({
                "schema_version": 1,
                "requested_date": today,
                "claimed_at": f"{today}T00:00:00+08:00",
                "workflow_run_id": "fixture",
                "workflow_run_url": "file:///fixture",
                "trigger_sha": "fixture",
                "semantics": "one_canonical_live_acquisition_attempt_per_asia_taipei_day",
            }) + "\n", encoding="utf-8")
            code = RUNNER.main(["--local-root", tmp, "--date", today])
            self.assertEqual(code, 1)
            self.assertFalse((root / "history" / "data" / "price-history").exists())


if __name__ == "__main__":
    unittest.main()
