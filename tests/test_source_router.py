from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.models import OriginSweepRequest, ProviderState, SearchRequest
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

    def test_ssot_selects_shared_broad_discovery_before_promo_only_sources(self):
        routing = self.policy["source_routing"]
        broad = routing["selected_routes"]["shared"]["broad_discovery"]
        self.assertEqual(broad["primary_provider"], "chatgpt_web_public_fare_index")
        self.assertEqual(broad["execution_mode"], "chatgpt_web_direct")
        self.assertEqual(
            broad["applies_to_profiles"], ["world", "japan", "korea", "china"]
        )
        self.assertEqual(
            broad["source_class_order"][0],
            "public_ota_or_metasearch_route_fare_index",
        )
        self.assertIn("origin_floor_scan", broad["query_shapes"])
        self.assertIn("exact_route_probe", broad["query_shapes"])
        self.assertTrue(broad["revalidation_required"])
        self.assertFalse(broad["full_market_coverage_claim"])

    def test_destination_free_origin_sweep_plans_one_shared_direct_web_stage(self):
        request = OriginSweepRequest(
            origin="TPE",
            horizon_start="2026-08-12",
        )
        self.assertEqual(
            request.profiles,
            ("world", "japan", "korea", "china"),
        )
        plan = build_source_plan(request, self.policy, {})
        self.assertEqual(plan.coverage_state, "planned")
        self.assertEqual(
            [entry.provider for entry in plan.entries],
            ["chatgpt_web_public_fare_index"],
        )
        self.assertIn("destination-free", plan.entries[0].reason)

    def test_preselected_destination_cannot_claim_broad_discovery_contract(self):
        plan = build_source_plan(
            self.request(
                profile="world",
                search_stage="broad_discovery",
                origin="TPE",
                destination="PUS",
                outbound_date="2026-09-21",
                return_date=None,
            ),
            self.policy,
            {},
        )
        self.assertEqual(plan.coverage_state, "invalid_contract")
        self.assertEqual(plan.entries, ())
        self.assertIn("cannot establish outbound-first coverage", plan.fallback_reason)

    def test_origin_sweep_seed_can_continue_to_known_route_outbound_probe(self):
        plan = build_source_plan(
            self.request(
                profile="world",
                search_stage="outbound_probe",
                origin="TPE",
                destination="ICN",
                outbound_date="2026-09-30",
                return_date=None,
            ),
            self.policy,
            {},
        )
        self.assertEqual(plan.coverage_state, "planned")
        self.assertIn("known-route outbound_probe", plan.entries[0].reason)

    def test_return_expansion_requires_exact_return_date(self):
        plan = build_source_plan(
            self.request(
                profile="world",
                search_stage="return_expansion",
                origin="TPE",
                destination="ICN",
                outbound_date="2026-09-30",
                return_date=None,
            ),
            self.policy,
            {},
        )
        self.assertEqual(plan.coverage_state, "unsupported")
        self.assertIn("exact return date", plan.fallback_reason)

    def test_ssot_keeps_china_deep_slice_on_flyai(self):
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

    def test_unconfigured_deep_market_stage_remains_explicit(self):
        plan = build_source_plan(
            self.request(profile="world", search_stage="deep_search"),
            self.policy,
            {"flyai": ProviderState("flyai", credential_available=True, healthy=True)},
        )
        self.assertEqual(plan.coverage_state, "unconfigured")
        self.assertEqual(plan.entries, ())


if __name__ == "__main__":
    unittest.main()
