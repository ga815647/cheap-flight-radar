"""Anomaly-first production Radar runtime.

ChatGPT remains the scheduler/orchestrator. This module is deterministic,
short-lived execution only: destination-free acquisition, bounded endpoint
expansion, exact completion, anomaly qualification, immutable evidence, and
publication-manifest construction. It owns no schedule, queue, daemon, or
long-lived state service.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
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
from .operational_status import derive_provider_health, reconcile_provider_failures
from .source_router import build_source_plan

PROJECT_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_DEAL_DURATION_ANCHORS_DAYS = (3, 7, 12)
FORMAL_DEAL_MINIMUM_AWAY_HOURS = 24
MARKETS = ("japan", "korea", "china", "other_asia_oceania")
EXECUTION_SURFACES = (
    "flight_deals",
    "explore",
    "conventional_exact",
    "flexible_dates",
    "mixed_taiwan_return",
    "open_jaw",
)


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
    anomaly_baseline_twd: int | None = None
    anomaly_scope: str | None = None

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


def _clock_datetime(leg: AirfareLeg, value: str | None, *, arrival: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if "T" in value or " " in value:
            return parsed
    except ValueError:
        pass
    try:
        parsed_time = time.fromisoformat(value)
        result = datetime.combine(date.fromisoformat(leg.date), parsed_time)
    except ValueError:
        return None
    if arrival and leg.departure_time:
        departure = _clock_datetime(leg, leg.departure_time)
        if departure is not None and result <= departure:
            result += timedelta(days=1)
    return result


def _actual_away_hours(record: AirfareRecord) -> float | None:
    if not record.provider_segments_cover_complete_trip or len(record.legs) < 2:
        return None
    if record.surface == "open_jaw":
        arrival_leg = record.legs[0]
        departure_leg = record.legs[-1]
    else:
        arrival_index = next(
            (index for index, leg in enumerate(record.legs) if leg.destination == record.destination.iata),
            None,
        )
        if arrival_index is None:
            return None
        departure_index = next(
            (
                index
                for index, leg in enumerate(record.legs[arrival_index + 1 :], start=arrival_index + 1)
                if leg.origin == record.destination.iata
            ),
            None,
        )
        if departure_index is None:
            return None
        arrival_leg = record.legs[arrival_index]
        departure_leg = record.legs[departure_index]
    arrival = _clock_datetime(arrival_leg, arrival_leg.arrival_time, arrival=True)
    departure = _clock_datetime(departure_leg, departure_leg.departure_time)
    if arrival is None or departure is None:
        return None
    if arrival_leg.destination != departure_leg.origin and (arrival.tzinfo is None or departure.tzinfo is None):
        return None
    try:
        seconds = (departure - arrival).total_seconds()
    except TypeError:
        return None
    return seconds / 3600.0


def _minimum_away_satisfied(record: AirfareRecord, minimum_hours: int = FORMAL_DEAL_MINIMUM_AWAY_HOURS) -> bool:
    actual = _actual_away_hours(record)
    if actual is not None:
        return actual > minimum_hours
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


def _destination_floor_sort_key(record: AirfareRecord) -> tuple[float, float, str]:
    return (
        float(record.current_price_twd or 10**12),
        -float(record.discount_percent or 0.0),
        record.record_id,
    )


def _dedupe_destination_floor(records: Sequence[AirfareRecord]) -> list[AirfareRecord]:
    """Keep the cheapest complete current fare as the destination representative."""
    by_destination: dict[str, AirfareRecord] = {}
    for record in records:
        destination = record.destination.iata
        incumbent = by_destination.get(destination)
        if incumbent is None or _destination_floor_sort_key(record) < _destination_floor_sort_key(incumbent):
            by_destination[destination] = record
    return sorted(by_destination.values(), key=_discovery_sort_key)


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
        "anomaly_baseline_twd": item.anomaly_baseline_twd,
        "anomaly_scope": item.anomaly_scope,
        "current_complete_airfare_twd": item.current_complete_airfare_twd,
        "discovery": _record_json(item.discovery),
        "exact": _record_json(item.exact),
    }


def _profile_for_record(record: AirfareRecord) -> str:
    market = market_slice(record.destination.country)
    return market if market in {"japan", "korea", "china"} else "world"


def _market_coverage_template() -> dict[str, dict[str, int]]:
    return {market: {"discovered": 0, "qualified": 0, "revalidated": 0, "deals": 0} for market in MARKETS}


def _execution_template() -> dict[str, dict[str, int]]:
    return {
        surface: {"attempts": 0, "records": 0, "successes": 0, "empty": 0, "failures": 0, "unsupported": 0}
        for surface in EXECUTION_SURFACES
    }


def _count_provider_result(execution: dict[str, dict[str, int]], surface: str, result: ProviderResult) -> None:
    counter = execution[surface]
    counter["records"] += len(result.records)
    if result.coverage_state == "complete" and result.records:
        counter["successes"] += 1
    elif result.coverage_state == "failed":
        counter["failures"] += 1
    elif result.coverage_state == "unsupported":
        counter["unsupported"] += 1
    else:
        counter["empty"] += 1


def _best_flexible_record(records: Sequence[AirfareRecord], run_date: date, horizon_end: date) -> AirfareRecord | None:
    eligible: list[AirfareRecord] = []
    for record in records:
        if not record.outbound_date or not record.return_date or not record.current_price_twd:
            continue
        try:
            departure = date.fromisoformat(record.outbound_date)
        except ValueError:
            continue
        if departure < run_date or departure > horizon_end or not _minimum_away_satisfied(record):
            continue
        eligible.append(record)
    if not eligible:
        return None
    return min(eligible, key=lambda item: (item.current_price_twd or 10**12, item.outbound_date or "", item.record_id))


def _open_jaw_exit(seed: AirfareRecord, pool: Sequence[AirfareRecord]) -> AirfareRecord | None:
    distinct = [item for item in pool if item.destination.iata != seed.destination.iata]
    if not distinct:
        return None
    same_country = [item for item in distinct if item.destination.country == seed.destination.country]
    if same_country:
        return sorted(same_country, key=_discovery_sort_key)[0]
    same_market = [item for item in distinct if market_slice(item.destination.country) == market_slice(seed.destination.country)]
    if same_market:
        return sorted(same_market, key=_discovery_sort_key)[0]
    return sorted(distinct, key=_discovery_sort_key)[0]


class ProductionRadar:
    def __init__(self, *, policy: Mapping[str, Any], adapter: GFlightsAdapter, prior_history: Sequence[FareObservation] = ()) -> None:
        self.policy = policy
        self.adapter = adapter
        self.prior_history = tuple(prior_history)
        self.anomaly_priority = tuple(str(item) for item in policy["source_routing"]["anomaly_truth_priority"])

    def _external_truth(
        self,
        discovery: AirfareRecord,
        exact: AirfareRecord,
        destination_baseline: AirfareRecord | None,
    ) -> AnomalyEvidence | None:
        evidences: list[AnomalyEvidence] = []
        flight_deals_baseline = destination_baseline
        if flight_deals_baseline is None and discovery.anomaly_authority == "google_flight_deals":
            flight_deals_baseline = discovery
        if (
            flight_deals_baseline is not None
            and flight_deals_baseline.anomaly_authority == "google_flight_deals"
            and flight_deals_baseline.typical_price_twd is not None
        ):
            evidences.append(
                AnomalyEvidence(
                    source="google_flight_deals",
                    current_price_twd=float(exact.current_price_twd or 0),
                    typical_price_twd=float(flight_deals_baseline.typical_price_twd),
                    discount_percent=None,
                    reproducible=bool(flight_deals_baseline.reproducible_search and exact.reproducible_search),
                    qualified=(
                        flight_deals_baseline.evidence_class == "qualified_round_trip_deal"
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

    def _exact_plan(self, discovery: AirfareRecord, departure_date: str, return_date: str) -> bool:
        plan = build_source_plan(
            SearchRequest(
                profile=_profile_for_record(discovery),
                search_stage="round_trip_benchmark",
                origin=discovery.origin.iata,
                destination=discovery.destination.iata,
                outbound_date=departure_date,
                return_date=return_date,
                destination_country=discovery.destination.country,
            ),
            self.policy,
            {},
        )
        return bool(
            plan.coverage_state == "planned"
            and plan.entries
            and plan.entries[0].provider == "gflights_google_exact"
        )

    async def run(self, *, run_at: datetime | None = None) -> RadarRunResult:
        local_run_at = _local_datetime(run_at)
        run_id = _safe_run_id(local_run_at)
        run_date = local_run_at.date()
        search_policy = self.policy["search"]
        origins = tuple(str(item) for item in search_policy["origin_airports"])
        horizon_days = int(search_policy["horizon_days"])
        deep_limit = int(search_policy["deep_search_candidate_limit"])
        final_limit = int(search_policy["final_shortlist_limit"])
        horizon_end = run_date + timedelta(days=horizon_days)
        flexible_months = max(1, min(4, (horizon_days + 29) // 30))
        expansion_variant_limit = min(max(1, len(origins)), max(0, deep_limit))

        origin_coverage: dict[str, dict[str, Any]] = {}
        market_coverage = _market_coverage_template()
        execution = _execution_template()
        provider_failures: list[Mapping[str, str]] = []
        completion_seed_records: list[AirfareRecord] = []
        destination_baselines: dict[str, AirfareRecord] = {}
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
                execution["flight_deals"]["unsupported"] += 1
                continue

            for duration_days in DEFAULT_DEAL_DURATION_ANCHORS_DAYS:
                anchor_departure = run_date + timedelta(days=14)
                execution["flight_deals"]["attempts"] += 1
                result = await self.adapter.flight_deals(
                    origin=origin,
                    anchor_departure=anchor_departure.isoformat(),
                    anchor_return=(anchor_departure + timedelta(days=duration_days)).isoformat(),
                )
                _count_provider_result(execution, "flight_deals", result)
                if result.coverage_state == "failed":
                    message = result.error or "provider failure"
                    origin_errors.append(message)
                    provider_failures.append({"origin": origin, "surface": "flight_deals", "error": message})
                else:
                    origin_records.extend(result.records)

            region_records: list[AirfareRecord] = []
            qualified_records: list[AirfareRecord] = []
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
                if record.anomaly_authority == "google_flight_deals" and record.typical_price_twd:
                    incumbent_baseline = destination_baselines.get(record.destination.iata)
                    if incumbent_baseline is None or int(record.typical_price_twd) < int(incumbent_baseline.typical_price_twd or 10**12):
                        destination_baselines[record.destination.iata] = record
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
                    market_coverage[market]["qualified"] += 1
                else:
                    weak_signals.append(
                        RadarItem(
                            "Signal",
                            "weak_seed",
                            record,
                            None,
                            record.anomaly_authority,
                            record.discount_percent,
                            "Flight Deals result did not satisfy complete qualified Deal evidence",
                        )
                    )
                if record.current_price_twd and record.outbound_date:
                    completion_seed_records.append(record)

            explore_count = 0
            execution["explore"]["attempts"] += 1
            explore = await self.adapter.explore(origin=origin)
            _count_provider_result(execution, "explore", explore)
            if explore.coverage_state == "failed":
                message = explore.error or "provider failure"
                provider_failures.append({"origin": origin, "surface": "explore", "error": message})
                origin_errors.append(f"explore: {message}")
            else:
                for record in explore.records:
                    if not is_international_asia_oceania(record.destination.country):
                        continue
                    if record.outbound_date:
                        try:
                            departure = date.fromisoformat(record.outbound_date)
                        except ValueError:
                            continue
                        if departure < run_date or departure > horizon_end:
                            continue
                    explore_count += 1
                    market_coverage[market_slice(record.destination.country)]["discovered"] += 1
                    if record.current_price_twd and record.outbound_date:
                        completion_seed_records.append(record)
                    weak_signals.append(
                        RadarItem(
                            "Signal",
                            "weak_seed",
                            record,
                            None,
                            None,
                            None,
                            "Google Explore seed has endpoint evidence but no qualified anomaly truth",
                        )
                    )

            if not origin_records and explore_count == 0:
                origin_status = "failed"
            elif not origin_records:
                origin_status = "degraded"
            else:
                origin_status = "attempted"
            origin_coverage[origin] = {
                "status": origin_status,
                "returned_flight_deals": len(origin_records),
                "asia_oceania_records": len(region_records),
                "qualified_deals": len(qualified_records),
                "explore_seeds": explore_count,
                "errors": origin_errors,
            }

        deduped_seed_pool = _dedupe_discovery(completion_seed_records)
        destination_representatives = _select_for_revalidation(
            _dedupe_destination_floor(
                [item for item in deduped_seed_pool if item.complete_airfare and item.current_price_twd and item.return_date]
            ),
            deep_limit,
        )
        expansion_seed_pool = _select_for_revalidation(deduped_seed_pool, deep_limit)
        selected_record_ids = {item.record_id for item in (*destination_representatives, *expansion_seed_pool)}

        exact_signals: list[RadarItem] = []
        same_destination_exact: list[tuple[AirfareRecord, AirfareRecord, str]] = []

        for discovery in destination_representatives:
            if not discovery.outbound_date or not discovery.return_date:
                continue
            if not self._exact_plan(discovery, discovery.outbound_date, discovery.return_date):
                execution["conventional_exact"]["unsupported"] += 1
                reason = "source-router blocked conventional exact completion"
                provider_failures.append({
                    "origin": discovery.origin.iata,
                    "surface": "source_router_exact",
                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                    "error": reason,
                })
                exact_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, reason))
                continue
            execution["conventional_exact"]["attempts"] += 1
            exact_result = await self.adapter.exact(
                origin=discovery.origin.iata,
                destination=discovery.destination.iata,
                departure_date=discovery.outbound_date,
                return_date=discovery.return_date,
            )
            _count_provider_result(execution, "conventional_exact", exact_result)
            if exact_result.coverage_state != "complete" or not exact_result.records:
                message = exact_result.error or exact_result.coverage_state
                if exact_result.coverage_state == "failed":
                    provider_failures.append({
                        "origin": discovery.origin.iata,
                        "surface": "exact",
                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                        "error": message,
                    })
                exact_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, f"exact revalidation failed closed: {message}"))
                continue
            exact = exact_result.records[0]
            if exact.current_price_twd and exact.complete_airfare and _minimum_away_satisfied(exact):
                same_destination_exact.append((discovery, exact, "provider_selected_dates"))
            else:
                exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, discovery.anomaly_authority, None, "exact surface lacked a complete >24h current airfare"))

        flexible_dates_by_seed: dict[str, tuple[str, str]] = {}
        for discovery in expansion_seed_pool:
            if not discovery.outbound_date:
                continue
            seed_duration = _trip_duration_days(discovery)
            if seed_duration is not None and seed_duration <= 1:
                seed_duration = None
            if discovery.return_date and not self._exact_plan(discovery, discovery.outbound_date, discovery.return_date):
                execution["flexible_dates"]["unsupported"] += 1
                continue
            execution["flexible_dates"]["attempts"] += 1
            flexible = await self.adapter.cheapest_dates(
                origin=discovery.origin.iata,
                destination=discovery.destination.iata,
                start_date=run_date.isoformat(),
                months=flexible_months,
                trip_duration_days=seed_duration,
            )
            _count_provider_result(execution, "flexible_dates", flexible)
            best = _best_flexible_record(flexible.records, run_date, horizon_end)
            if best is None or not best.outbound_date or not best.return_date:
                continue
            flexible_dates_by_seed[discovery.record_id] = (best.outbound_date, best.return_date)
            if not self._exact_plan(discovery, best.outbound_date, best.return_date):
                execution["flexible_dates"]["unsupported"] += 1
                continue
            execution["flexible_dates"].setdefault("exact_attempts", 0)
            execution["flexible_dates"].setdefault("exact_successes", 0)
            execution["flexible_dates"].setdefault("exact_empty", 0)
            execution["flexible_dates"].setdefault("exact_failures", 0)
            execution["flexible_dates"]["exact_attempts"] += 1
            exact_result = await self.adapter.exact(
                origin=discovery.origin.iata,
                destination=discovery.destination.iata,
                departure_date=best.outbound_date,
                return_date=best.return_date,
            )
            if exact_result.coverage_state == "complete" and exact_result.records:
                execution["flexible_dates"]["exact_successes"] += 1
                exact = exact_result.records[0]
                if exact.current_price_twd and exact.complete_airfare and _minimum_away_satisfied(exact):
                    same_destination_exact.append((discovery, exact, "flexible_dates"))
                else:
                    exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, discovery.anomaly_authority, None, "flexible-date exact result lacked a complete >24h current airfare"))
            else:
                message = exact_result.error or exact_result.coverage_state
                if exact_result.coverage_state == "failed":
                    execution["flexible_dates"]["exact_failures"] += 1
                    provider_failures.append({
                        "origin": discovery.origin.iata,
                        "surface": "flexible_exact",
                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                        "error": message,
                    })
                else:
                    execution["flexible_dates"]["exact_empty"] += 1

        best_same_destination: dict[str, tuple[AirfareRecord, AirfareRecord, str]] = {}
        for candidate in same_destination_exact:
            discovery, exact, source_kind = candidate
            incumbent = best_same_destination.get(discovery.destination.iata)
            if incumbent is None or (exact.current_price_twd or 10**12, discovery.record_id) < (incumbent[1].current_price_twd or 10**12, incumbent[0].record_id):
                best_same_destination[discovery.destination.iata] = (discovery, exact, source_kind)

        qualified_deals: list[RadarItem] = []
        for discovery, exact, source_kind in best_same_destination.values():
            observation = _to_observation(run_id, exact)
            destination_baseline = destination_baselines.get(discovery.destination.iata)
            truth = self._external_truth(discovery, exact, destination_baseline) or self._history_truth(observation)
            market = market_slice(discovery.destination.country)
            market_coverage[market]["revalidated"] += 1
            if truth is None or not truth.is_usable_truth():
                exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, None, None, "current exact airfare revalidated, but no qualified positive anomaly truth remained", observation.observation_id))
                continue
            discount = truth.normalized_discount_percent()
            if discount is None or discount <= 0:
                exact_signals.append(RadarItem("Signal", "exact_revalidated_candidate", discovery, exact, truth.source, discount, "exact current airfare is no longer below the selected anomaly baseline", observation.observation_id))
                continue
            baseline_twd = int(round(truth.typical_price_twd)) if truth.typical_price_twd is not None else None
            anomaly_scope = "destination_airport_all_taiwan_origins" if truth.source in {"google_flight_deals", "own_price_history"} else "selected_authority_scope"
            qualified_deals.append(
                RadarItem(
                    "Deal",
                    "deal",
                    discovery,
                    exact,
                    truth.source,
                    discount,
                    f"qualified anomaly authority plus current exact complete airfare via {source_kind}",
                    observation.observation_id,
                    anomaly_baseline_twd=baseline_twd,
                    anomaly_scope=anomaly_scope,
                )
            )
            market_coverage[market]["deals"] += 1

        qualified_deals.sort(
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
        deals = qualified_deals[:final_limit]
        qualified_destinations = {item.discovery.destination.iata for item in qualified_deals}

        alternative_signals: list[RadarItem] = []
        return_airports = tuple(str(item) for item in search_policy["return_to_taiwan"]["primary_return_search_airports"])
        variant_seeds = list(expansion_seed_pool[:expansion_variant_limit])
        for discovery in variant_seeds:
            dates = flexible_dates_by_seed.get(discovery.record_id)
            if dates is None and discovery.outbound_date and discovery.return_date:
                dates = (discovery.outbound_date, discovery.return_date)
            if dates is None:
                continue
            departure_date, return_date = dates
            alternate_return = next((airport for airport in return_airports if airport != discovery.origin.iata), None)
            if alternate_return is not None:
                mixed_result = await self.revalidate_open_jaw(
                    legs=[
                        (discovery.origin.iata, discovery.destination.iata, departure_date),
                        (discovery.destination.iata, alternate_return, return_date),
                    ]
                )
                if mixed_result.provider == "gflights":
                    execution["mixed_taiwan_return"]["attempts"] += 1
                    _count_provider_result(execution, "mixed_taiwan_return", mixed_result)
                else:
                    execution["mixed_taiwan_return"]["unsupported"] += 1
                if mixed_result.coverage_state == "complete" and mixed_result.records:
                    exact = mixed_result.records[0]
                    if discovery.destination.iata in qualified_destinations and exact.current_price_twd and exact.complete_airfare:
                        observation = _to_observation(run_id, exact)
                        alternative_signals.append(
                            RadarItem(
                                "Signal",
                                "mixed_taiwan_return_alternative",
                                discovery,
                                exact,
                                None,
                                None,
                                f"combined Google multi-city airfare returns to {alternate_return}; no synthetic anomaly baseline",
                                observation.observation_id,
                            )
                        )
                elif mixed_result.coverage_state == "failed":
                    provider_failures.append({
                        "origin": discovery.origin.iata,
                        "surface": "mixed_taiwan_return",
                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}-{alternate_return}",
                        "error": mixed_result.error or mixed_result.coverage_state,
                    })

            exit_seed = _open_jaw_exit(discovery, expansion_seed_pool)
            if exit_seed is not None:
                open_jaw_result = await self.revalidate_open_jaw(
                    legs=[
                        (discovery.origin.iata, discovery.destination.iata, departure_date),
                        (exit_seed.destination.iata, discovery.origin.iata, return_date),
                    ]
                )
                if open_jaw_result.provider == "gflights":
                    execution["open_jaw"]["attempts"] += 1
                    _count_provider_result(execution, "open_jaw", open_jaw_result)
                else:
                    execution["open_jaw"]["unsupported"] += 1
                if open_jaw_result.coverage_state == "complete" and open_jaw_result.records:
                    exact = open_jaw_result.records[0]
                    if discovery.destination.iata in qualified_destinations and exact.current_price_twd and exact.complete_airfare:
                        observation = _to_observation(run_id, exact)
                        alternative_signals.append(
                            RadarItem(
                                "Signal",
                                "open_jaw_airfare_alternative",
                                discovery,
                                exact,
                                None,
                                None,
                                f"combined Google multi-city airfare exits via {exit_seed.destination.iata}; no synthetic multi-city typical price",
                                observation.observation_id,
                            )
                        )
                elif open_jaw_result.coverage_state == "failed":
                    provider_failures.append({
                        "origin": discovery.origin.iata,
                        "surface": "open_jaw",
                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}/{exit_seed.destination.iata}-{discovery.origin.iata}",
                        "error": open_jaw_result.error or open_jaw_result.coverage_state,
                    })

        signal_by_key: dict[tuple[Any, ...], RadarItem] = {}
        for item in [
            *exact_signals,
            *alternative_signals,
            *(item for item in weak_signals if item.discovery.record_id not in selected_record_ids),
        ]:
            key = (item.discovery.record_id, item.state, item.reason, item.exact.record_id if item.exact else None)
            signal_by_key.setdefault(key, item)

        coverage = {
            "origins": origin_coverage,
            "markets": market_coverage,
            "execution": execution,
            "origin_attempt_required": True,
            "all_origins_attempted": all(origin in origin_coverage for origin in origins),
            "deal_acquisition_surface": "google_flight_deals",
            "exact_completion_surface": "google_flights_exact",
            "destination_scope": "asia_oceania",
            "anomaly_normalization": "exact_destination_airport_across_tpe_tsa_rmq_khh",
            "destination_representative_rule": "lowest_current_complete_airfare_per_destination",
            "expansion_seed_rule": "bounded_origin_date_variants_preserved_separately",
            "destination_representative_count": len(destination_representatives),
            "expansion_seed_count": len(expansion_seed_pool),
            "deep_search_candidate_limit": deep_limit,
            "final_shortlist_limit": final_limit,
            "final_shortlist_applied_after_deep_search": True,
            "same_destination_typical_rule": "lowest_qualified_google_flight_deals_typical",
            "fixed_watch_is_deal_coverage_authority": False,
        }
        provider_failures = list(reconcile_provider_failures(coverage, provider_failures))
        coverage["provider_health"] = derive_provider_health(coverage, provider_failures)
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
            return ProviderResult("source_router", "open_jaw", "unsupported", error=plan.fallback_reason or "Google exact open-jaw route is not selected by SSOT")
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
        "provider_health": result.coverage.get("provider_health", {}),
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
                "provider_health": result.coverage.get("provider_health", {}),
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
