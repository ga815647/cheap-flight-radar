from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tomllib
import unittest

import yaml

from cheap_flight_radar.airfare import ProviderResult
from cheap_flight_radar.models import OriginSweepRequest, SearchRequest
from cheap_flight_radar.production_radar import ProductionRadar
from cheap_flight_radar.providers.flyai import FlyAIAdapter
from cheap_flight_radar.source_router import build_source_plan


ROOT = Path(__file__).resolve().parents[1]
RUN_AT = datetime.fromisoformat("2026-08-20T09:00:00+08:00")


class FailingGFlightsOnlyAdapter:
    """Deterministic primary failure fixture; there is intentionally no fallback adapter."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def flight_deals(self, **kwargs):
        self.calls.append(("gflights", "flight_deals"))
        return ProviderResult(
            "gflights",
            "flight_deals",
            "failed",
            error="synthetic primary failure",
        )

    async def explore(self, **kwargs):
        self.calls.append(("gflights", "explore"))
        return ProviderResult("gflights", "explore", "complete", ())

    async def exact(self, **kwargs):
        self.fail("exact must not run without a discovered seed")

    async def cheapest_dates(self, **kwargs):
        self.fail("flexible search must not run without a discovered seed")

    async def open_jaw(self, **kwargs):
        self.fail("open jaw must not run without a discovered seed")

    def fail(self, message: str):
        raise AssertionError(message)


class ProviderFallbackTruthTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))

    def test_machine_ssot_has_no_legacy_executable_fallback_claim(self):
        routing = self.policy["source_routing"]
        self.assertEqual(routing["status"], "provider_execution_truth_converged_v3")
        contract = routing["route_plan_execution_contract"]
        self.assertTrue(contract["entry_means_current_execution_plane_can_invoke_provider"])
        self.assertEqual(contract["legacy_fallback_provider_field"], "forbidden")

        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        self.assertNotIn("fallback_provider", set(keys(routing["selected_routes"])))

    def test_current_plans_are_gflights_only_and_fallback_is_none(self):
        origin_plan = build_source_plan(
            OriginSweepRequest(origin="TPE", horizon_start="2026-08-20"),
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
        self.assertEqual([entry.provider for entry in exact_plan.entries], ["gflights_google_exact"])
        shared = self.policy["source_routing"]["selected_routes"]["shared"]
        self.assertIsNone(shared["origin_wide_discovery"]["automatic_executable_fallback"])
        self.assertIsNone(shared["broad_discovery"]["automatic_executable_fallback"])
        self.assertEqual(shared["origin_wide_discovery"]["primary_failure_action"], "fail_closed")
        self.assertEqual(shared["broad_discovery"]["primary_failure_action"], "fail_closed")

    def test_expedia_is_external_recall_candidate_not_anomaly_or_backend_coverage(self):
        routing = self.policy["source_routing"]
        origin_wide = routing["selected_routes"]["shared"]["origin_wide_discovery"]
        expedia = routing["providers"]["expedia_tw_airport_origin_surface"]
        self.assertIn("expedia_tw_airport_origin_surface", origin_wide["external_web_recall_candidates"])
        self.assertEqual(expedia["execution_plane"], "external_chatgpt_web_direct")
        self.assertEqual(expedia["current_integration_state"], "external_not_backend_integrated")
        self.assertFalse(expedia["automatic_execution_supported"])
        self.assertFalse(expedia["anomaly_authority"])
        self.assertEqual(expedia["canonical_backend_coverage_without_own_query"], "forbidden")
        self.assertNotIn("expedia", " ".join(routing["anomaly_truth_priority"]).lower())

    def test_fli_is_researched_not_integrated_and_flyai_is_distinct(self):
        routing = self.policy["source_routing"]
        broad = routing["selected_routes"]["shared"]["broad_discovery"]
        fli = routing["providers"]["fli_google_exact"]
        self.assertIn("fli_google_exact", broad["researched_not_integrated_candidates"])
        self.assertEqual(fli["current_integration_state"], "absent")
        self.assertEqual(fli["current_production_adapter"], "absent")
        self.assertEqual(fli["current_project_dependency"], "absent")
        self.assertFalse(fli["automatic_execution_supported"])
        self.assertEqual(fli["distinct_from_provider"], "flyai")
        self.assertEqual(FlyAIAdapter.provider, "flyai")
        self.assertNotEqual(FlyAIAdapter.provider, "fli_google_exact")

        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = [str(value).lower() for value in pyproject["project"]["dependencies"]]
        self.assertFalse(any(value.startswith("flights") for value in dependencies))
        self.assertFalse(any(value.startswith("click") for value in dependencies))

    async def test_primary_failure_has_zero_fake_fallback_calls_or_success_evidence(self):
        adapter = FailingGFlightsOnlyAdapter()
        result = await ProductionRadar(policy=deepcopy(self.policy), adapter=adapter).run(run_at=RUN_AT)

        self.assertEqual(result.deals, ())
        self.assertEqual(result.coverage["provider_health"]["status"], "provider_failed")
        self.assertTrue(result.provider_failures)
        self.assertEqual({provider for provider, _ in adapter.calls}, {"gflights"})
        self.assertEqual(len(adapter.calls), 16)  # 4 origins * (3 Flight Deals anchors + 1 Explore)
        self.assertEqual(sum(surface == "flight_deals" for _, surface in adapter.calls), 12)
        self.assertEqual(sum(surface == "explore" for _, surface in adapter.calls), 4)

        evidence = repr((result.coverage, result.provider_failures)).lower()
        self.assertNotIn("expedia", evidence)
        self.assertNotIn("fli_google_exact", evidence)
        self.assertNotIn("fallback succeeded", evidence)

    def test_docs_distinguish_current_execution_from_historical_candidates(self):
        strategy = (ROOT / "docs" / "search-strategy.md").read_text(encoding="utf-8")
        bakeoff = (ROOT / "docs" / "substrate-bakeoff-2026-08-13.md").read_text(encoding="utf-8")
        self.assertIn("automatic executable fallback is **none**", strategy)
        self.assertIn("Expedia airport-origin public Web remains an external", strategy)
        self.assertIn("no fli production adapter", strategy)
        self.assertIn("preserves the 2026-08-13 live bake-off evidence", bakeoff)
        self.assertIn("FlyAI is a distinct provider contract and is not fli", bakeoff)


if __name__ == "__main__":
    unittest.main()
