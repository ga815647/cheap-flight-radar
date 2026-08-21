from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.airfare import is_international_asia_oceania
from cheap_flight_radar.models import OriginSweepRequest, SearchRequest
from cheap_flight_radar.source_router import build_source_plan


ROOT = Path(__file__).resolve().parents[1]


class SRAOperationalSSOTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    def test_capability_state_separates_current_runtime_from_qualified_future(self):
        state = self.policy["capability_state"]
        semantics = state["ssot_semantics"]
        current = state["current_runtime"]
        future = state["accepted_qualified_future"]

        self.assertEqual(semantics["product_intent_authority"], "PRODUCT_INTENT.md")
        self.assertTrue(semantics["current_runtime_fields_do_not_define_product_ceiling"])
        self.assertTrue(semantics["accepted_target_capability_does_not_authorize_runtime_execution"])
        self.assertEqual(current["destination_scope"], "asia_oceania")
        self.assertEqual(future["destination_scope"], "substrate_native_worldwide_non_exhaustive")
        self.assertEqual(future["commodity_search"], "borrow_qualified_external_substrate")
        self.assertEqual(future["provider_access_adapters"], "replaceable_after_qualification")

    def test_sr_a_does_not_expand_current_runtime_geography(self):
        search = self.policy["search"]
        self.assertEqual(search["destination_scope"], "asia_oceania")
        self.assertEqual(search["daily_profiles"]["profiles"]["world"]["destination_scope"], "asia_oceania")
        self.assertTrue(is_international_asia_oceania("Japan"))
        self.assertFalse(is_international_asia_oceania("France"))

    def test_current_executable_provider_plan_is_unchanged_and_replaceable(self):
        state = self.policy["capability_state"]
        current = state["current_runtime"]
        self.assertEqual(current["destination_free_discovery_adapter"], "gflights_google_flight_deals")
        self.assertEqual(current["exact_flexible_open_jaw_adapter"], "gflights_google_exact")
        self.assertEqual(current["destination_free_automatic_executable_fallback"], "none")
        self.assertEqual(current["known_route_exact_flexible_automatic_executable_fallback"], "kiwi_mcp_exact")

        origin_plan = build_source_plan(
            OriginSweepRequest(origin="TPE", horizon_start="2026-08-21"),
            self.policy,
            {},
        )
        exact_plan = build_source_plan(
            SearchRequest(
                profile="world",
                search_stage="round_trip_benchmark",
                origin="TPE",
                destination="NRT",
                outbound_date="2026-10-05",
                return_date="2026-10-09",
                destination_country="JP",
            ),
            self.policy,
            {},
        )
        self.assertEqual([entry.provider for entry in origin_plan.entries], ["gflights_google_flight_deals"])
        self.assertEqual([entry.provider for entry in exact_plan.entries], ["gflights_google_exact", "kiwi_mcp_exact"])

    def test_preserved_product_truth_contracts_remain_active(self):
        self.assertEqual(
            self.policy["ranking"]["formal_deal_order"],
            ["relative_anomaly_strength_desc", "current_complete_airfare_twd_asc"],
        )
        self.assertTrue(self.policy["routing"]["open_jaw"])
        self.assertFalse(self.policy["operational_health"]["provider_acquisition"]["deal_count_is_health_signal"])
        self.assertEqual(
            self.policy["source_routing"]["api_production_gate"],
            "long_term_free_or_proven_recurring_free_quota_only",
        )
        absolute_low = self.policy["ftr_handoff"]["absolute_low_non_deal_producer"]
        self.assertTrue(absolute_low["enabled"])
        self.assertEqual(absolute_low["deal_isolation"]["formal_deal_input"], "excluded")
        self.assertEqual(absolute_low["generic_signal_isolation"]["weak_seed_promotion"], "forbidden")
        self.assertEqual(self.policy["ftr_handoff"]["schema_version"], "2.0")

    def test_retired_outbound_first_is_compatibility_only(self):
        contract = self.policy["search"]["outbound_first_contract"]
        self.assertEqual(contract["status"], "legacy_compatibility_only")
        self.assertFalse(self.policy["capability_state"]["ssot_semantics"]["legacy_search_contracts_are_product_intent"])

    def test_followup_qualification_gates_are_explicit_and_ordered(self):
        self.assertEqual(
            self.policy["capability_state"]["qualification_gates"],
            [
                "CFR-SR-B_gflights_qualification",
                "CFR-SR-C_scoped_native_window_BORROW_bakeoff",
                "CFR-SR-D_executable_TWD0_redundancy",
                "CFR-SR-E_blind_spot_schema",
                "CFR-SR-F_crawler_simplification",
            ],
        )


if __name__ == "__main__":
    unittest.main()
