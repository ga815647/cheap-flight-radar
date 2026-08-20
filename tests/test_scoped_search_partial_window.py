from datetime import datetime
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.airfare import ProviderResult
from cheap_flight_radar.ftr_handoff import FTRHandoffError
from cheap_flight_radar.scoped_search import (
    AvailabilityWindow,
    ScopedExecutionPolicy,
    ScopedSearchRequest,
    acquire_scoped,
    execute_scoped_search,
)


RUN_AT = datetime.fromisoformat("2026-08-20T08:00:00+08:00")


def load_policy():
    return yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))


def partial_request():
    return ScopedSearchRequest(
        request_id="partial-window",
        availability_windows=(
            AvailabilityWindow("2026-10-01", "2026-10-05"),
            AvailabilityWindow("2026-11-01", "2026-11-05"),
        ),
        execution_policy=ScopedExecutionPolicy(
            max_discovery_calls=8,
            max_exact_revalidations=4,
        ),
    )


class OneWindowUnavailableAdapter:
    def __init__(self):
        self.flight_deals_calls = []
        self.exact_calls = []

    async def flight_deals(self, **kwargs):
        self.flight_deals_calls.append(dict(kwargs))
        if kwargs["anchor_departure"].startswith("2026-11"):
            return ProviderResult(
                "gflights",
                "flight_deals",
                "failed",
                error="fixture window unavailable",
            )
        # A genuinely queried empty slice is successful coverage and is not a
        # candidate or provider failure by itself.
        return ProviderResult("gflights", "flight_deals", "complete", ())

    async def exact(self, **kwargs):
        self.exact_calls.append(dict(kwargs))
        raise AssertionError("empty discovery must not invoke exact")


class ScopedPartialWindowCoverageTest(unittest.IsolatedAsyncioTestCase):
    async def test_one_queryable_window_cannot_make_failed_window_look_successful(self):
        adapter = OneWindowUnavailableAdapter()
        plan, result, evidence = await acquire_scoped(
            request=partial_request(),
            policy=load_policy(),
            adapter=adapter,
            run_at=RUN_AT,
        )

        self.assertEqual(len(plan.windows), 2)
        self.assertEqual(len(adapter.flight_deals_calls), 8)
        self.assertEqual(adapter.exact_calls, [])

        october = evidence["window_execution"]["w-2026-10-01-2026-10-05"]
        november = evidence["window_execution"]["w-2026-11-01-2026-11-05"]
        self.assertEqual(october["attempts"], 4)
        self.assertEqual(october["successes"], 4)
        self.assertEqual(october["failures"], 0)
        self.assertEqual(october["records"], 0)
        self.assertEqual(november["attempts"], 4)
        self.assertEqual(november["successes"], 0)
        self.assertEqual(november["failures"], 4)
        self.assertEqual(result.coverage["execution"]["flight_deals"]["failures"], 4)
        self.assertNotEqual(result.coverage["provider_execution"]["gflights"]["status"], "succeeded")

    async def test_partial_window_failure_cannot_leave_consumable_scoped_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            latest = history / "data/ftr-feed/latest.json"
            status = history / "data/ftr-feed/current-status.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_bytes(b"canonical-latest-before\n")
            status.write_bytes(b'{"repair_required":true,"fixture":"before"}\n')
            before = (latest.read_bytes(), status.read_bytes())

            with self.assertRaisesRegex(FTRHandoffError, "not consumable"):
                await execute_scoped_search(
                    request=partial_request(),
                    policy=load_policy(),
                    adapter=OneWindowUnavailableAdapter(),
                    history_dir=history,
                    producer_commit_sha="deadbeef",
                    run_at=RUN_AT,
                    generated_at="2026-08-20T08:05:00+08:00",
                )

            self.assertEqual((latest.read_bytes(), status.read_bytes()), before)
            scoped_dir = history / "data/ftr-feed/scoped"
            self.assertFalse(scoped_dir.exists() and any(scoped_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
