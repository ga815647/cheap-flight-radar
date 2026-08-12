from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class PublicIntelligenceSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        cls.public = cls.spec["public_intelligence"]

    def test_fixed_watch_registry_is_minimal_signal_only_and_explicit(self) -> None:
        registry = self.public["fixed_watch_registry"]
        self.assertEqual({source["id"] for source in registry}, {"china_airlines_official"})
        source = registry[0]
        self.assertEqual(source["role"], "signal_only")
        self.assertEqual(source["cadence_hours"], 24)
        self.assertIn(source["acquisition"], {"direct_http", "headless"})
        self.assertTrue(source["markets"])
        self.assertTrue(source["coverage_claim"].endswith("_attempt_only"))

    def test_ptt_is_not_an_active_fixed_watch(self) -> None:
        fixed_ids = {source["id"] for source in self.public["fixed_watch_registry"]}
        self.assertNotIn("ptt_japan_travel_info", fixed_ids)

    def test_tigerair_is_opportunistic_after_live_runner_contract_failed(self) -> None:
        fixed_ids = {source["id"] for source in self.public["fixed_watch_registry"]}
        self.assertNotIn("tigerair_tw_official", fixed_ids)
        exclusion = self.public["fixed_watch_research_exclusions"]["tigerair_tw_official"]
        self.assertEqual(exclusion["role"], "opportunistic")
        self.assertEqual(
            exclusion["preferred_discovery"],
            "public_web_indexed_official_news_and_static_event_pages",
        )
        self.assertFalse(exclusion["anti_bot_evasion_allowed"])

    def test_fixed_watch_is_not_deal_coverage_authority(self) -> None:
        coverage = self.public["coverage"]
        self.assertFalse(coverage["fixed_watch_attempts_are_coverage_authority"])
        self.assertFalse(coverage["opportunistic_source_cannot_substitute_fixed_watch_coverage"])
        self.assertTrue(coverage["fixed_registry_does_not_claim_market_exhaustiveness"])
        role = self.public["roles"]["fixed_watch"]
        self.assertEqual(role["definition"], "optional_recurring_signal_source_not_deal_truth_authority")
        self.assertFalse(role["failure_affects_coverage"])

    def test_dedupe_preserves_provenance_without_counting_sources_as_deals(self) -> None:
        provenance = self.public["provenance"]
        dedupe = self.public["dedupe"]
        self.assertTrue(provenance["first_seen_immutable"])
        self.assertTrue(provenance["discovery_sources_append_only"])
        self.assertTrue(provenance["preserve_all_duplicate_sightings"])
        self.assertTrue(dedupe["source_identity_excluded_from_candidate_identity"])
        self.assertTrue(dedupe["price_excluded_from_itinerary_identity"])
        self.assertTrue(dedupe["fare_observations_append_to_existing_candidate"])
        self.assertTrue(dedupe["never_count_duplicate_sightings_as_separate_deals"])

    def test_high_risk_or_unstable_sources_are_researched_examples_not_required_watches(self) -> None:
        fixed_ids = {source["id"] for source in self.public["fixed_watch_registry"]}
        opportunistic_examples = set(
            self.public["opportunistic_policy"]["examples_researched_not_required_coverage"]
        )
        self.assertNotIn("facebook", fixed_ids)
        self.assertTrue(
            {
                "tigerair_tw_official_news_and_static_events",
                "taiwan_airfare_editor_facebook_pages",
                "tway_official_events",
                "jejuair_official_events",
                "secret_flying",
                "fly4free",
            }.issubset(opportunistic_examples)
        )


if __name__ == "__main__":
    unittest.main()
