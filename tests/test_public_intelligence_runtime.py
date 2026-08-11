from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.fixed_watch_runner import browser_required
from cheap_flight_radar.public_intelligence import (
    DiscoverySighting,
    FixedWatch,
    FixedWatchAttempt,
    campaign_identity,
    dedupe_campaign_sightings,
    exact_itinerary_identity,
    load_fixed_watch_registry,
    load_policy,
    plan_fixed_watches,
    validate_orchestration_policy,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "flight-radar.yaml"
UTC = timezone.utc


class PublicIntelligenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.watches = load_fixed_watch_registry(POLICY_PATH)
        self.by_id = {watch.id: watch for watch in self.watches}
        self.now = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)

    def attempt(self, source_id, status, completed_hours_ago, name):
        completed = self.now - timedelta(hours=completed_hours_ago)
        return FixedWatchAttempt(
            attempt_id=name,
            source_id=source_id,
            status=status,
            started_at=completed - timedelta(minutes=1),
            completed_at=completed,
            requested_url=self.by_id[source_id].entry_url,
        )

    def test_registry_and_orchestration_contract(self):
        self.assertEqual(
            {watch.id for watch in self.watches},
            {"china_airlines_official", "ptt_japan_travel_info"},
        )
        policy = load_policy(POLICY_PATH)
        validate_orchestration_policy(policy)
        orchestration = policy["public_intelligence"]["orchestration"]
        self.assertEqual(orchestration["primary_scheduler"], "chatgpt_scheduled_radar_run")
        self.assertFalse(orchestration["independent_github_cron"])
        self.assertIn("freshness_reuse_window", orchestration["cadence_semantics"])
        self.assertEqual(self.by_id["china_airlines_official"].acquisition, "direct_http")
        self.assertEqual(self.by_id["ptt_japan_travel_info"].acquisition, "direct_http")

    def test_browser_fallback_is_opt_in_not_required_by_current_registry(self):
        self.assertFalse(browser_required(self.watches))
        future_headless = FixedWatch(
            id="future_js_source",
            markets=("world",),
            source_type="official_airline",
            acquisition="headless",
            entry_url="https://example.test/",
            cadence_hours=6,
            coverage_claim="source_attempt_only",
        )
        self.assertTrue(browser_required((future_headless,)))

    def test_no_success_is_due(self):
        plan = {entry.source_id: entry for entry in plan_fixed_watches(self.watches, (), self.now)}
        self.assertTrue(all(entry.due for entry in plan.values()))
        self.assertEqual(plan["ptt_japan_travel_info"].reason, "no_successful_attempt")

    def test_fresh_success_can_be_reused_and_boundary_is_due(self):
        ptt = self.by_id["ptt_japan_travel_info"]
        fresh = self.attempt(ptt.id, "success", 2, "ptt-fresh")
        entry = plan_fixed_watches((ptt,), (fresh,), self.now)[0]
        self.assertFalse(entry.due)
        self.assertEqual(entry.latest_success_attempt_id, "ptt-fresh")
        self.assertEqual(entry.reason, "fresh_prior_success")

        boundary = self.attempt(ptt.id, "success", 3, "ptt-boundary")
        entry = plan_fixed_watches((ptt,), (boundary,), self.now)[0]
        self.assertTrue(entry.due)
        self.assertEqual(entry.reason, "cadence_expired")

    def test_failed_attempt_does_not_refresh_due_clock(self):
        ptt = self.by_id["ptt_japan_travel_info"]
        expired_success = self.attempt(ptt.id, "success", 4, "old-success")
        recent_failure = self.attempt(ptt.id, "fetch_failed", 1, "recent-failure")
        entry = plan_fixed_watches((ptt,), (expired_success, recent_failure), self.now)[0]
        self.assertTrue(entry.due)
        self.assertEqual(entry.latest_success_attempt_id, "old-success")

    def test_china_airlines_six_hour_cadence(self):
        china = self.by_id["china_airlines_official"]
        fresh = self.attempt(china.id, "success", 5, "fresh")
        expired = self.attempt(china.id, "success", 6, "expired")
        self.assertFalse(plan_fixed_watches((china,), (fresh,), self.now)[0].due)
        self.assertTrue(plan_fixed_watches((china,), (expired,), self.now)[0].due)

    def test_campaign_dedupe_preserves_all_sightings_and_ignores_source_and_price(self):
        first = DiscoverySighting(
            observation_id="one",
            source_id="source-a",
            source_url="https://a.example/",
            item_url="https://a.example/deal",
            observed_at=self.now - timedelta(minutes=10),
            title="sale one",
            carrier="Carrier X",
            sale_period="Aug 11-Aug 12",
            travel_period="Sep-Oct",
            route_set=("TPE-NRT", "KHH-NRT"),
            promo_code="GO",
            price_text="TWD 1999",
        )
        second = DiscoverySighting(
            observation_id="two",
            source_id="source-b",
            source_url="https://b.example/",
            item_url="https://b.example/another",
            observed_at=self.now,
            title="sale repost",
            carrier="carrier x",
            sale_period="Aug 11-Aug 12",
            travel_period="Sep-Oct",
            route_set=("KHH-NRT", "TPE-NRT"),
            promo_code="go",
            price_text="TWD 2099",
        )
        self.assertEqual(campaign_identity(first), campaign_identity(second))
        candidates, unresolved = dedupe_campaign_sightings((second, first))
        self.assertEqual(unresolved, ())
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.first_seen_at, first.observed_at)
        self.assertEqual(candidate.first_discovery_source_id, "source-a")
        self.assertEqual(candidate.discovery_source_ids, ("source-a", "source-b"))
        self.assertEqual(tuple(item.price_text for item in candidate.sightings), ("TWD 1999", "TWD 2099"))

    def test_unresolved_sighting_is_not_promoted_to_separate_deal(self):
        sighting = DiscoverySighting(
            observation_id="raw",
            source_id="source-a",
            source_url="https://a.example/",
            item_url="https://a.example/raw",
            observed_at=self.now,
            title="cheap fare without campaign scope",
        )
        candidates, unresolved = dedupe_campaign_sightings((sighting,))
        self.assertEqual(candidates, ())
        self.assertEqual(unresolved, (sighting,))

    def test_exact_itinerary_identity_has_no_price_dimension(self):
        kwargs = dict(
            trip_type="round_trip",
            exact_origin_airport="TPE",
            exact_destination_airport_when_known="NRT",
            outbound_date_or_window="2026-09-01",
            return_date_or_window="2026-09-05",
            operating_or_marketing_flight_identity_when_known=("IT200", "IT201"),
        )
        first = exact_itinerary_identity(**kwargs)
        second = exact_itinerary_identity(**kwargs)
        self.assertEqual(first, second)

    def test_fixed_watch_workflow_has_no_schedule_and_browser_install_is_conditional(self):
        workflow_path = ROOT / ".github/workflows/fixed-watch-run.yml"
        text = workflow_path.read_text(encoding="utf-8")
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        triggers = workflow["on"]
        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("schedule", triggers)
        self.assertIn("--print-browser-required", text)
        self.assertIn("if: steps.runtime.outputs.browser_required == 'true'", text)
        self.assertIn("playwright install --with-deps chromium", text)


if __name__ == "__main__":
    unittest.main()
