from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SRBGFlightsQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        cls.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_dependency_and_machine_provider_truth_use_031(self):
        deps = tuple(str(value) for value in self.pyproject["project"]["dependencies"])
        self.assertIn("gflights==0.3.1", deps)
        self.assertNotIn("gflights==0.3.0", deps)
        providers = self.policy["source_routing"]["providers"]
        for provider in (
            "gflights_google_flight_deals",
            "gflights_google_explore",
            "gflights_google_exact",
        ):
            self.assertEqual(providers[provider]["library"], "gflights==0.3.1")

    def test_sr_b_does_not_change_replaceable_fail_closed_architecture(self):
        state = self.policy["capability_state"]
        self.assertTrue(state["ssot_semantics"]["search_paths_and_provider_adapters_are_replaceable_implementation"])
        self.assertEqual(state["current_runtime"]["automatic_executable_fallback"], "none")
        routing = self.policy["source_routing"]
        self.assertTrue(routing["strict_no_silent_degradation"])
        shared = routing["selected_routes"]["shared"]
        self.assertIsNone(shared["origin_wide_discovery"]["automatic_executable_fallback"])
        self.assertIsNone(shared["broad_discovery"]["automatic_executable_fallback"])

    def test_qualification_document_is_durable_and_bounded(self):
        text = (ROOT / "docs" / "gflights-qualification-2026-08-21.md").read_text(encoding="utf-8")
        self.assertIn("Upgrade the current CFR machine access adapter", text)
        self.assertIn("f700a3345fda0e191829364d62647d75140db568", text)
        self.assertIn("32489872400", text)
        self.assertIn("does **not** prove permanent provider reliability", text)


if __name__ == "__main__":
    unittest.main()
