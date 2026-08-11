from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.fixed_watch_state import (
    ManifestError,
    build_fixed_watch_artifact_state,
    main,
    parse_fixed_watch_manifest,
)
from cheap_flight_radar.public_intelligence import load_fixed_watch_registry


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "flight-radar.yaml"
UTC = timezone.utc


class FixedWatchArtifactStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.watches = load_fixed_watch_registry(POLICY_PATH)
        self.now = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)

    def manifest_payload(
        self,
        *,
        run_id="prior-run",
        china_completed="2026-08-11T08:30:00+00:00",
        ptt_completed="2026-08-11T08:31:00+00:00",
        ptt_status="success",
        china_observation_title="TPE-NRT fare",
    ):
        observations = [
            {
                "observation_id": f"obs-{run_id}-china",
                "source_id": "china_airlines_official",
                "source_url": "https://www.china-airlines.com/tw/zh/index.html",
                "item_url": "https://example.test/china-fare",
                "observed_at": china_completed,
                "title": china_observation_title,
                "carrier": "China Airlines",
                "sale_period": None,
                "travel_period": None,
                "route_set": [],
                "promo_code": None,
                "price_text": "TWD 10,848",
            }
        ]
        attempts = [
            {
                "attempt_id": f"attempt-{run_id}-china",
                "source_id": "china_airlines_official",
                "status": "success",
                "started_at": "2026-08-11T08:29:00+00:00",
                "completed_at": china_completed,
                "requested_url": "https://www.china-airlines.com/tw/zh/index.html",
                "final_url": "https://www.china-airlines.com/tw/zh/index.html",
                "http_status": 200,
                "error": None,
                "observation_count": 1,
            },
            {
                "attempt_id": f"attempt-{run_id}-ptt",
                "source_id": "ptt_japan_travel_info",
                "status": ptt_status,
                "started_at": "2026-08-11T05:29:00+00:00",
                "completed_at": ptt_completed,
                "requested_url": "https://www.ptt.cc/bbs/Japan_Travel/index.html",
                "final_url": "https://www.ptt.cc/bbs/Japan_Travel/index.html",
                "http_status": 200 if ptt_status == "success" else 503,
                "error": None if ptt_status == "success" else "HTTP 503",
                "observation_count": 0,
            },
        ]
        return {
            "run_id": run_id,
            "requested_at": "2026-08-11T05:28:00+00:00",
            "completed_at": max(china_completed, ptt_completed),
            "requested_watch_ids": ["china_airlines_official", "ptt_japan_travel_info"],
            "attempts": attempts,
            "observations": observations,
        }

    def test_legacy_v1_manifest_without_schema_version_reuses_fresh_successes(self):
        manifest = parse_fixed_watch_manifest(self.manifest_payload())
        state = build_fixed_watch_artifact_state(self.watches, (manifest,), self.now)
        self.assertEqual(state.due_watch_ids, ())
        self.assertEqual(
            {item.source_id: item.attempt_id for item in state.reused_successes},
            {
                "china_airlines_official": "attempt-prior-run-china",
                "ptt_japan_travel_info": "attempt-prior-run-ptt",
            },
        )
        self.assertEqual(
            tuple(item.title for item in state.normalized_observations),
            ("TPE-NRT fare",),
        )

    def test_new_failed_attempt_does_not_refresh_expired_success(self):
        old = self.manifest_payload(
            run_id="old",
            ptt_completed="2026-08-11T05:30:00+00:00",
        )
        recent_failure = self.manifest_payload(
            run_id="failure",
            ptt_completed="2026-08-11T08:55:00+00:00",
            ptt_status="fetch_failed",
        )
        recent_failure["attempts"] = [recent_failure["attempts"][1]]
        recent_failure["requested_watch_ids"] = ["ptt_japan_travel_info"]
        recent_failure["observations"] = []
        state = build_fixed_watch_artifact_state(
            self.watches,
            (
                parse_fixed_watch_manifest(old),
                parse_fixed_watch_manifest(recent_failure),
            ),
            self.now,
        )
        self.assertEqual(state.due_watch_ids, ("ptt_japan_travel_info",))
        reused = {item.source_id: item.attempt_id for item in state.reused_successes}
        self.assertEqual(reused["china_airlines_official"], "attempt-old-china")
        self.assertNotIn("ptt_japan_travel_info", reused)

    def test_latest_fresh_success_supplies_only_its_own_observations(self):
        older = parse_fixed_watch_manifest(
            self.manifest_payload(
                run_id="older",
                china_completed="2026-08-11T07:00:00+00:00",
                china_observation_title="old China observation",
            )
        )
        newer = parse_fixed_watch_manifest(
            self.manifest_payload(
                run_id="newer",
                china_completed="2026-08-11T08:45:00+00:00",
                china_observation_title="new China observation",
            )
        )
        state = build_fixed_watch_artifact_state(self.watches, (older, newer), self.now)
        titles = tuple(item.title for item in state.normalized_observations)
        self.assertIn("new China observation", titles)
        self.assertNotIn("old China observation", titles)
        china = next(
            item
            for item in state.reused_successes
            if item.source_id == "china_airlines_official"
        )
        self.assertEqual(china.run_id, "newer")

    def test_manifest_observation_count_mismatch_is_rejected(self):
        payload = self.manifest_payload()
        payload["attempts"][0]["observation_count"] = 2
        with self.assertRaisesRegex(ManifestError, "observation_count=2"):
            parse_fixed_watch_manifest(payload)

    def test_cli_reads_extracted_artifacts_and_emits_orchestration_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "fixed-watch-run.json"
            output_path = Path(tmp) / "state.json"
            manifest_path.write_text(
                json.dumps(self.manifest_payload()),
                encoding="utf-8",
            )
            rc = main(
                [
                    "--policy",
                    str(POLICY_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--now",
                    self.now.isoformat(),
                    "--output",
                    str(output_path),
                ]
            )
            self.assertEqual(rc, 0)
            state = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(state["due_watch_ids"], [])
            self.assertEqual(len(state["reused_successes"]), 2)
            self.assertEqual(len(state["normalized_observations"]), 1)

    def test_production_workflow_persists_manifest_without_becoming_scheduler(self):
        workflow_path = ROOT / ".github/workflows/fixed-watch-run.yml"
        text = workflow_path.read_text(encoding="utf-8")
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        triggers = workflow["on"]
        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("schedule", triggers)
        self.assertIn("name: fixed-watch-run-${{ inputs.radar_run_id }}", text)
        self.assertIn("path: artifacts/fixed-watch-run.json", text)
        self.assertIn("retention-days: 14", text)


if __name__ == "__main__":
    unittest.main()
