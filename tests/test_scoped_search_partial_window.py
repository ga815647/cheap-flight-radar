from datetime import datetime
from pathlib import Path
import tempfile
import unittest

import yaml

from cheap_flight_radar.airfare import ProviderResult
from cheap_flight_radar.ftr_handoff import FTRHandoffError, load_manifest_snapshot
from cheap_flight_radar.scoped_search import (
    AvailabilityWindow,
    DurationConstraint,
    ScopedExecutionPolicy,
    ScopedSearchRequest,
    acquire_scoped,
    execute_scoped_search,
)


RUN_AT = datetime.fromisoformat("2026-08-20T08:00:00+08:00")
GENERATED_AT = "2026-08-20T08:05:00+08:00"


def load_policy():
    return yaml.safe_load(Path("flight-radar.yaml").read_text(encoding="utf-8"))


def scoped_request(
    *,
    request_id="partial-window",
    windows=(
        ("2026-10-01", "2026-10-05"),
        ("2026-11-01", "2026-11-05"),
    ),
    discovery_calls=8,
    duration=None,
):
    return ScopedSearchRequest(
        request_id=request_id,
        availability_windows=tuple(AvailabilityWindow(*value) for value in windows),
        execution_policy=ScopedExecutionPolicy(
            max_discovery_calls=discovery_calls,
            max_exact_revalidations=4,
        ),
        duration=duration,
    )


class CompleteEmptyAdapter:
    def __init__(self):
        self.flight_deals_calls = []
        self.exact_calls = []

    async def flight_deals(self, **kwargs):
        self.flight_deals_calls.append(dict(kwargs))
        return ProviderResult("gflights", "flight_deals", "complete", ())

    async def exact(self, **kwargs):
        self.exact_calls.append(dict(kwargs))
        raise AssertionError("empty discovery must not invoke exact")


class OneWindowUnavailableAdapter(CompleteEmptyAdapter):
    async def flight_deals(self, **kwargs):
        self.flight_deals_calls.append(dict(kwargs))
        if kwargs["anchor_departure"].startswith("2026-11"):
            return ProviderResult(
                "gflights",
                "flight_deals",
                "failed",
                error="fixture window unavailable",
            )
        return ProviderResult("gflights", "flight_deals", "complete", ())


class ScopedPartialWindowCoverageTest(unittest.IsolatedAsyncioTestCase):
    async def test_one_queryable_window_cannot_make_failed_window_look_successful(self):
        adapter = OneWindowUnavailableAdapter()
        plan, result, evidence = await acquire_scoped(
            request=scoped_request(),
            policy=load_policy(),
            adapter=adapter,
            run_at=RUN_AT,
        )

        self.assertEqual(len(plan.windows), 2)
        self.assertEqual(len(adapter.flight_deals_calls), 8)
        self.assertEqual(adapter.exact_calls, [])

        october = evidence["window_execution"]["w-2026-10-01-2026-10-05"]
        november = evidence["window_execution"]["w-2026-11-01-2026-11-05"]
        self.assertEqual(october["status"], "succeeded")
        self.assertEqual(october["attempts"], 4)
        self.assertEqual(october["provider_calls"], 4)
        self.assertEqual(october["successes"], 0)
        self.assertEqual(october["empty"], 4)
        self.assertEqual(october["failures"], 0)
        self.assertEqual(october["records"], 0)
        self.assertEqual(november["status"], "failed")
        self.assertEqual(november["attempts"], 4)
        self.assertEqual(november["provider_calls"], 4)
        self.assertEqual(november["successes"], 0)
        self.assertEqual(november["empty"], 0)
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
                    request=scoped_request(),
                    policy=load_policy(),
                    adapter=OneWindowUnavailableAdapter(),
                    history_dir=history,
                    producer_commit_sha="deadbeef",
                    run_at=RUN_AT,
                    generated_at=GENERATED_AT,
                )

            self.assertEqual((latest.read_bytes(), status.read_bytes()), before)
            scoped_dir = history / "data/ftr-feed/scoped"
            self.assertFalse(scoped_dir.exists() and any(scoped_dir.iterdir()))

    async def test_budget_unattempted_window_is_explicit_and_non_consumable(self):
        req = scoped_request(request_id="budget-window", discovery_calls=4)
        adapter = CompleteEmptyAdapter()
        plan, result, evidence = await acquire_scoped(
            request=req,
            policy=load_policy(),
            adapter=adapter,
            run_at=RUN_AT,
        )
        self.assertTrue(plan.discovery_truncated)
        october = evidence["window_execution"]["w-2026-10-01-2026-10-05"]
        november = evidence["window_execution"]["w-2026-11-01-2026-11-05"]
        self.assertEqual(october["status"], "succeeded")
        self.assertEqual(october["empty"], 4)
        self.assertEqual(november["status"], "not_attempted")
        self.assertEqual(november["reason"], "budget_unattempted")
        self.assertEqual(november["attempts"], 0)
        self.assertEqual(november["provider_calls"], 0)
        self.assertEqual(result.coverage["provider_health"]["status"], "degraded")
        self.assertEqual(result.coverage["provider_execution"]["gflights"]["status"], "succeeded")

        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            latest = history / "data/ftr-feed/latest.json"
            status = history / "data/ftr-feed/current-status.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_bytes(b"canonical-budget-before\n")
            status.write_bytes(b'{"repair_required":true,"fixture":"budget-before"}\n')
            before = (latest.read_bytes(), status.read_bytes())
            with self.assertRaisesRegex(FTRHandoffError, "window coverage incomplete"):
                await execute_scoped_search(
                    request=req,
                    policy=load_policy(),
                    adapter=CompleteEmptyAdapter(),
                    history_dir=history,
                    producer_commit_sha="deadbeef",
                    run_at=RUN_AT,
                    generated_at=GENERATED_AT,
                )
            self.assertEqual((latest.read_bytes(), status.read_bytes()), before)
            scoped_dir = history / "data/ftr-feed/scoped"
            self.assertFalse(scoped_dir.exists() and any(scoped_dir.iterdir()))

    async def test_every_supplied_window_attempt_truth_is_persisted_and_reconstructable(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            outcome = await execute_scoped_search(
                request=scoped_request(request_id="all-window-empty", discovery_calls=8),
                policy=load_policy(),
                adapter=CompleteEmptyAdapter(),
                history_dir=history,
                producer_commit_sha="deadbeef",
                run_at=RUN_AT,
                generated_at=GENERATED_AT,
            )
            loaded = load_manifest_snapshot(
                history_dir=history,
                manifest_path=outcome.staged["manifest_path"],
            )
            persisted = loaded["coverage"]["windows"]
            scoped = loaded["scoped_search"]["execution"]["window_execution"]
            self.assertEqual(persisted, scoped)
            self.assertEqual(
                set(persisted),
                {"w-2026-10-01-2026-10-05", "w-2026-11-01-2026-11-05"},
            )
            for row in persisted.values():
                self.assertEqual(row["status"], "succeeded")
                self.assertEqual(row["attempts"], row["planned_tasks"])
                self.assertEqual(row["provider_calls"], row["attempts"])
                self.assertEqual(row["empty"], row["provider_calls"])
                self.assertEqual(row["records"], 0)
            self.assertEqual(loaded["candidate_counts"]["variants"], 0)

    async def test_zero_queryable_date_pairs_make_zero_provider_calls_and_not_attempted_truth(self):
        req = scoped_request(
            request_id="zero-pairs",
            windows=(("2026-10-01", "2026-10-03"),),
            discovery_calls=4,
            duration=DurationConstraint(min_nights=5),
        )
        adapter = CompleteEmptyAdapter()
        plan, result, evidence = await acquire_scoped(
            request=req,
            policy=load_policy(),
            adapter=adapter,
            run_at=RUN_AT,
        )
        self.assertEqual(plan.discovery_tasks, ())
        self.assertEqual(adapter.flight_deals_calls, [])
        row = evidence["window_execution"]["w-2026-10-01-2026-10-03"]
        self.assertEqual(row["queryable_date_pairs"], 0)
        self.assertEqual(row["status"], "not_attempted")
        self.assertEqual(row["reason"], "no_queryable_date_pair")
        self.assertEqual(row["attempts"], 0)
        self.assertEqual(row["provider_calls"], 0)
        self.assertEqual(result.coverage["provider_execution"]["gflights"]["status"], "not_attempted")

        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp)
            with self.assertRaisesRegex(FTRHandoffError, "window coverage incomplete"):
                await execute_scoped_search(
                    request=req,
                    policy=load_policy(),
                    adapter=CompleteEmptyAdapter(),
                    history_dir=history,
                    producer_commit_sha="deadbeef",
                    run_at=RUN_AT,
                    generated_at=GENERATED_AT,
                )
            self.assertEqual(adapter.exact_calls, [])
            scoped_dir = history / "data/ftr-feed/scoped"
            self.assertFalse(scoped_dir.exists() and any(scoped_dir.iterdir()))

    async def test_complete_empty_provider_failure_and_budget_unattempted_are_distinct_truth(self):
        complete_adapter = CompleteEmptyAdapter()
        _, _, complete_evidence = await acquire_scoped(
            request=scoped_request(request_id="truth-empty", windows=(("2026-10-01", "2026-10-05"),), discovery_calls=4),
            policy=load_policy(),
            adapter=complete_adapter,
            run_at=RUN_AT,
        )
        complete = complete_evidence["window_execution"]["w-2026-10-01-2026-10-05"]

        failure_adapter = OneWindowUnavailableAdapter()
        _, _, failure_evidence = await acquire_scoped(
            request=scoped_request(request_id="truth-fail", windows=(("2026-11-01", "2026-11-05"),), discovery_calls=4),
            policy=load_policy(),
            adapter=failure_adapter,
            run_at=RUN_AT,
        )
        failed = failure_evidence["window_execution"]["w-2026-11-01-2026-11-05"]

        _, _, budget_evidence = await acquire_scoped(
            request=scoped_request(request_id="truth-budget", discovery_calls=4),
            policy=load_policy(),
            adapter=CompleteEmptyAdapter(),
            run_at=RUN_AT,
        )
        budget = budget_evidence["window_execution"]["w-2026-11-01-2026-11-05"]

        self.assertEqual((complete["status"], complete["empty"], complete["provider_calls"]), ("succeeded", 4, 4))
        self.assertEqual((failed["status"], failed["failures"], failed["provider_calls"]), ("failed", 4, 4))
        self.assertEqual((budget["status"], budget["reason"], budget["provider_calls"]), ("not_attempted", "budget_unattempted", 0))


if __name__ == "__main__":
    unittest.main()
