from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.models import ProviderState, SearchRequest
from cheap_flight_radar.source_router import build_source_plan


ROOT = Path(__file__).resolve().parents[1]


class SourceRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "flight-radar.yaml").open("r", encoding="utf-8") as handle:
            cls.policy = yaml.safe_load(handle)

    def request(self, **overrides):
        values = {
            "profile": "china",
            "search_stage": "deep_search",
            "origin": "TSA",
            "destination": "SHA",
            "outbound_date": "2026-10-13",
            "return_date": "2026-10-17",
            "destination_country": "CN",
        }
        values.update(overrides)
        return SearchRequest(**values)

    def test_ssot_selects_only_current_china_deep_slice(self):
        routing = self.policy["source_routing"]
        deep = routing["selected_routes"]["china"]["deep_search"]
        self.assertEqual(deep["primary_provider"], "flyai")
        self.assertEqual(deep["query_scope"], "exact_round_trip")
        self.assertIsNone(deep["fallback_provider"])
        self.assertTrue(deep["exact_returned_airport_and_date_gate"])
        self.assertEqual(
            routing["providers"]["flyai"]["fare_semantics"]["currency"],
            "unknown",
        )
        self.assertIn("revalidation", routing["providers"]["flyai"]["unselected_roles"])

    def test_china_deep_plans_flyai_when_available_and_healthy(self):
        plan = build_source_plan(
            self.request(),
            self.policy,
            {"flyai": ProviderState("flyai", credential_available=True, healthy=True)},
        )
        self.assertEqual(plan.coverage_state, "planned")
        self.assertEqual([entry.provider for entry in plan.entries], ["flyai"])

    def test_missing_credential_is_explicit_unavailable(self):
        plan = build_source_plan(
            self.request(),
            self.policy,
            {"flyai": ProviderState("flyai", credential_available=False, healthy=True)},
        )
        self.assertEqual(plan.coverage_state, "unavailable")
        self.assertEqual(plan.entries, ())
        self.assertIn("no silent fallback", plan.fallback_reason)

    def test_unhealthy_provider_does_not_silently_degrade(self):
        plan = build_source_plan(
            self.request(),
            self.policy,
            {"flyai": ProviderState("flyai", credential_available=True, healthy=False)},
        )
        self.assertEqual(plan.coverage_state, "unavailable")
        self.assertIn("lower-fidelity", plan.fallback_reason)

    def test_combined_open_jaw_is_explicitly_unsupported(self):
        plan = build_source_plan(
            self.request(open_jaw_required=True),
            self.policy,
            {"flyai": ProviderState("flyai", credential_available=True, healthy=True)},
        )
        self.assertEqual(plan.coverage_state, "unsupported")
        self.assertEqual(plan.entries, ())

    def test_other_market_stage_remains_unconfigured(self):
        plan = build_source_plan(
            self.request(profile="world", search_stage="broad_discovery"),
            self.policy,
            {"flyai": ProviderState("flyai", credential_available=True, healthy=True)},
        )
        self.assertEqual(plan.coverage_state, "unconfigured")
        self.assertEqual(plan.entries, ())


if __name__ == "__main__":
    unittest.main()
