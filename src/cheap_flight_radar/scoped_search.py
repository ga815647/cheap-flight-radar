"""Bounded, deterministic FTR scoped-search acquisition.

This module is deliberately separate from canonical/operator orchestration while
reusing CFR source routing, gflights adapter methods, anomaly semantics, RP-02
absolute-low selection, and RP-01 handoff primitives. It has no scheduler and
does not consume canonical acquisition claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .airfare import AirfareRecord, ProviderResult, is_international_asia_oceania, market_slice
from .anomaly_truth import AnomalyEvidence, formal_deal_sort_key
from .ftr_absolute_low import apply_absolute_low_selection
from .ftr_handoff import (
    CANONICAL_LATEST_PATH,
    CURRENT_STATUS_PATH,
    FTRHandoffError,
    build_snapshot,
    load_manifest_snapshot,
    manifest_repository_path,
    stage_snapshot,
    validate_snapshot,
)
from .models import OriginSweepRequest, SearchRequest
from .production_radar import (
    MARKETS,
    ProductionRadar,
    RadarItem,
    RadarRunResult,
    _discovery_sort_key,
    _item_json,
    _minimum_away_satisfied,
    _observation_id,
    _to_observation,
)
from .source_router import build_source_plan


CONTRACT_VERSION = "1.0"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SCOPED_SURFACES = (
    "flight_deals",
    "explore",
    "conventional_exact",
    "flexible_dates",
    "mixed_taiwan_return",
    "open_jaw",
)


class ScopedSearchError(ValueError):
    """Raised when a scoped request/runtime cannot satisfy its contract."""


@dataclass(frozen=True, order=True)
class AvailabilityWindow:
    start_date: str
    end_date: str

    def dates(self) -> tuple[date, date]:
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as exc:
            raise ScopedSearchError("availability_windows must contain ISO dates") from exc
        if end <= start:
            raise ScopedSearchError("availability window end_date must be after start_date")
        return start, end


@dataclass(frozen=True)
class DurationConstraint:
    min_nights: int | None = None
    max_nights: int | None = None

    def validate(self) -> None:
        for value, field in ((self.min_nights, "min_nights"), (self.max_nights, "max_nights")):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
                raise ScopedSearchError(f"duration.{field} must be a positive integer")
        if self.min_nights is not None and self.max_nights is not None and self.min_nights > self.max_nights:
            raise ScopedSearchError("duration.min_nights cannot exceed duration.max_nights")


@dataclass(frozen=True)
class ScopedExecutionPolicy:
    max_discovery_calls: int
    max_exact_revalidations: int

    def validate(self) -> None:
        for value, field in (
            (self.max_discovery_calls, "max_discovery_calls"),
            (self.max_exact_revalidations, "max_exact_revalidations"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ScopedSearchError(f"execution_policy.{field} must be a positive integer")


@dataclass(frozen=True)
class ScopedSearchRequest:
    request_id: str
    availability_windows: tuple[AvailabilityWindow, ...]
    execution_policy: ScopedExecutionPolicy
    duration: DurationConstraint | None = None
    max_budget_twd: int | None = None

    def validate(self) -> None:
        if not REQUEST_ID_PATTERN.fullmatch(self.request_id):
            raise ScopedSearchError("request_id must be explicit, path-safe, and at most 80 characters")
        if not self.availability_windows:
            raise ScopedSearchError("at least one availability_window is required")
        for window in self.availability_windows:
            window.dates()
        if self.duration is not None:
            self.duration.validate()
        self.execution_policy.validate()
        if self.max_budget_twd is not None:
            if isinstance(self.max_budget_twd, bool) or not isinstance(self.max_budget_twd, int) or self.max_budget_twd <= 0:
                raise ScopedSearchError("max_budget_twd must be a positive integer when supplied")


@dataclass(frozen=True)
class ScopedDiscoveryTask:
    task_id: str
    window_id: str
    origin: str
    anchor_departure: str
    anchor_return: str


@dataclass(frozen=True)
class ScopedSearchPlan:
    request_id: str
    request_fingerprint: str
    plan_id: str
    windows: tuple[AvailabilityWindow, ...]
    discovery_tasks: tuple[ScopedDiscoveryTask, ...]
    discovery_truncated: bool
    duration: DurationConstraint | None
    max_budget_twd: int | None
    execution_policy: ScopedExecutionPolicy


@dataclass(frozen=True)
class ScopedRunOutcome:
    run_id: str
    plan: ScopedSearchPlan
    run_result: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    staged: Mapping[str, str]
    replayed: bool = False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_windows(windows: Sequence[AvailabilityWindow]) -> tuple[AvailabilityWindow, ...]:
    normalized = sorted(set(windows))
    return tuple(normalized)


def _request_payload(request: ScopedSearchRequest) -> Mapping[str, Any]:
    windows = _normalized_windows(request.availability_windows)
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request.request_id,
        "availability_windows": [asdict(value) for value in windows],
        "duration": asdict(request.duration) if request.duration is not None else None,
        "max_budget_twd": request.max_budget_twd,
        "execution_policy": asdict(request.execution_policy),
    }


def request_fingerprint(request: ScopedSearchRequest) -> str:
    request.validate()
    return _hash(_request_payload(request))


def _policy_contract(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(policy.get("ftr_handoff")).get("scoped_search_acquisition"))


def validate_scoped_search_policy(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    contract = _policy_contract(policy)
    if not contract:
        raise ScopedSearchError("missing ftr_handoff.scoped_search_acquisition policy")
    if contract.get("enabled") is not True:
        raise ScopedSearchError("scoped-search acquisition must be enabled pre-activation")
    if str(contract.get("contract_version") or "") != CONTRACT_VERSION:
        raise ScopedSearchError("scoped-search contract_version drifted")
    if str(contract.get("mode") or "") != "scoped_search":
        raise ScopedSearchError("scoped-search mode drifted")
    request = _mapping(contract.get("request"))
    if tuple(request.get("required_fields") or ()) != (
        "request_id", "availability_windows", "execution_policy",
    ):
        raise ScopedSearchError("scoped-search required request fields drifted")
    if request.get("duration_optional") is not True or request.get("absent_duration_applies_no_fixed_ftr_duration") is not True:
        raise ScopedSearchError("scoped-search duration semantics drifted")
    if request.get("max_budget_optional_query_hard_filter_only") is not True:
        raise ScopedSearchError("scoped-search max-budget semantics drifted")
    windows = _mapping(contract.get("windows"))
    if windows.get("complete_trip_must_fit_one_window") is not True:
        raise ScopedSearchError("scoped-search one-window trip invariant drifted")
    if windows.get("cross_window_trip") != "forbidden":
        raise ScopedSearchError("scoped-search cross-window trip invariant drifted")
    if windows.get("multiple_windows_merge_one_request") is not True:
        raise ScopedSearchError("scoped-search multi-window merge semantics drifted")
    acquisition = _mapping(contract.get("acquisition"))
    if acquisition.get("reuse_source_router") is not True or acquisition.get("reuse_exact_revalidation") is not True:
        raise ScopedSearchError("scoped-search CFR substrate reuse drifted")
    if acquisition.get("broad_horizon_then_post_filter") != "forbidden":
        raise ScopedSearchError("scoped-search broad-post-filter prohibition drifted")
    if acquisition.get("destination_discovery_surface") != "gflights_google_flight_deals":
        raise ScopedSearchError("scoped-search date-constrained discovery surface drifted")
    if acquisition.get("unconstrainable_surface_action") not in {"not_attempted", "failed_closed"}:
        raise ScopedSearchError("scoped-search unconstrainable-surface action drifted")
    bounded = _mapping(contract.get("bounded_execution"))
    max_windows = bounded.get("max_windows")
    max_discovery = bounded.get("max_discovery_calls")
    max_exact = bounded.get("max_exact_revalidations")
    for value, field in ((max_windows, "max_windows"), (max_discovery, "max_discovery_calls"), (max_exact, "max_exact_revalidations")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ScopedSearchError(f"scoped-search {field} must be a positive integer")
    if bounded.get("deterministic_ordering") is not True or bounded.get("deterministic_truncation") is not True:
        raise ScopedSearchError("scoped-search deterministic planning policy drifted")
    if bounded.get("search_horizon_days_is_scoped_budget") is not False:
        raise ScopedSearchError("search.horizon_days must not become scoped budget")
    identity = _mapping(contract.get("identity"))
    if identity.get("canonical_claim_consumption") != "forbidden":
        raise ScopedSearchError("scoped-search canonical claim isolation drifted")
    if identity.get("operator_reacquisition_identity_reuse") != "forbidden":
        raise ScopedSearchError("scoped-search operator identity isolation drifted")
    if identity.get("same_day_recovery_masquerade") != "forbidden":
        raise ScopedSearchError("scoped-search recovery identity isolation drifted")
    if identity.get("duplicate_request_semantics") != "replay_identical_fingerprint_reject_request_id_reuse":
        raise ScopedSearchError("scoped-search replay semantics drifted")
    isolation = _mapping(contract.get("canonical_isolation"))
    for field in (
        "never_advance_canonical_latest",
        "never_mutate_current_status",
        "never_clear_repair_required",
        "never_replace_repair_incident",
    ):
        if isolation.get(field) is not True:
            raise ScopedSearchError(f"scoped-search isolation flag drifted: {field}")
    ftr = _mapping(policy.get("ftr_handoff"))
    canonical = _mapping(ftr.get("canonical_activation"))
    if canonical.get("enabled") is not False:
        raise ScopedSearchError("RP-03 must not activate canonical FTR runtime")
    return contract


def _pair_allowed(nights: int, duration: DurationConstraint | None) -> bool:
    if duration is None:
        # CFR's existing >24h product invariant is not an FTR fixed duration.
        return nights >= 2
    if duration.min_nights is not None and nights < duration.min_nights:
        return False
    if duration.max_nights is not None and nights > duration.max_nights:
        return False
    return True


def _date_pairs(window: AvailabilityWindow, duration: DurationConstraint | None) -> tuple[tuple[str, str], ...]:
    start, end = window.dates()
    pairs: list[tuple[str, str]] = []
    cursor = start
    while cursor < end:
        ret = cursor + timedelta(days=1)
        while ret <= end:
            nights = (ret - cursor).days
            if _pair_allowed(nights, duration):
                pairs.append((cursor.isoformat(), ret.isoformat()))
            ret += timedelta(days=1)
        cursor += timedelta(days=1)
    # Stable fairness inside a window: shorter spans first, then departure/return.
    pairs.sort(key=lambda value: ((date.fromisoformat(value[1]) - date.fromisoformat(value[0])).days, value[0], value[1]))
    return tuple(pairs)


def build_scoped_plan(request: ScopedSearchRequest, *, policy: Mapping[str, Any]) -> ScopedSearchPlan:
    request.validate()
    contract = validate_scoped_search_policy(policy)
    bounded = _mapping(contract["bounded_execution"])
    windows = _normalized_windows(request.availability_windows)
    if len(windows) > int(bounded["max_windows"]):
        raise ScopedSearchError("availability_windows exceed machine SSOT max_windows")
    if request.execution_policy.max_discovery_calls > int(bounded["max_discovery_calls"]):
        raise ScopedSearchError("request max_discovery_calls exceeds machine SSOT")
    if request.execution_policy.max_exact_revalidations > int(bounded["max_exact_revalidations"]):
        raise ScopedSearchError("request max_exact_revalidations exceeds machine SSOT")

    origins = tuple(str(value) for value in _mapping(policy.get("search")).get("origin_airports", ()))
    if not origins:
        raise ScopedSearchError("search.origin_airports is empty")
    fingerprint = request_fingerprint(request)
    pair_sets = [_date_pairs(window, request.duration) for window in windows]
    candidates: list[tuple[int, int, str, str, str]] = []
    max_depth = max((len(value) for value in pair_sets), default=0)
    for pair_index in range(max_depth):
        for window_index, pairs in enumerate(pair_sets):
            if pair_index >= len(pairs):
                continue
            dep, ret = pairs[pair_index]
            for origin in origins:
                candidates.append((pair_index, window_index, origin, dep, ret))
    limit = request.execution_policy.max_discovery_calls
    selected = candidates[:limit]
    tasks: list[ScopedDiscoveryTask] = []
    for _, window_index, origin, dep, ret in selected:
        window = windows[window_index]
        window_id = f"w-{window.start_date}-{window.end_date}"
        task_material = [fingerprint, window_id, origin, dep, ret]
        tasks.append(
            ScopedDiscoveryTask(
                task_id="scoped-discovery-" + _hash(task_material)[:16],
                window_id=window_id,
                origin=origin,
                anchor_departure=dep,
                anchor_return=ret,
            )
        )
    plan_material = {
        "request_fingerprint": fingerprint,
        "tasks": [asdict(value) for value in tasks],
        "exact_budget": request.execution_policy.max_exact_revalidations,
    }
    return ScopedSearchPlan(
        request_id=request.request_id,
        request_fingerprint=fingerprint,
        plan_id="scoped-plan-" + _hash(plan_material)[:20],
        windows=windows,
        discovery_tasks=tuple(tasks),
        discovery_truncated=len(candidates) > len(tasks),
        duration=request.duration,
        max_budget_twd=request.max_budget_twd,
        execution_policy=request.execution_policy,
    )


def _window_for_id(plan: ScopedSearchPlan, window_id: str) -> AvailabilityWindow:
    for window in plan.windows:
        if window_id == f"w-{window.start_date}-{window.end_date}":
            return window
    raise ScopedSearchError(f"unknown plan window_id: {window_id}")


def _record_fits_window(record: AirfareRecord, window: AvailabilityWindow) -> bool:
    if not record.outbound_date or not record.return_date:
        return False
    try:
        outbound = date.fromisoformat(record.outbound_date)
        returned = date.fromisoformat(record.return_date)
    except ValueError:
        return False
    start, end = window.dates()
    return start <= outbound <= returned <= end


def _record_duration_allowed(record: AirfareRecord, duration: DurationConstraint | None) -> bool:
    if duration is None:
        return True
    if not record.outbound_date or not record.return_date:
        return False
    try:
        nights = (date.fromisoformat(record.return_date) - date.fromisoformat(record.outbound_date)).days
    except ValueError:
        return False
    if duration.min_nights is not None and nights < duration.min_nights:
        return False
    if duration.max_nights is not None and nights > duration.max_nights:
        return False
    return True


def _execution_row() -> dict[str, int]:
    return {
        "attempts": 0,
        "provider_calls": 0,
        "records": 0,
        "successes": 0,
        "empty": 0,
        "failures": 0,
        "suppressed": 0,
        "unsupported": 0,
    }


def _count(execution: dict[str, dict[str, int]], surface: str, result: ProviderResult) -> None:
    row = execution[surface]
    row["records"] += len(result.records)
    if result.request_sent:
        row["provider_calls"] += 1
    else:
        row["suppressed"] += 1
        return
    if result.coverage_state == "complete" and result.records:
        row["successes"] += 1
    elif result.coverage_state == "failed":
        row["failures"] += 1
    elif result.coverage_state == "unsupported":
        row["unsupported"] += 1
    else:
        row["empty"] += 1


def _profile(record: AirfareRecord) -> str:
    market = market_slice(record.destination.country)
    return market if market in {"japan", "korea", "china"} else "world"


def _provider_health(
    *,
    origin_rows: Mapping[str, Mapping[str, Any]],
    flight_deals: Mapping[str, int],
) -> Mapping[str, Any]:
    attempted = [value for value in origin_rows.values() if value.get("status") != "not_attempted"]
    all_failed = bool(attempted) and all(value.get("status") == "failed" for value in attempted)
    if all_failed and int(flight_deals.get("provider_calls", 0)) > 0:
        status = "provider_failed"
        reasons = ["all attempted scoped Flight Deals origin slices failed"]
    elif any(value.get("status") != "attempted" for value in origin_rows.values()):
        status = "degraded"
        reasons = ["bounded scoped plan left a required origin unattempted or degraded"]
    else:
        status = "healthy"
        reasons = []
    return {
        "status": status,
        "technical_failure_count": int(flight_deals.get("failures", 0)),
        "reasons": reasons,
    }


def _canonical_guard(history_dir: Path) -> Mapping[str, tuple[bool, str]]:
    result: dict[str, tuple[bool, str]] = {}
    for relative in (CANONICAL_LATEST_PATH, CURRENT_STATUS_PATH):
        path = history_dir / relative
        if path.exists():
            result[relative] = (True, hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            result[relative] = (False, "")
    return result


def _assert_canonical_guard(history_dir: Path, before: Mapping[str, tuple[bool, str]]) -> None:
    after = _canonical_guard(history_dir)
    if dict(after) != dict(before):
        raise FTRHandoffError("scoped_search mutated canonical latest/current-status isolation guard")


def _scoped_metadata(plan: ScopedSearchPlan, *, execution: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": plan.request_id,
        "request_fingerprint": plan.request_fingerprint,
        "plan_id": plan.plan_id,
        "availability_windows": [asdict(value) for value in plan.windows],
        "duration": asdict(plan.duration) if plan.duration is not None else None,
        "max_budget_twd": plan.max_budget_twd,
        "execution_policy": asdict(plan.execution_policy),
        "discovery_truncated": plan.discovery_truncated,
        "discovery_plan": [asdict(value) for value in plan.discovery_tasks],
    }
    if execution is not None:
        payload["execution"] = dict(execution)
    return payload


def validate_scoped_snapshot(snapshot: Mapping[str, Any], *, plan: ScopedSearchPlan | None = None) -> None:
    validate_snapshot(snapshot)
    if str(snapshot.get("mode") or "") != "scoped_search":
        raise FTRHandoffError("scoped snapshot mode must be scoped_search")
    scoped = _mapping(snapshot.get("scoped_search"))
    if not scoped:
        raise FTRHandoffError("scoped snapshot missing scoped_search metadata")
    if str(scoped.get("contract_version") or "") != CONTRACT_VERSION:
        raise FTRHandoffError("scoped snapshot contract version unsupported")
    request_id = str(scoped.get("request_id") or "")
    fingerprint = str(scoped.get("request_fingerprint") or "")
    plan_id = str(scoped.get("plan_id") or "")
    if not REQUEST_ID_PATTERN.fullmatch(request_id) or len(fingerprint) != 64 or not plan_id.startswith("scoped-plan-"):
        raise FTRHandoffError("scoped snapshot identity metadata invalid")
    windows_raw = scoped.get("availability_windows")
    if not isinstance(windows_raw, Sequence) or isinstance(windows_raw, (str, bytes)) or not windows_raw:
        raise FTRHandoffError("scoped snapshot availability_windows invalid")
    windows = tuple(
        AvailabilityWindow(
            start_date=str(_mapping(value).get("start_date") or ""),
            end_date=str(_mapping(value).get("end_date") or ""),
        )
        for value in windows_raw
    )
    for window in windows:
        window.dates()
    duration_raw = scoped.get("duration")
    duration: DurationConstraint | None = None
    if duration_raw is not None:
        duration = DurationConstraint(
            min_nights=_mapping(duration_raw).get("min_nights"),
            max_nights=_mapping(duration_raw).get("max_nights"),
        )
        duration.validate()
    max_budget = scoped.get("max_budget_twd")
    if max_budget is not None and (isinstance(max_budget, bool) or not isinstance(max_budget, int) or max_budget <= 0):
        raise FTRHandoffError("scoped snapshot max_budget_twd invalid")
    for opportunity in snapshot.get("opportunities") or []:
        for variant in _mapping(opportunity).get("variants") or []:
            outbound = str(_mapping(variant).get("outbound_date") or "")
            returned = str(_mapping(variant).get("return_date") or "")
            fits = False
            for window in windows:
                start, end = window.dates()
                try:
                    dep = date.fromisoformat(outbound)
                    ret = date.fromisoformat(returned)
                except ValueError:
                    continue
                if start <= dep <= ret <= end:
                    fits = True
                    break
            if not fits:
                raise FTRHandoffError("scoped snapshot contains trip outside all supplied windows")
            if duration is not None:
                nights = (date.fromisoformat(returned) - date.fromisoformat(outbound)).days
                if duration.min_nights is not None and nights < duration.min_nights:
                    raise FTRHandoffError("scoped snapshot violates min_nights")
                if duration.max_nights is not None and nights > duration.max_nights:
                    raise FTRHandoffError("scoped snapshot violates max_nights")
            if max_budget is not None and int(_mapping(variant).get("complete_airfare_twd") or 0) > max_budget:
                raise FTRHandoffError("scoped snapshot violates request max_budget_twd")
    if plan is not None:
        expected = _scoped_metadata(plan)
        for key in (
            "contract_version", "request_id", "request_fingerprint", "plan_id",
            "availability_windows", "duration", "max_budget_twd", "execution_policy",
            "discovery_truncated", "discovery_plan",
        ):
            if scoped.get(key) != expected.get(key):
                raise FTRHandoffError(f"scoped snapshot metadata mismatches plan: {key}")


def _candidate_pool_key(record: AirfareRecord) -> tuple[Any, ...]:
    qualified = (
        record.evidence_class == "qualified_round_trip_deal"
        and bool(record.anomaly_authority)
        and bool(record.typical_price_twd)
    )
    return (
        0 if qualified else 1,
        -float(record.discount_percent or 0.0) if qualified else 0.0,
        int(record.current_price_twd or 10**12),
        record.outbound_date or "",
        record.return_date or "",
        record.origin.iata,
        record.destination.iata,
        record.record_id,
    )


def _dedupe_records(records: Sequence[tuple[AirfareRecord, str]]) -> tuple[tuple[AirfareRecord, str], ...]:
    best: dict[tuple[str, str, str | None, str | None], tuple[AirfareRecord, str]] = {}
    for record, window_id in records:
        key = (record.origin.iata, record.destination.iata, record.outbound_date, record.return_date)
        incumbent = best.get(key)
        if incumbent is None or _candidate_pool_key(record) < _candidate_pool_key(incumbent[0]):
            best[key] = (record, window_id)
    return tuple(sorted(best.values(), key=lambda value: _candidate_pool_key(value[0])))


def _run_result_json(
    result: RadarRunResult,
    *,
    provider_health: Mapping[str, Any],
    scoped_execution: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "radar_run_id": result.radar_run_id,
        "run_at": result.run_at,
        "execution_mode": "scoped_search",
        "deals": [_item_json(value) for value in result.deals],
        "signals": [_item_json(value) for value in result.signals],
        "ftr_absolute_low_non_deals": [_item_json(value) for value in result.ftr_absolute_low_non_deals],
        "coverage": dict(result.coverage),
        "provider_health": dict(provider_health),
        "provider_failures": [dict(value) for value in result.provider_failures],
        "scoped_execution": dict(scoped_execution),
    }


def _same_request_manifest(history_dir: Path, request_id: str) -> tuple[str, Mapping[str, Any], Mapping[str, Any]] | None:
    root = history_dir / "data" / "ftr-feed" / "scoped"
    if not root.exists():
        return None
    matches: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for path in sorted(root.glob("*.json")):
        relative = path.relative_to(history_dir).as_posix()
        try:
            snapshot = load_manifest_snapshot(history_dir=history_dir, manifest_path=relative)
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, FTRHandoffError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        scoped = _mapping(snapshot.get("scoped_search"))
        if str(scoped.get("request_id") or "") == request_id:
            matches.append((relative, manifest, snapshot))
    fingerprints = {
        str(_mapping(snapshot.get("scoped_search")).get("request_fingerprint") or "")
        for _, _, snapshot in matches
    }
    if len(fingerprints) > 1:
        raise FTRHandoffError("request_id already exists with multiple scoped fingerprints")
    return matches[0] if matches else None


async def acquire_scoped(
    *,
    request: ScopedSearchRequest,
    policy: Mapping[str, Any],
    adapter: Any,
    run_at: datetime,
    prior_history: Sequence[Any] = (),
) -> tuple[ScopedSearchPlan, RadarRunResult, Mapping[str, Any]]:
    """Execute only supplied-window Flight Deals anchors and exact revalidation."""
    plan = build_scoped_plan(request, policy=policy)
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ScopedSearchError("run_at must be timezone-aware")
    run_id = f"ftr-scoped-{request.request_id}-{plan.request_fingerprint[:12]}"
    run_at_text = run_at.isoformat()
    execution = {name: _execution_row() for name in SCOPED_SURFACES}
    origin_state: dict[str, dict[str, Any]] = {
        str(origin): {
            "status": "not_attempted",
            "returned_flight_deals": 0,
            "explore_seeds": 0,
            "errors": [],
        }
        for origin in _mapping(policy.get("search")).get("origin_airports", ())
    }
    market_rows = {
        market: {"status": "not_attempted", "coverage_basis": "scoped_shared_destination_free_origin_coverage",
                 "discovered": 0, "qualified": 0, "revalidated": 0, "deals": 0}
        for market in MARKETS
    }
    provider_failures: list[Mapping[str, str]] = []
    scoped_rows: list[tuple[AirfareRecord, str]] = []
    window_attempts: dict[str, dict[str, int]] = {
        f"w-{window.start_date}-{window.end_date}": {"attempts": 0, "successes": 0, "failures": 0, "records": 0}
        for window in plan.windows
    }

    for task in plan.discovery_tasks:
        origin = task.origin
        window = _window_for_id(plan, task.window_id)
        execution["flight_deals"]["attempts"] += 1
        window_attempts[task.window_id]["attempts"] += 1
        route_plan = build_source_plan(
            OriginSweepRequest(
                origin=origin,
                horizon_start=window.start_date,
                horizon_days=(window.dates()[1] - window.dates()[0]).days + 1,
                destination_scope="asia_oceania",
                currency="TWD",
            ),
            policy,
            {},
        )
        if (
            route_plan.coverage_state != "planned"
            or not route_plan.entries
            or route_plan.entries[0].provider != "gflights_google_flight_deals"
        ):
            execution["flight_deals"]["unsupported"] += 1
            origin_state[origin]["status"] = "degraded"
            message = route_plan.fallback_reason or "scoped Flight Deals routing unavailable"
            origin_state[origin]["errors"].append(message)
            window_attempts[task.window_id]["failures"] += 1
            provider_failures.append({"provider": "gflights", "origin": origin, "surface": "source_router", "error": message})
            continue

        result = await adapter.flight_deals(
            origin=origin,
            anchor_departure=task.anchor_departure,
            anchor_return=task.anchor_return,
        )
        _count(execution, "flight_deals", result)
        if result.coverage_state == "failed":
            origin_state[origin]["status"] = "degraded"
            message = result.error or "provider failure"
            origin_state[origin]["errors"].append(message)
            window_attempts[task.window_id]["failures"] += 1
            if result.request_sent:
                provider_failures.append({"provider": result.provider, "origin": origin, "surface": "flight_deals", "error": message})
            continue

        if origin_state[origin]["status"] == "not_attempted":
            origin_state[origin]["status"] = "attempted"
        window_attempts[task.window_id]["successes"] += 1
        window_attempts[task.window_id]["records"] += len(result.records)
        origin_state[origin]["returned_flight_deals"] += len(result.records)
        for record in result.records:
            if not is_international_asia_oceania(record.destination.country):
                continue
            if not _record_fits_window(record, window):
                continue
            if not _record_duration_allowed(record, plan.duration):
                continue
            scoped_rows.append((record, task.window_id))
            market = market_slice(record.destination.country)
            market_rows[market]["discovered"] += 1
            if (
                record.evidence_class == "qualified_round_trip_deal"
                and record.complete_airfare
                and record.current_price_twd
                and record.typical_price_twd
                and record.discount_percent
                and _minimum_away_satisfied(record)
            ):
                market_rows[market]["qualified"] += 1

    if plan.discovery_truncated:
        for origin in origin_state:
            if origin_state[origin]["status"] == "not_attempted":
                origin_state[origin]["errors"].append("not reached under deterministic scoped discovery budget")

    pool = _dedupe_records(scoped_rows)
    selected = pool[: plan.execution_policy.max_exact_revalidations]
    exact_items: list[RadarItem] = []
    nondeal_items: list[RadarItem] = []
    weak_signals: list[RadarItem] = []
    destination_baselines: dict[str, AirfareRecord] = {}
    for record, _ in pool:
        if record.anomaly_authority == "google_flight_deals" and record.typical_price_twd:
            incumbent = destination_baselines.get(record.destination.iata)
            if incumbent is None or int(record.typical_price_twd) < int(incumbent.typical_price_twd or 10**12):
                destination_baselines[record.destination.iata] = record

    semantics = ProductionRadar(policy=policy, adapter=adapter, prior_history=prior_history)
    for discovery, window_id in selected:
        window = _window_for_id(plan, window_id)
        if not discovery.outbound_date or not discovery.return_date:
            continue
        route_plan = build_source_plan(
            SearchRequest(
                profile=_profile(discovery),
                search_stage="round_trip_benchmark",
                origin=discovery.origin.iata,
                destination=discovery.destination.iata,
                outbound_date=discovery.outbound_date,
                return_date=discovery.return_date,
                destination_country=discovery.destination.country,
            ),
            policy,
            {},
        )
        execution["conventional_exact"]["attempts"] += 1
        if (
            route_plan.coverage_state != "planned"
            or not route_plan.entries
            or route_plan.entries[0].provider != "gflights_google_exact"
        ):
            execution["conventional_exact"]["unsupported"] += 1
            reason = route_plan.fallback_reason or "source-router blocked scoped exact completion"
            provider_failures.append({
                "provider": "gflights", "origin": discovery.origin.iata, "surface": "source_router_exact",
                "route": f"{discovery.origin.iata}-{discovery.destination.iata}", "error": reason,
            })
            weak_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, reason))
            continue

        exact_result = await adapter.exact(
            origin=discovery.origin.iata,
            destination=discovery.destination.iata,
            departure_date=discovery.outbound_date,
            return_date=discovery.return_date,
        )
        _count(execution, "conventional_exact", exact_result)
        if exact_result.coverage_state != "complete" or not exact_result.records:
            message = exact_result.error or exact_result.coverage_state
            if exact_result.coverage_state == "failed" and exact_result.request_sent:
                provider_failures.append({
                    "provider": exact_result.provider, "origin": discovery.origin.iata, "surface": "exact",
                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}", "error": message,
                })
            weak_signals.append(RadarItem(
                "Signal", "weak_seed", discovery, None, discovery.anomaly_authority,
                discovery.discount_percent, f"scoped exact revalidation failed closed: {message}",
            ))
            continue

        exact = exact_result.records[0]
        if (
            exact.origin.iata != discovery.origin.iata
            or exact.destination.iata != discovery.destination.iata
            or not _record_fits_window(exact, window)
            or not _record_duration_allowed(exact, plan.duration)
            or exact.outbound_date != discovery.outbound_date
            or exact.return_date != discovery.return_date
        ):
            weak_signals.append(RadarItem(
                "Signal", "weak_seed", discovery, None, discovery.anomaly_authority,
                discovery.discount_percent, "exact provider result violated scoped route/date/window contract",
            ))
            continue
        if exact.verification_state != "revalidated" or not exact.complete_airfare or not exact.current_price_twd:
            weak_signals.append(RadarItem(
                "Signal", "exact_revalidated_candidate", discovery, exact, discovery.anomaly_authority,
                None, "exact surface did not yield revalidated complete airfare",
            ))
            continue
        if plan.max_budget_twd is not None and exact.current_price_twd > plan.max_budget_twd:
            continue
        if not _minimum_away_satisfied(exact):
            continue

        observation = _to_observation(run_id, exact)
        truth = semantics._external_truth(discovery, exact, destination_baselines.get(discovery.destination.iata))
        if truth is None:
            truth = semantics._history_truth(observation)
        market = market_slice(discovery.destination.country)
        market_rows[market]["revalidated"] += 1
        discount = truth.normalized_discount_percent() if truth is not None and truth.is_usable_truth() else None
        if discount is not None and discount > 0:
            baseline = int(round(truth.typical_price_twd)) if truth.typical_price_twd is not None else None
            exact_items.append(RadarItem(
                "Deal", "deal", discovery, exact, truth.source, discount,
                "qualified anomaly authority plus current scoped exact complete airfare",
                observation.observation_id,
                anomaly_baseline_twd=baseline,
                anomaly_scope=(
                    "destination_airport_all_taiwan_origins"
                    if truth.source in {"google_flight_deals", "own_price_history"}
                    else "selected_authority_scope"
                ),
            ))
            market_rows[market]["deals"] += 1
        else:
            nondeal_items.append(RadarItem(
                "Signal", "exact_revalidated_candidate", discovery, exact,
                truth.source if truth is not None else None, discount,
                "scoped exact current airfare revalidated, but no qualified positive anomaly truth remained",
                observation.observation_id,
            ))

    exact_items.sort(
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

    planned_origins = {task.origin for task in plan.discovery_tasks}
    for market in MARKETS:
        if not planned_origins:
            market_rows[market]["status"] = "not_attempted"
        elif all(origin_state[origin]["status"] == "attempted" for origin in origin_state):
            market_rows[market]["status"] = "succeeded"
        else:
            market_rows[market]["status"] = "failed"

    health = _provider_health(origin_rows=origin_state, flight_deals=execution["flight_deals"])
    coverage = {
        "origins": origin_state,
        "markets": market_rows,
        "execution": execution,
        "all_origins_attempted": all(value["status"] != "not_attempted" for value in origin_state.values()),
        "destination_scope": "asia_oceania",
        "provider_health": health,
        "provider_execution": {
            "gflights": {
                "status": "failed" if health["status"] == "provider_failed" else "succeeded",
                "health_status": health["status"],
                "surfaces": ["flight_deals", "exact"],
                "reasons": list(health["reasons"]),
            }
        },
    }
    base = RadarRunResult(
        radar_run_id=run_id,
        run_at=run_at_text,
        deals=tuple(exact_items),
        signals=tuple([*weak_signals, *nondeal_items]),
        coverage=coverage,
        provider_failures=tuple(provider_failures),
        exact_non_deal_candidates=tuple(nondeal_items),
    )
    selected_result = apply_absolute_low_selection(base, policy=policy)
    return plan, selected_result, {
        "window_execution": window_attempts,
        "eligible_seed_count": len(pool),
        "exact_selected_count": len(selected),
        "discovery_truncated": plan.discovery_truncated,
        "unconstrainable_surfaces": {
            "explore": "not_attempted",
            "flexible_dates": "not_attempted",
            "open_jaw": "not_attempted",
        },
    }


async def execute_scoped_search(
    *,
    request: ScopedSearchRequest,
    policy: Mapping[str, Any],
    adapter: Any,
    history_dir: Path,
    producer_commit_sha: str,
    run_at: datetime,
    generated_at: str | None = None,
    prior_history: Sequence[Any] = (),
) -> ScopedRunOutcome:
    """Run/stage a scoped request with deterministic replay and canonical guards."""
    plan = build_scoped_plan(request, policy=policy)
    existing = _same_request_manifest(history_dir, request.request_id)
    if existing is not None:
        manifest_path, manifest, snapshot = existing
        scoped = _mapping(snapshot.get("scoped_search"))
        if str(scoped.get("request_fingerprint") or "") != plan.request_fingerprint:
            raise FTRHandoffError("request_id reuse with different scoped intent is forbidden")
        validate_scoped_snapshot(snapshot, plan=plan)
        return ScopedRunOutcome(
            run_id=str(snapshot["run_id"]),
            plan=plan,
            run_result={},
            snapshot=snapshot,
            staged={
                "snapshot_path": str(manifest["snapshot_path"]),
                "manifest_path": manifest_path,
                "snapshot_sha256": str(manifest["snapshot_sha256"]),
            },
            replayed=True,
        )

    guard = _canonical_guard(history_dir)
    try:
        plan, result, scoped_execution = await acquire_scoped(
            request=request,
            policy=policy,
            adapter=adapter,
            run_at=run_at,
            prior_history=prior_history,
        )
        health = _mapping(result.coverage).get("provider_health") or {}
        run_json = _run_result_json(result, provider_health=_mapping(health), scoped_execution=scoped_execution)
        base_snapshot = build_snapshot(
            run_json,
            producer_commit_sha=producer_commit_sha,
            mode="scoped_search",
            generated_at=generated_at,
        )
        snapshot = dict(base_snapshot)
        snapshot["scoped_search"] = _scoped_metadata(plan, execution=scoped_execution)
        validate_scoped_snapshot(snapshot, plan=plan)
        staged = stage_snapshot(history_dir=history_dir, snapshot=snapshot)
        loaded = load_manifest_snapshot(history_dir=history_dir, manifest_path=staged["manifest_path"])
        validate_scoped_snapshot(loaded, plan=plan)
        return ScopedRunOutcome(
            run_id=result.radar_run_id,
            plan=plan,
            run_result=run_json,
            snapshot=snapshot,
            staged=staged,
            replayed=False,
        )
    finally:
        _assert_canonical_guard(history_dir, guard)
