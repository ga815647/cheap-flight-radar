from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.models import OriginSweepRequest, SearchRequest
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

    def test_ssot_selects_only_integrated_google_flight_deals_for_destination_free_backend(self):
        routing = self.policy["source_routing"]
        origin_wide = routing["selected_routes"]["shared"]["origin_wide_discovery"]
        self.assertEqual(origin_wide["primary_provider"], "gflights_google_flight_deals")
        self.assertIsNone(origin_wide["automatic_executable_fallback"])
        self.assertEqual(origin_wide["primary_failure_action"], "fail_closed")
        self.assertNotIn("fallback_provider", origin_wide)
        self.assertIn("expedia_tw_airport_origin_surface", origin_wide["external_web_recall_candidates"])
        self.assertEqual(origin_wide["execution_mode"], "keyless_http_client")
        self.assertFalse(origin_wide["credential_required"])
        self.assertEqual(origin_wide["query_scope"], "destination_free_origin_airport_anywhere")
        self.assertTrue(origin_wide["destination_input_forbidden"])
        self.assertIn("qualified_round_trip_deal", origin_wide["evidence_kinds"])
        provider = routing["providers"]["gflights_google_flight_deals"]
        self.assertEqual(provider["truth_source"], "google_flight_deals")
        self.assertEqual(provider["execution_plane"], "canonical_backend")
        self.assertEqual(provider["current_integration_state"], "integrated")
        self.assertTrue(provider["automatic_execution_supported"])
        self.assertEqual(provider["proxy"], "forbidden")
        self.assertEqual(provider["user_agent"], "fixed_explicit_project_identity_required")

    def test_known_route_completion_has_no_automatic_fli_fallback(self):
        routing = self.policy["source_routing"]
        broad = routing["selected_routes"]["shared"]["broad_discovery"]
        self.assertEqual(broad["primary_provider"], "gflights_google_exact")
        self.assertIsNone(broad["automatic_executable_fallback"])
        self.assertEqual(broad["primary_failure_action"], "fail_closed")
        self.assertNotIn("fallback_provider", broad)
        self.assertIn("fli_google_exact", broad["researched_not_integrated_candidates"])
        self.assertEqual(broad["query_scope"], "known_route_exact_or_flexible_completion")
        self.assertEqual(broad["combined_open_jaw"], "supported")
        self.assertTrue(broad["revalidation_required"])

    def test_destination_free_origin_sweep_plans_only_current_backend_provider(self):
        request = OriginSweepRequest(origin="TPE", horizon_start="2026-08-13")
        plan = build_source_plan(request, self.policy, {})
        self.assertEqual(plan.coverage_state, "planned")
        self.assertEqual([entry.provider for entry in plan.entries], ["gflights_google_flight_deals"])
        self.assertIn("destination-free", plan.entries[0].reason)

    def test_external_web_recall_metadata_never_becomes_executable_entry(self):
        policy = deepcopy(self.policy)
        origin_wide = policy["source_routing"]["selected_routes"]["shared"]["origin_wide_discovery"]
        origin_wide["external_web_recall_candidates"].append("chatgpt_web_public_fare_index")
        plan = build_source_plan(OriginSweepRequest(origin="TPE", horizon_start="2026-08-13"), policy, {})
        self.assertEqual([entry.provider for entry in plan.entries], ["gflights_google_flight_deals"])

    def test_researched_fli_metadata_never_becomes_executable_entry(self):
        policy = deepcopy(self.policy)
        broad = policy["source_routing"]["selected_routes"]["shared"]["broad_discovery"]
        broad["researched_not_integrated_candidates"].append("trvl_research_only")
        plan = build_source_plan(
            self.request(profile="world", search_stage="outbound_probe", origin="TPE", destination="ICN", return_date=None),
            policy,
            {},
        )
        self.assertEqual([entry.provider for entry in plan.entries], ["gflights_google_exact"])

    def test_legacy_fallback_provider_drift_fails_closed(self):
        policy = deepcopy(self.policy)
        policy["source_routing"]["selected_routes"]["shared"]["origin_wide_discovery"]["fallback_provider"] = (
            "expedia_tw_airport_origin_surface"
        )
        plan = build_source_plan(OriginSweepRequest(origin="TPE", horizon_start="2026-08-13"), policy, {})
        self.assertEqual(plan.coverage_state, "invalid_contract")
        self.assertEqual(plan.entries, ())
        self.assertIn("fallback_provider", plan.fallback_reason)

    def test_unintegrated_automatic_fallback_drift_fails_closed(self):
        policy = deepcopy(self.policy)
        policy["source_routing"]["selected_routes"]["shared"]["broad_discovery"]["automatic_executable_fallback"] = (
            "fli_google_exact"
        )
        plan = build_source_plan(
            self.request(profile="world", search_stage="outbound_probe", origin="TPE", destination="ICN", return_date=None),
            policy,
            {},
        )
        self.assertEqual(plan.coverage_state, "invalid_contract")
        self.assertEqual(plan.entries, ())
        self.assertIn("not integrated/executable", plan.fallback_reason)

    def test_preselected_destination_cannot_claim_destination_free_coverage(self):
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
        self.assertIn("destination-free origin coverage", plan.fallback_reason)

    def test_seed_can_continue_to_known_route_outbound_probe(self):
        plan = build_source_plan(
            self.request(
                profile="world",
                search_stage="outbound_probe",
                origin="TPE",
                destination="ICN",
                outbound_date="2026-09-16",
                return_date=None,
            ),
            self.policy,
            {},
        )
        self.assertEqual(plan.coverage_state, "planned")
        self.assertEqual([entry.provider for entry in plan.entries], ["gflights_google_exact"])

    def test_return_expansion_requires_exact_return_date(self):
        plan = build_source_plan(
            self.request(
                profile="world",
                search_stage="return_expansion",
                origin="TPE",
                destination="ICN",
                outbound_date="2026-09-16",
                return_date=None,
            ),
            self.policy,
            {},
        )
        self.assertEqual(plan.coverage_state, "unsupported")
        self.assertIn("exact return date", plan.fallback_reason)

    def test_china_deep_uses_shared_google_exact_without_credentials(self):
        routing = self.policy["source_routing"]
        deep = routing["selected_routes"]["china"]["deep_search"]
        self.assertEqual(deep["primary_provider"], "gflights_google_exact")
        self.assertIsNone(deep["automatic_executable_fallback"])
        self.assertEqual(deep["primary_failure_action"], "fail_closed")
        self.assertFalse(deep["credential_required"])
        self.assertFalse(deep["specialist_pipeline_required"])
        plan = build_source_plan(self.request(), self.policy, {})
        self.assertEqual(plan.coverage_state, "planned")
        self.assertEqual([entry.provider for entry in plan.entries], ["gflights_google_exact"])

    def test_combined_open_jaw_is_supported_by_selected_exact_substrate(self):
        plan = build_source_plan(self.request(open_jaw_required=True), self.policy, {})
        self.assertEqual(plan.coverage_state, "planned")
        self.assertEqual([entry.provider for entry in plan.entries], ["gflights_google_exact"])

    def test_unconfigured_deep_market_stage_remains_explicit(self):
        plan = build_source_plan(self.request(profile="world", search_stage="deep_search"), self.policy, {})
        self.assertEqual(plan.coverage_state, "unconfigured")
        self.assertEqual(plan.entries, ())


if __name__ == "__main__":
    unittest.main()
