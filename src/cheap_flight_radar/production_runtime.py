"""Canonical one-shot production execution wrapper.

The core :mod:`production_radar` runtime intentionally spends exact-search work
only on a bounded competitive shortlist.  This wrapper records destination-free
Flight Deals acquisition so every qualified anomaly candidate remains durable
evidence even when it was not selected for exact completion in this run.

It does not alter Deal qualification or Deal ordering, and it performs no extra
provider queries.  ChatGPT remains the scheduler/orchestrator; this module is
only short-lived execution.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .airfare import AirfareRecord, ProviderResult, is_international_asia_oceania
from .production_radar import (
    ProductionRadar,
    RadarItem,
    RadarRunResult,
    _dedupe_discovery,
    _discovery_sort_key,
    _item_json,
    _load_prior_history,
    _minimum_away_satisfied,
    load_policy,
    write_run_artifacts as _write_run_artifacts,
)
from .providers.gflights import GFlightsAdapter


class RecordingFlightDealsAdapter:
    """Transparent adapter decorator retaining already-fetched discovery rows."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.flight_deal_records: list[AirfareRecord] = []

    async def flight_deals(self, **kwargs: Any) -> ProviderResult:
        result = await self._delegate.flight_deals(**kwargs)
        if result.coverage_state != "failed":
            self.flight_deal_records.extend(result.records)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def retain_pending_qualified_candidates(
    result: RadarRunResult,
    *,
    flight_deal_records: Sequence[AirfareRecord],
    policy: Mapping[str, Any],
) -> RadarRunResult:
    """Retain qualified-but-not-exact-completed Flight Deals as Signals.

    A record is pending only when it meets the same discovery qualification
    predicates as the core runtime and is not already represented by a Deal or
    another Signal.  Pending records remain Signals because exact current fare
    completion has not been performed.
    """

    run_date = datetime.fromisoformat(result.run_at).date()
    horizon_end = run_date + timedelta(days=int(policy["search"]["horizon_days"]))
    retained_ids = {
        item.discovery.record_id
        for item in (*result.deals, *result.signals)
    }
    pending: list[RadarItem] = []
    for record in _dedupe_discovery(flight_deal_records):
        if record.record_id in retained_ids:
            continue
        if not is_international_asia_oceania(record.destination.country):
            continue
        if record.outbound_date:
            try:
                departure = date.fromisoformat(record.outbound_date)
            except ValueError:
                continue
            if departure < run_date or departure > horizon_end:
                continue
        qualified = (
            record.evidence_class == "qualified_round_trip_deal"
            and record.complete_airfare
            and bool(record.current_price_twd)
            and bool(record.typical_price_twd)
            and bool(record.discount_percent)
            and _minimum_away_satisfied(record)
        )
        if not qualified:
            continue
        pending.append(
            RadarItem(
                classification="Signal",
                state="qualified_anomaly_candidate_pending_exact",
                discovery=record,
                exact=None,
                anomaly_source=record.anomaly_authority,
                anomaly_strength_percent=record.discount_percent,
                reason=(
                    "qualified Flight Deals anomaly retained; exact completion "
                    "was not selected under the current run compute budget"
                ),
            )
        )
        retained_ids.add(record.record_id)

    pending.sort(key=lambda item: _discovery_sort_key(item.discovery))
    return RadarRunResult(
        radar_run_id=result.radar_run_id,
        run_at=result.run_at,
        deals=result.deals,
        signals=tuple([*result.signals, *pending]),
        coverage=result.coverage,
        provider_failures=result.provider_failures,
    )


async def run_once(
    *,
    policy: Mapping[str, Any],
    adapter: Any,
    prior_history: Sequence[Any] = (),
    run_at: datetime | None = None,
) -> RadarRunResult:
    recorder = RecordingFlightDealsAdapter(adapter)
    base_result = await ProductionRadar(
        policy=policy,
        adapter=recorder,
        prior_history=prior_history,
    ).run(run_at=run_at)
    return retain_pending_qualified_candidates(
        base_result,
        flight_deal_records=recorder.flight_deal_records,
        policy=policy,
    )


def write_run_artifacts(
    result: RadarRunResult,
    *,
    policy: Mapping[str, Any],
    output_dir: Path,
) -> Mapping[str, str]:
    """Write canonical artifacts, including full Signal rows in run-result."""

    paths = _write_run_artifacts(result, policy=policy, output_dir=output_dir)
    result_path = Path(paths["run_result"])
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["signals"] = [_item_json(item) for item in result.signals]
    payload["signal_states"] = {
        state: sum(1 for item in result.signals if item.state == state)
        for state in sorted({item.state for item in result.signals})
    }
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths


async def _async_main(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    prior_history = _load_prior_history(Path(args.history_dir) if args.history_dir else None)
    result = await run_once(
        policy=policy,
        adapter=GFlightsAdapter(),
        prior_history=prior_history,
    )
    paths = write_run_artifacts(result, policy=policy, output_dir=Path(args.output_dir))
    print(json.dumps({
        "radar_run_id": result.radar_run_id,
        "run_at": result.run_at,
        "deal_count": len(result.deals),
        "signal_count": len(result.signals),
        "signal_states": {
            state: sum(1 for item in result.signals if item.state == state)
            for state in sorted({item.state for item in result.signals})
        },
        "coverage": result.coverage,
        "provider_failures": list(result.provider_failures),
        "paths": paths,
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one canonical short-lived Cheap Flight Radar acquisition"
    )
    parser.add_argument("--policy", default="flight-radar.yaml")
    parser.add_argument(
        "--history-dir",
        default=None,
        help="Optional checked-out history/price-observations ref",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
