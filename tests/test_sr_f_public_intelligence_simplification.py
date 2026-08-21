from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
import yaml

from cheap_flight_radar import public_intelligence as pi

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


class SRFPublicIntelligenceSimplificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        cls.public = cls.policy["public_intelligence"]

    def test_fixed_watch_executable_surface_is_retired(self):
        for rel in (
            ".github/workflows/fixed-watch-run.yml",
            "src/cheap_flight_radar/fixed_watch_runner.py",
            "src/cheap_flight_radar/fixed_watch_state.py",
            "src/cheap_flight_radar/public_sources.py",
        ):
            self.assertFalse((ROOT / rel).exists(), rel)
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
        self.assertNotIn("scrapy", pyproject)
        self.assertNotIn("playwright", pyproject)
        self.assertFalse(hasattr(pi, "FixedWatch"))
        self.assertFalse(hasattr(pi, "plan_fixed_watches"))

    def test_ssot_keeps_only_opportunistic_and_verification_signal_roles(self):
        self.assertEqual(self.public["status"], "simplified_opportunistic_signal_lane_v2")
        self.assertEqual(set(self.public["roles"]), {"opportunistic", "verification_only"})
        self.assertFalse(self.public["coverage"]["public_intelligence_is_required_coverage_authority"])
        self.assertFalse(self.public["coverage"]["opportunistic_source_failure_affects_provider_health"])
        self.assertEqual(self.public["retired_fixed_watch_subsystem"]["status"], "retired_by_CFR_SR_F")
        self.assertNotIn("fixed_watch_coverage_and_freshness", self.policy["publication"]["required_operational_sections"])

    def test_campaign_dedupe_preserves_provenance_without_price_identity(self):
        now = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
        first = pi.DiscoverySighting(
            observation_id="one", source_id="a", source_url="https://a.example/", item_url="https://a.example/1",
            observed_at=now - timedelta(minutes=1), title="sale", carrier="Carrier X", sale_period="Aug",
            travel_period="Sep", route_set=("TPE-NRT",), promo_code="GO", price_text="TWD 1999",
        )
        second = pi.DiscoverySighting(
            observation_id="two", source_id="b", source_url="https://b.example/", item_url="https://b.example/2",
            observed_at=now, title="sale repost", carrier="carrier x", sale_period="Aug",
            travel_period="Sep", route_set=("TPE-NRT",), promo_code="go", price_text="TWD 2099",
        )
        self.assertEqual(pi.campaign_identity(first), pi.campaign_identity(second))
        candidates, unresolved = pi.dedupe_campaign_sightings((second, first))
        self.assertEqual(unresolved, ())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].discovery_source_ids, ("a", "b"))
        self.assertEqual(tuple(x.price_text for x in candidates[0].sightings), ("TWD 1999", "TWD 2099"))

    def test_unresolved_signal_is_not_promoted_and_itinerary_identity_has_no_price(self):
        now = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)
        raw = pi.DiscoverySighting(
            observation_id="raw", source_id="web", source_url="https://example/", item_url="https://example/raw",
            observed_at=now, title="unscoped cheap hint",
        )
        candidates, unresolved = pi.dedupe_campaign_sightings((raw,))
        self.assertEqual(candidates, ())
        self.assertEqual(unresolved, (raw,))
        ident = pi.exact_itinerary_identity(
            trip_type="round_trip", exact_origin_airport="TPE", exact_destination_airport_when_known="NRT",
            outbound_date_or_window="2026-10-05", return_date_or_window="2026-10-09",
            operating_or_marketing_flight_identity_when_known=("IT200", "IT201"),
        )
        self.assertTrue(ident.startswith("itinerary:"))

    def test_publication_has_no_active_fixed_watch_registry_dependency(self):
        source = (ROOT / "src/cheap_flight_radar/publication.py").read_text(encoding="utf-8")
        self.assertNotIn('policy["public_intelligence"]["fixed_watch_registry"]', source)
        self.assertIn("Historical fixed-watch evidence", source)

    def test_current_docs_make_old_fixed_watch_material_historical(self):
        text = (ROOT / "docs/search-strategy.md").read_text(encoding="utf-8")
        self.assertIn("Current public-intelligence contract (SR-F, 2026-08-21)", text)
        self.assertIn("fixed-watch crawler/cadence/state subsystem is retired", text)


if __name__ == "__main__":
    unittest.main()
