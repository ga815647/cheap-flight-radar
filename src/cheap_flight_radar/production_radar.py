"""Anomaly-first production Radar runtime.

ChatGPT remains the scheduler/orchestrator.  This module is deterministic
short-lived execution: destination-free Flight Deals acquisition, selective
exact completion, anomaly qualification, immutable evidence construction, and
publication-manifest construction.  It owns no schedule, queue, daemon, or
long-lived state service.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import yaml

from .airfare import AirfareLeg, AirfareRecord, ProviderResult, is_international_asia_oceania, market_slice
from .anomaly_truth import AnomalyEvidence, formal_deal_sort_key, select_anomaly_truth
from .price_history import (
    FareObservation,
    build_snapshot,
    compare_with_history,
    snapshot_from_json,
    snapshot_repository_path,
    snapshot_to_json,
)
from .providers.gflights import GFlightsAdapter
from .models import OriginSweepRequest, SearchRequest
from .source_router import build_source_plan

PROJECT_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_DEAL_DURATION_ANCHORS_DAYS = (3, 7, 12)
FORMAL_DEAL_MINIMUM_AWAY_HOURS = 24
MARKETS = ("japan", "korea", "china", "other_asia_oceania")


@dataclass(frozen=True)
class RadarItem:
    classification: str
    state: str
    discovery: AirfareRecord
    exact: AirfareRecord | None
    anomaly_source: str | None
    anomaly_strength_percent: float | None
    reason: str
    observation_id: str | None = None

    @property
    def current_complete_airfare_twd(self) -> int | None:
        if self.exact is not None:
            return self.exact.current_price_twd
        return self.discovery.current_price_twd if self.discovery.complete_airfare else None


@dataclass(frozen=True)
class RadarRunResult:
    radar_run_id: str
    run_at: str
    deals: tuple[RadarItem, ...]
    signals: tuple[RadarItem, ...]
    coverage: Mapping[str, Any]
    provider_failures: tuple[Mapping[str, str], ...]


def load_policy(path: Path) -> Mapping[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError("flight-radar policy must be a mapping")
    return raw


def _local_datetime(value: datetime | None = None) -> datetime:
    current = value or datetime.now(PROJECT_TIMEZONE)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("run_at must be timezone-aware")
    return current.astimezone(PROJECT_TIMEZONE)


def _safe_run_id(run_at: datetime) -> str:
    return f"production-radar-{run_at:%Y%m%dT%H%M%S%z}"


def _trip_duration_days(record: AirfareRecord) -> int | None:
    if not record.outbound_date or not record.return_date:
        return None
    try:
        return (date.fromisoformat(record.return_date) - date.fromisoformat(record.outbound_date)).days
    except ValueError:
        return None


def _minimum_away_satisfied(record: AirfareRecord, minimum_hours: int = FORMAL_DEAL_MINIMUM_AWAY_HOURS) -> bool:
    days = _trip_duration_days(record)
    if days is None:
        return False
    return days * 24 > minimum_hours


def _candidate_key(record: AirfareRecord) -> tuple[str, str, str | None, str | None]:
    return (record.origin.iata, record.destination.iata, record.outbound_date, record.return_date)


def _discovery_sort_key(record: AirfareRecord) -> tuple[float, float, str]:
    return (
        -float(record.discount_percent or 0.0),
        float(record.current_price_twd or 10**12),
        record.record_id,
    )


def _dedupe_discovery(records: Sequence[AirfareRecord]) -> list[AirfareRecord]:
    by_key: dict[tuple[str, str, str | None, str | None], AirfareRecord] = {}
    for record in records:
        key = _candidate_key(record)
        incumbent = by_key.get(key)
        if incumbent is None or _discovery_sort_key(record) < _discovery_sort_key(incumbent):
            by_key[key] = record
    return sorted(by_key.values(), key=_discovery_sort_key)


def _select_for_revalidation(records: Sequence[AirfareRecord], limit: int) -> tuple[AirfareRecord, ...]:
    if limit <= 0:
        return ()
    ranked = list(sorted(records, key=_discovery_sort_key))
    selected: list[AirfareRecord] = []
    seen_ids: set[str] = set()

    def add(record: AirfareRecord) -> None:
        if record.record_id not in seen_ids and len(selected) < limit:
            selected.append(record)
            seen_ids.add(record.record_id)

    for origin in sorted({item.origin.iata for item in ranked}):
        candidate = next((item for item in ranked if item.origin.iata == origin), None)
        if candidate:
            add(candidate)
    for market in MARKETS:
        candidate = next((item for item in ranked if market_slice(item.destination.country) == market), None)
        if candidate:
            add(candidate)
    for record in ranked:
        add(record)
    return tuple(selected)


def _load_prior_history(history_dir: Path | None) -> tuple[FareObservation, ...]:
    if history_dir is None:
        return ()
    root = history_dir / "data" / "price-history"
    if not root.exists():
        return ()
    observations: list[FareObservation] = []
    for path in sorted(root.rglob("*.json")):
        snapshot = snapshot_from_json(path.read_text(encoding="utf-8"))
        observations.extend(snapshot.observations)
    return tuple(observations)


def _observation_id(run_id: str, exact: AirfareRecord) -> str:
    route = f"{exact.origin.iata}-{exact.destination.iata}"
    dep = exact.outbound_date or "unknown"
    ret = exact.return_date or "oneway"
    suffix = exact.record_id.removeprefix("gf-")[:10]
    return f"{run_id}-{route}-{dep}-{ret}-{suffix}".lower()


def _to_observation(run_id: str, exact: AirfareRecord) -> FareObservation:
    if exact.current_price_twd is None or exact.outbound_date is None:
        raise ValueError("history observation requires complete current fare and departure date")
    trip_type = "round_trip" if exact.is_round_trip or exact.reproducible_search.get("return_date") else "one_way"
    if exact.surface == "open_jaw":
        trip_type = "multi_city"
    return FareObservation(
        observation_id=_observation_id(run_id, exact),
        radar_run_id=run_id,
        observed_at=exact.observed_at,
        origin=exact.origin.iata,
        destination=exact.destination.iata,
        departure_date=exact.outbound_date,
        trip_type=trip_type,
        normalized_twd_price=exact.current_price_twd,
        fare_scope="usable_complete_trip",
        availability_state="available",
        source_id="gflights_google_exact",
        source_url=exact.booking_url or exact.evidence_url,
        verification_state=exact.verification_state,
        original_price=exact.current_price_twd,
        original_currency="TWD",
    )


def _record_json(record: AirfareRecord | None) -> Mapping[str, Any] | None:
    return None if record is None else asdict(record)


def _item_json(item: RadarItem) -> Mapping[str, Any]:
    return {
        "classification": item.classification,
        "state": item.state,
        "reason": item.reason,
        "observation_id": item.observation_id,
        "anomaly_source": item.anomaly_source,
        "anomaly_strength_percent": item.anomaly_strength_percent,
        "current_complete_airfare_twd": item.current_complete_airfare_twd,
        "discovery": _record_json(item.discovery),
        "exact": _record_json(item.exact),
    }


def _profile_for_record(record: AirfareRecord) -> str:
    market = market_slice(record.destination.country)
    return market if market in {"japan", "korea", "china"} else "world"


def _market_coverage_template() -> dict[str, dict[str, int]]:
    return {market: {"discovered": 0, "qualified": 0, "revalidated": 0, "deals": 0} for market in MARKETS}


class ProductionRadar:
    def __init__(self, *, policy: Mapping[str, Any], adapter: GFlightsAdapter, prior_history: Sequence[FareObservation] = ()) -> None:
        self.policy = policy
        self.adapter = adapter
        self.prior_history = tuple(prior_history)
        self.anomaly_priority = tuple(str(item) for item in policy["source_routing"]["anomaly_truth_priority"])

    def _external_truth(self, discovery: AirfareRecord, exact: AirfareRecord) -> AnomalyEvidence | None:
        evidences: list[AnomalyEvidence] = []
        if discovery.anomaly_authority == "google_flight_deals":
            evidences.append(
                AnomalyEvidence(
                    source="google_flight_deals",
                    current_price_twd=float(exact.current_price_twd or 0),
                    typical_price_twd=float(discovery.typical_price_twd) if discovery.typical_price_twd is not None else None,
                    discount_percent=None,
                    reproducible=bool(discovery.reproducible_search and exact.reproducible_search),
                    qualified=(
                        discovery.evidence_class == "qualified_round_trip_deal"
                        and exact.verification_state == "revalidated"
                        and exact.complete_airfare
                    ),
                )
            )
        if exact.anomaly_authority == "google_flights_exact_price_insight":
            evidences.append(
                AnomalyEvidence(
                    source="google_flights_exact_price_insight",
                    current_price_twd=float(exact.current_price_twd or 0),
                    typical_price_twd=float(exact.typical_price_twd) if exact.typical_price_twd else None,
                    discount_percent=exact.discount_percent,
                    reproducible=bool(exact.reproducible_search),
                    qualified=exact.verification_state == "revalidated",
                )
            )
        return select_anomaly_truth(evidences, self.anomaly_priority)

    def _history_truth(self, observation: FareObservation) -> AnomalyEvidence | None:
        if not self.prior_history:
            return None
        comparison = compare_with_history(observation, self.prior_history, self.policy["price_history"])
        if comparison.anomaly_label != "historical_floor":
            return None
        if comparison.selected_baseline_twd is None or comparison.percent_below_baseline is None:
            return None
        if comparison.percent_below_baseline <= 0:
            return None
        evidence = AnomalyEvidence(
            source="own_price_history",
            current_price_twd=float(observation.normalized_twd_price or 0),
            typical_price_twd=float(comparison.selected_baseline_twd),
            discount_percent=None,
            reproducible=True,
            qualified=True,
            evidence_kind="own_price_history",
        )
        return select_anomaly_truth((evidence,), self.anomaly_priority)

    async def run(self, *, run_at: datetime | None = None) -> RadarRunResult:
        local_run_at = _local_datetime(run_at)
        run_id = _safe_run_id(local_run_at)
        run_date = local_run_at.date()
        origins = tuple(str(item) for item in self.policy["search"]["origin_airports"])
        horizon_days = int(self.policy["search"]["horizon_days"])
        candidate_limit = min(
            int(self.policy["search"]["deep_search_candidate_limit"]),
            int(self.policy["search"]["final_shortlist_limit"]),
        )
        origin_coverage: dict[str, dict[str, Any]] = {}
        market_coverage = _market_coverage_template()
        provider_failures: list[Mapping[str, str]] = []
        completion_seed_records: list[AirfareRecord] = []
        weak_signals: list[RadarItem] = []

        for origin in origins:
            origin_records: list[AirfareRecord] = []
            origin_errors: list[str] = []
            sweep_plan = build_source_plan(
                OriginSweepRequest(
                    origin=origin,
                    horizon_start=run_date.isoformat(),
                    horizon_days=horizon_days,
                    destination_scope="asia_oceania",
                    currency="TWD",
                ),
                self.policy,
                {},
            )
            if (
                sweep_plan.coverage_state != "planned"
                or not sweep_plan.entries
                or sweep_plan.entries[0].provider != "gflights_google_flight_deals"
            ):
                reason = sweep_plan.fallback_reason or "Flight Deals primary is not executable under current SSOT"
                origin_coverage[origin] = {
                    "status": "failed",
                    "returned_flight_deals": 0,
                    "asia_oceania_records": 0,
                    "qualified_deals": 0,
                    "explore_seeds": 0,
                    "errors": [reason],
                }
                provider_failures.append({"origin": origin, "surface": "source_router", "error": reason})
                continue

            for duration_days in DEFAULT_DEAL_DURATION_ANCHORS_DAYS:
                anchor_departure = run_date + timedelta(days=14)
                result = await self.adapter.flight_deals(
                    origin=origin,
                    anchor_departure=anchor_departure.isoformat(),
                    anchor_return=(anchor_departure + timedelta(days=duration_days)).isoformat(),
                )
                if result.coverage_state == "failed":
                    message = result.error or "provider failure"
                    origin_errors.append(message)
                    provider_failures.append({"origin": origin, "surface": "flight_deals", "error": message})
                else:
                    origin_records.extend(result.records)

            region_records: list[AirfareRecord] = []
            qualified_records: list[AirfareRecord] = []
            horizon_end = run_date + timedelta(days=horizon_days)
            for record in _dedupe_discovery(origin_records):
                if not is_international_asia_oceania(record.destination.country):
                    continue
                if record.outbound_date:
                    try:
                        departure = date.fromisoformat(record.outbound_date)
                    except ValueError:
                        continue
                    if departure < run_date or departure > horizon_end:
                        continue
                region_records.append(record)
                market = market_slice(record.destination.country)
                market_coverage[market]["discovered"] += 1
                qualified = (
                    record.evidence_class == "qualified_round_trip_deal"
                    and record.complete_airfare
                    and bool(record.current_price_twd)
                    and bool(record.typical_price_twd)
                    and bool(record.discount_percent)
                    and _minimum_away_satisfied(record)
                )
                if qualified:
                    qualified_records.append(record)
                    completion_seed_records.append(record)
                    market_coverage[market]["qualified"] += 1
                else:
                    if record.complete_airfare and record.current_price_twd and record.outbound_date and record.return_date:
                        completion_seed_records.append(record)
                    weak_signals.append(
                        RadarItem(
                            classification="Signal",
                            state="weak_seed",
                            discovery=record,
                            exact=None,
                            anomaly_source=record.anomaly_authority,
                            anomaly_strength_percent=record.discount_percent,
                            reason="Flight Deals result did not satisfy complete qualified Deal evidence",
                        )
                    )

            explore_count = 0
            if not qualified_records:
                explore = await self.adapter.explore(origin=origin)
                if explore.coverage_state == "failed":
                    message = explore.error or "provider failure"
                    provider_failures.append({"origin": origin, "surface": "explore", "error": message})
                    origin_errors.append(f"explore: {message}")
                else:
                    for record in explore.records:
                        if not is_international_asia_oceania(record.destination.country):
                            continue
                        explore_count += 1
                        market_coverage[market_slice(record.destination.country)]["discovered"] += 1
                        if record.complete_airfare and record.current_price_twd and record.outbound_date and record.return_date:
                            completion_seed_records.append(record)
                        weak_signals.append(
                            RadarItem(
                                classification="Signal",
                                state="weak_seed",
                                discovery=record,
                                exact=None,
                                anomaly_source=None,
                                anomaly_strength_percent=None,
                                reason="Google Explore seed has current route/price evidence but no qualified anomaly truth",
                            )
                        )

            origin_coverage[origin] = {
                "status": "failed" if not origin_records and origin_errors else "attempted",
                "returned_flight_deals": len(origin_records),
                "asia_oceania_records": len(region_records),
                "qualified_deals": len(qualified_records),
                "explore_seeds": explore_count,
                "errors": origin_errors,
            }

        candidates = _select_for_revalidation(_dedupe_discovery(completion_seed_records), candidate_limit)
        selected_record_ids = {item.record_id for item in candidates}
        deals: list[RadarItem] = []
        exact_signals: list[RadarItem] = []

        for discovery in candidates:
            if not discovery.outbound_date or not discovery.return_date:
                continue
            exact_plan = build_source_plan(
                SearchRequest(
                    profile=_profile_for_record(discovery),
                    search_stage="round_trip_benchmark",
                    origin=discovery.origin.iata,
                    destination=discovery.destination.iata,
                    outbound_date=discovery.outbound_date,
                    return_date=discovery.return_date,
                    destination_country=discovery.destination.country,
                ),
                self.policy,
                {},
            )
            if (
                exact_plan.coverage_state != "planned"
                or not exact_plan.entries
                or exact_plan.entries[0].provider != "gflights_google_exact"
            ):
                reason = exact_plan.fallback_reason or "Google exact primary is not executable under current SSOT"
                provider_failures.append({
                    "origin": discovery.origin.iata,
                    "surface": "source_router_exact",
                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                    "error": reason,
                })
                exact_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, f"source-router blocked exact completion: {reason}"))
                continue

            exact_result = await self.adapter.exact(
                origin=discovery.origin.iata,
                destination=discovery.destination.iata,
                departure_date=discovery.outbound_date,
                return_date=discovery.return_date,
            )
            if exact_result.coverage_state != "complete" or not exact_result.records:
                message = exact_result.error or exact_result.coverage_state
                provider_failures.append({
                    "origin": discovery.origin.iata,
                    "surface": "exact",
                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                    "error": message,
                })
                exact_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, f"exact revalidation failed closed: {message}"))
                continue

            exact = exact_result.records[0]
            if exact.current_price_twd is None or not exact.complete_airfare:
                exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, discovery.anomaly_authority, None, "exact surface did not expose a complete positive current airfare"))
                continue

            observation = _to_observation(run_id, exact)
            truth = self._external_truth(discovery, exact) or self._history_truth(observation)
            market = market_slice(discovery.destination.country)
            market_coverage[market]["revalidated"] += 1
            if truth is None or not truth.is_usable_truth():
                exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, None, None, "current exact airfare revalidated, but no qualified positive anomaly truth remained", observation.observation_id))
                continue
            discount = truth.normalized_discount_percent()
            if discount is None or discount <= 0:
                exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, truth.source, discount, "exact current airfare is no longer below the selected anomaly baseline", observation.observation_id))
                continue
            deals.append(RadarItem("Deal", "deal", discovery, exact, truth.source, discount, "qualified anomaly authority plus current exact complete airfare", observation.observation_id))
            market_coverage[market]["deals"] += 1

        deals.sort(
            key=lambda item: formal_deal_sort_key(
                AnomalyEvidence(
                    source=item.anomaly_source or "",
                    current_price_twd=float(item.current_complete_airfare_twd or 0),
                    discount_percent=item.anomaly_strength_percent,
                    reproducible=True,
                    qualified=True,
                )
            )
        )
        signal_by_key: dict[tuple[Any, ...], RadarItem] = {}
        for item in [*exact_signals, *(item for item in weak_signals if item.discovery.record_id not in selected_record_ids)]:
            key = (item.discovery.record_id, item.state, item.reason, item.exact.record_id if item.exact else None)
            signal_by_key.setdefault(key, item)
        coverage = {
            "origins": origin_coverage,
            "markets": market_coverage,
            "origin_attempt_required": True,
            "all_origins_attempted": all(origin in origin_coverage for origin in origins),
            "deal_acquisition_surface": "google_flight_deals",
            "exact_completion_surface": "google_flights_exact",
            "destination_scope": "asia_oceania",
            "fixed_watch_is_deal_coverage_authority": False,
        }
        return RadarRunResult(run_id, local_run_at.isoformat(), tuple(deals), tuple(signal_by_key.values()), coverage, tuple(provider_failures))

    async def revalidate_open_jaw(self, *, legs: Sequence[tuple[str, str, str]]) -> ProviderResult:
        if len(legs) < 2:
            raise ValueError("open-jaw exact completion requires at least two legs")
        first_origin, first_destination, first_date = legs[0]
        plan = build_source_plan(
            SearchRequest(
                profile="world",
                search_stage="round_trip_benchmark",
                origin=first_origin,
                destination=first_destination,
                outbound_date=first_date,
                return_date=legs[-1][2],
                open_jaw_required=True,
            ),
            self.policy,
            {},
        )
        if plan.coverage_state != "planned" or not plan.entries or plan.entries[0].provider != "gflights_google_exact":
            return ProviderResult("source_router", "open_jaw", "failed", error=plan.fallback_reason or "Google exact open-jaw route is not selected by SSOT")
        return await self.adapter.open_jaw(legs=legs)


def build_run_artifacts(result: RadarRunResult, *, policy: Mapping[str, Any]) -> tuple[Any, Mapping[str, Any]]:
    run_at = datetime.fromisoformat(result.run_at)
    observations_by_id: dict[str, FareObservation] = {}
    for item in (*result.deals, *result.signals):
        if item.exact is None or item.current_complete_airfare_twd is None:
            continue
        observation = _to_observation(result.radar_run_id, item.exact)
        observations_by_id[observation.observation_id] = observation
    snapshot = build_snapshot(result.radar_run_id, run_at, tuple(observations_by_id.values()))
    manifest: Mapping[str, Any] = {
        "schema_version": 2,
        "radar_run_id": result.radar_run_id,
        "run_at": result.run_at,
        "history_snapshot_path": snapshot_repository_path(snapshot),
        "deals": [_item_json(item) for item in result.deals],
        "signals": [_item_json(item) for item in result.signals],
        "coverage": result.coverage,
        "provider_failures": list(result.provider_failures),
        "anomaly_truth_priority": list(policy["source_routing"]["anomaly_truth_priority"]),
        "formal_deal_order": "relative_anomaly_strength_desc_then_current_complete_airfare_twd_asc",
        "legacy_views_status": "diagnostic_or_transition_only",
    }
    return snapshot, manifest


def write_run_artifacts(result: RadarRunResult, *, policy: Mapping[str, Any], output_dir: Path) -> Mapping[str, str]:
    snapshot, manifest = build_run_artifacts(result, policy=policy)
    history_path = output_dir / "history" / Path(snapshot_repository_path(snapshot))
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(snapshot_to_json(snapshot), encoding="utf-8")
    manifest_path = output_dir / "publication" / "runs" / f"{result.radar_run_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result_path = output_dir / "run-result.json"
    result_path.write_text(
        json.dumps(
            {
                "radar_run_id": result.radar_run_id,
                "run_at": result.run_at,
                "deal_count": len(result.deals),
                "signal_count": len(result.signals),
                "deals": [_item_json(item) for item in result.deals],
                "coverage": result.coverage,
                "provider_failures": list(result.provider_failures),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return {
        "history_snapshot": history_path.as_posix(),
        "publication_manifest": manifest_path.as_posix(),
        "run_result": result_path.as_posix(),
    }


async def _async_main(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    prior_history = _load_prior_history(Path(args.history_dir) if args.history_dir else None)
    runtime = ProductionRadar(policy=policy, adapter=GFlightsAdapter(), prior_history=prior_history)
    result = await runtime.run()
    paths = write_run_artifacts(result, policy=policy, output_dir=Path(args.output_dir))
    print(json.dumps({
        "radar_run_id": result.radar_run_id,
        "run_at": result.run_at,
        "deal_count": len(result.deals),
        "signal_count": len(result.signals),
        "coverage": result.coverage,
        "provider_failures": list(result.provider_failures),
        "paths": paths,
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one short-lived production Cheap Flight Radar acquisition")
    parser.add_argument("--policy", default="flight-radar.yaml")
    parser.add_argument("--history-dir", default=None, help="Optional checked-out history/price-observations ref")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
