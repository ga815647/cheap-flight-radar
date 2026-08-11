from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class PublicIntelligenceSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        cls.public = cls.spec["public_intelligence"]

    def test_fixed_watch_registry_is_minimal_and_explicit(self) -> None:
        registry = self.public["fixed_watch_registry"]
        self.assertEqual(
            {source["id"] for source in registry},
            {
                "tigerair_tw_official",
                "china_airlines_official",
                "ptt_japan_travel_info",
            },
        )
        for source in registry:
            self.assertGreater(source["cadence_hours"], 0)
            self.assertIn(source["acquisition"], {"direct_http", "headless"})
            self.assertTrue(source["markets"])
            self.assertTrue(source["coverage_claim"].endswith("_attempt_only"))

    def test_opportunistic_sources_cannot_repair_fixed_coverage(self) -> None:
        coverage = self.public["coverage"]
        self.assertTrue(coverage["fixed_watch_attempts_are_coverage_authority"])
        self.assertTrue(coverage["failed_fixed_watch_must_be_reported"])
        self.assertTrue(coverage["opportunistic_source_cannot_substitute_fixed_watch_coverage"])
        self.assertTrue(coverage["fixed_registry_does_not_claim_market_exhaustiveness"])

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

    def test_high_risk_sources_are_researched_examples_not_required_watches(self) -> None:
        fixed_ids = {source["id"] for source in self.public["fixed_watch_registry"]}
        opportunistic_examples = set(
            self.public["opportunistic_policy"]["examples_researched_not_required_coverage"]
        )
        self.assertNotIn("facebook", fixed_ids)
        self.assertTrue(
            {
                "taiwan_airfare_editor_facebook_pages",
                "tway_official_events",
                "jejuair_official_events",
                "secret_flying",
                "fly4free",
            }.issubset(opportunistic_examples)
        )


if __name__ == "__main__":
    unittest.main()
