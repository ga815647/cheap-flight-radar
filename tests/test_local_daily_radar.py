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
    def test_github_trigger_ssot_matches_restored_workflows(self):
        policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        orchestration = policy["publication"]["orchestration"]
        self.assertEqual(orchestration["primary_scheduler"], "chatgpt_scheduled_radar_run")
        control = orchestration["canonical_daily_control"]
        self.assertEqual(control["branch"], "ops/radar-request")
        self.assertEqual(control["request_path"], "requests/daily.json")
        self.assertEqual(control["request_mode"], "canonical_daily")
        self.assertFalse((ROOT / ".agents" / "loops" / "daily-radar.md").exists())

    def test_production_github_workflows_are_present(self):
        remaining = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(
            [path.name for path in remaining],
            [
                "canonical-production-radar-test.yml",
                "canonical-production-radar.yml",
                "ci.yml",
                "operator-production-radar.yml",
                "radar-pages-isolated-test.yml",
                "radar-pages.yml",
            ],
        )

    def test_unattended_permissions_and_prompt_guards(self):
        import json as jsonlib

        config = jsonlib.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
        bash_rules = config["permission"]["bash"]
        self.assertEqual(
            bash_rules.get("python3 scripts/local_daily_radar.py*"), "allow"
        )
        external = config["permission"]["external_directory"]
        self.assertIn("cheap-flight-radar", jsonlib.dumps(external))
        runner_text = (ROOT / "scripts" / "local_daily_radar.py").read_text(encoding="utf-8")
        self.assertIn('"--execution-mode", "operator_requested_reacquisition"', runner_text)


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
