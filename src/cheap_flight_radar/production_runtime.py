"""Canonical one-shot production execution wrapper.

The core :mod:`production_radar` runtime intentionally spends exact-search work
only on a bounded competitive shortlist. This wrapper records destination-free
Flight Deals acquisition so every qualified anomaly candidate remains durable
evidence even when it was not selected for exact completion in this run.

It also owns narrowly operational provider hardening for the canonical daily
execution path. Multi-city searches use a client created at process start that
is separate from the high-volume discovery/exact/flexible client. Both clients
retain the same explicit CheapFlightRadar User-Agent, direct connection
(``proxy=None``), locale, and currency through :class:`GFlightsAdapter`; this is
surface budget isolation, not UA/proxy/session rotation, retry, or rate-limit
resetting. Provider failures still fail closed through the underlying adapter.

The wrapper does not alter Deal qualification, Deal ordering, or provider-call
latency semantics. ChatGPT remains the scheduler/orchestrator; this module is
only short-lived execution.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
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


class ProductionExecutionAdapter:
    """Reserve a separate fixed provider client for multi-city request budget.

    The primary and multi-city adapters are both constructed once at process
    start. A primary-client 429 therefore cannot make the library's client-local
    sticky rate-limit state suppress every later multi-city request. The
    dedicated multi-city client does not change IP, proxy, User-Agent, locale,
    currency, or anti-bot behavior; a provider-side refusal still fails closed
    normally.
    """

    def __init__(self, *, primary: Any, multi_city: Any) -> None:
        self._primary = primary
        self._multi_city = multi_city

    async def flight_deals(self, **kwargs: Any) -> ProviderResult:
        return await self._primary.flight_deals(**kwargs)

    async def explore(self, **kwargs: Any) -> ProviderResult:
        return await self._primary.explore(**kwargs)

    async def exact(self, **kwargs: Any) -> ProviderResult:
        return await self._primary.exact(**kwargs)

    async def cheapest_dates(self, **kwargs: Any) -> ProviderResult:
        return await self._primary.cheapest_dates(**kwargs)

    async def open_jaw(self, **kwargs: Any) -> ProviderResult:
        return await self._multi_city.open_jaw(**kwargs)


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
    another Signal. Pending records remain Signals because exact current fare
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


def _replace_run_identity(value: Any, old_id: str, new_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(old_id, new_id).replace(old_id.lower(), new_id.lower())
    if isinstance(value, list):
        return [_replace_run_identity(item, old_id, new_id) for item in value]
    if isinstance(value, dict):
        return {key: _replace_run_identity(item, old_id, new_id) for key, item in value.items()}
    return value


def retag_run_artifacts(
    *,
    output_dir: Path,
    paths: Mapping[str, str],
    run_id_prefix: str,
    execution_mode: str,
) -> Mapping[str, str]:
    """Retag one completed acquisition without re-querying providers.

    Canonical automatic runs retain the ``production-radar-*`` identity. Explicit
    operator reacquisitions are retagged after acquisition so their immutable
    snapshot can coexist on the same local day without entering the canonical
    daily snapshot namespace.
    """

    prefix = run_id_prefix.strip("-.")
    if not prefix or re.search(r"[^A-Za-z0-9._-]", prefix):
        raise ValueError("run_id_prefix must contain only path-safe characters")
    if prefix == "production-radar":
        return paths

    result_path = Path(paths["run_result"])
    manifest_path = Path(paths["publication_manifest"])
    snapshot_path = Path(paths["history_snapshot"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    old_id = str(result.get("radar_run_id") or "")
    if not old_id.startswith("production-radar-"):
        raise ValueError("retag source must be a production-radar run")
    suffix = old_id.removeprefix("production-radar-")
    new_id = f"{prefix}-{suffix}"
    old_safe = re.sub(r"[^A-Za-z0-9._-]+", "-", old_id).strip("-.")
    new_safe = re.sub(r"[^A-Za-z0-9._-]+", "-", new_id).strip("-.")

    transformed_result = _replace_run_identity(result, old_id, new_id)
    transformed_manifest = _replace_run_identity(manifest, old_id, new_id)
    transformed_snapshot = _replace_run_identity(snapshot, old_id, new_id)
    history_rel = Path(str(manifest["history_snapshot_path"]))
    if history_rel.name != f"{old_safe}.json":
        raise ValueError("history snapshot path does not match source run identity")
    new_history_rel = history_rel.with_name(f"{new_safe}.json").as_posix()
    transformed_manifest["history_snapshot_path"] = new_history_rel
    transformed_manifest["execution_mode"] = execution_mode
    transformed_result["execution_mode"] = execution_mode

    new_snapshot_path = snapshot_path.with_name(f"{new_safe}.json")
    new_manifest_path = manifest_path.with_name(f"{new_id}.json")
    new_snapshot_path.write_text(
        json.dumps(transformed_snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    new_manifest_path.write_text(
        json.dumps(transformed_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    result_path.write_text(
        json.dumps(transformed_result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if new_snapshot_path != snapshot_path:
        snapshot_path.unlink()
    if new_manifest_path != manifest_path:
        manifest_path.unlink()
    return {
        "history_snapshot": new_snapshot_path.as_posix(),
        "publication_manifest": new_manifest_path.as_posix(),
        "run_result": result_path.as_posix(),
    }


async def _async_main(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    prior_history = _load_prior_history(Path(args.history_dir) if args.history_dir else None)
    adapter = ProductionExecutionAdapter(
        primary=GFlightsAdapter(),
        multi_city=GFlightsAdapter(),
    )
    result = await run_once(
        policy=policy,
        adapter=adapter,
        prior_history=prior_history,
    )
    paths = write_run_artifacts(result, policy=policy, output_dir=Path(args.output_dir))
    if args.run_id_prefix != "production-radar":
        paths = retag_run_artifacts(
            output_dir=Path(args.output_dir),
            paths=paths,
            run_id_prefix=args.run_id_prefix,
            execution_mode=args.execution_mode,
        )
    summary = json.loads(Path(paths["run_result"]).read_text(encoding="utf-8"))
    print(json.dumps({
        "radar_run_id": summary["radar_run_id"],
        "run_at": summary["run_at"],
        "deal_count": summary["deal_count"],
        "signal_count": summary["signal_count"],
        "signal_states": summary["signal_states"],
        "coverage": summary["coverage"],
        "provider_failures": summary["provider_failures"],
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
    parser.add_argument(
        "--run-id-prefix",
        default="production-radar",
        help="Path-safe run identity prefix; operator workflows use a request-specific prefix",
    )
    parser.add_argument(
        "--execution-mode",
        default="canonical_daily",
        help="Provenance label embedded in non-canonical retagged run artifacts",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
