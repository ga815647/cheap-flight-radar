from __future__ import annotations

import unittest

from cheap_flight_radar.ftr_handoff import summarize_coverage
from cheap_flight_radar.operational_status import derive_provider_health


def _surface(*, records: int, successes: int = 1, empty: int = 0):
    return {
        "attempts": 1,
        "provider_calls": 1,
        "records": records,
        "successes": successes,
        "empty": empty,
        "failures": 0,
        "suppressed": 0,
        "unsupported": 0,
    }


class FTRProviderExecutionRegressionTests(unittest.TestCase):
    def test_recovered_kiwi_fallback_exposes_explicit_provider_execution(self):
        coverage = {
            "execution": {
                "flight_deals": _surface(records=1),
                "explore": _surface(records=0, successes=0, empty=1),
            },
            "origins": {
                "TPE": {
                    "status": "attempted",
                    "returned_flight_deals": 1,
                    "explore_seeds": 0,
                    "errors": [],
                }
            },
            "markets": {"world": {"status": "attempted"}},
            "all_origins_attempted": True,
            "access_redundancy": {
                "known_route_exact_flexible": {
                    "primary": "gflights_google_exact",
                    "automatic_executable_fallback": "kiwi_mcp",
                    "events": [
                        {
                            "surface": "exact",
                            "primary_provider": "gflights_google_exact",
                            "primary_state": "failed",
                            "primary_request_sent": True,
                            "primary_error": "sticky 429",
                            "fallback_provider": "kiwi_mcp_exact",
                            "fallback_state": "complete",
                            "fallback_request_sent": True,
                            "fallback_error": None,
                            "fallback_record_count": 1,
                        }
                    ],
                }
            },
        }
        failures = ({
            "origin": "known_route",
            "surface": "exact",
            "kind": "primary_failure_recovered_by_fallback",
            "error": "gflights primary failed; kiwi_mcp fallback=complete",
        },)

        health = derive_provider_health(coverage, failures)

        self.assertEqual(health["status"], "degraded")
        self.assertEqual(
            coverage["provider_execution"],
            {
                "gflights": {
                    "status": "failed",
                    "surfaces": ["exact"],
                    "reasons": ["sticky 429"],
                },
                "kiwi_mcp": {
                    "status": "succeeded",
                    "surfaces": ["exact"],
                    "reasons": [],
                },
            },
        )

        normalized = summarize_coverage({
            "coverage": coverage,
            "provider_health": health,
            "provider_failures": list(failures),
            "deals": [],
            "signals": [],
        })
        self.assertEqual(normalized["overall_state"], "degraded")
        self.assertEqual(normalized["providers"]["gflights"]["status"], "failed")
        self.assertEqual(normalized["providers"]["kiwi_mcp"]["status"], "succeeded")

    def test_inconsistent_fallback_identity_stays_fail_closed(self):
        coverage = {
            "execution": {
                "flight_deals": _surface(records=1),
                "explore": _surface(records=0, successes=0, empty=1),
            },
            "origins": {
                "TPE": {
                    "status": "attempted",
                    "returned_flight_deals": 1,
                    "explore_seeds": 0,
                    "errors": [],
                }
            },
            "markets": {"world": {"status": "attempted"}},
            "all_origins_attempted": True,
            "access_redundancy": {
                "known_route_exact_flexible": {
                    "primary": "gflights_google_exact",
                    "automatic_executable_fallback": "kiwi_mcp",
                    "events": [
                        {
                            "surface": "exact",
                            "primary_provider": "gflights_google_exact",
                            "primary_state": "failed",
                            "fallback_provider": "unexpected_provider",
                            "fallback_state": "complete",
                        }
                    ],
                }
            },
        }

        derive_provider_health(coverage)
        self.assertNotIn("provider_execution", coverage)


if __name__ == "__main__":
    unittest.main()
