from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.access_blind_spots import AccessBlindSpotError, normalize_access_blind_spots
from cheap_flight_radar.production_radar import RadarRunResult, build_run_artifacts
from cheap_flight_radar.production_runtime import attach_access_blind_spot_truth


ROOT = Path(__file__).resolve().parents[1]


class SREAccessBlindSpotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    def base_result(self):
        return RadarRunResult(
            radar_run_id="production-radar-20260821T230000+0800",
            run_at="2026-08-21T23:00:00+08:00",
            deals=(),
            signals=(),
            coverage={"provider_health": {"status": "healthy"}},
            provider_failures=(),
        )

    def test_initial_registry_separates_surface_from_specific_fare_existence(self):
        truth = normalize_access_blind_spots(self.policy)
        self.assertEqual(truth["schema_version"], 1)
        self.assertFalse(truth["affects_provider_health"])
        self.assertEqual(len(truth["items"]), 1)
        item = truth["items"][0]
        self.assertEqual(item["id"], "expedia_flight_deals_app")
        self.assertEqual(item["surface_class_existence"], "known")
        self.assertEqual(item["specific_fare_existence"], "unknown")
        self.assertEqual(item["visibility"], "restricted")
        self.assertEqual(item["automatic_observation"], "unavailable")
        self.assertEqual(item["exact_reproducibility"], "unavailable")
        self.assertEqual(item["formal_truth_eligibility"], "ineligible")
        self.assertEqual(item["price_observability"], "unavailable")

    def test_inaccessible_registry_cannot_contain_hidden_price(self):
        policy = deepcopy(self.policy)
        policy["access_blind_spots"]["registry"][0]["current_price_twd"] = 1234
        with self.assertRaisesRegex(AccessBlindSpotError, "must not contain hidden fare/price"):
            normalize_access_blind_spots(policy)

    def test_unknown_fare_existence_cannot_be_relabelled_as_known_fare(self):
        policy = deepcopy(self.policy)
        policy["access_blind_spots"]["registry"][0]["coverage_semantics"] = "fare_exists"
        with self.assertRaisesRegex(AccessBlindSpotError, "cannot claim fare existence"):
            normalize_access_blind_spots(policy)

    def test_attached_blind_spots_do_not_change_candidates_or_health(self):
        base = self.base_result()
        result = attach_access_blind_spot_truth(base, policy=self.policy)
        self.assertEqual(result.deals, ())
        self.assertEqual(result.signals, ())
        self.assertEqual(result.exact_non_deal_candidates, ())
        self.assertEqual(result.ftr_absolute_low_non_deals, ())
        self.assertEqual(result.provider_failures, ())
        self.assertEqual(result.coverage["provider_health"], base.coverage["provider_health"])
        self.assertEqual(result.coverage["access_blind_spots"]["health_role"], "informational_non_required")

    def test_immutable_publication_evidence_carries_typed_coverage_without_price(self):
        result = attach_access_blind_spot_truth(self.base_result(), policy=self.policy)
        _, manifest = build_run_artifacts(result, policy=self.policy)
        blind = manifest["coverage"]["access_blind_spots"]
        raw = repr(blind).lower()
        self.assertIn("expedia_flight_deals_app", raw)
        self.assertNotIn("current_price_twd", raw)
        self.assertNotIn("price_twd", raw)
        self.assertFalse(blind["affects_provider_health"])

    def test_sr_e_does_not_modify_ftr_contract_files(self):
        doc = (ROOT / "docs" / "access-blind-spots-2026-08-21.md").read_text(encoding="utf-8")
        self.assertIn("changes no FTR code", doc)
        self.assertIn("contains no hidden price", doc)


if __name__ == "__main__":
    unittest.main()
