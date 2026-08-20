"""Bounded, deterministic FTR scoped-search acquisition.

The runtime reuses CFR source routing, provider adapter methods, Deal semantics,
RP-02 absolute-low selection, and RP-01 handoff primitives. It has no scheduler,
uses its own request identity, and never consumes canonical acquisition state.
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
    stage_snapshot,
    validate_snapshot,
)
from .models import OriginSweepRequest, SearchRequest
from .production_radar import (
    MARKETS,
    ProductionRadar,
    RadarItem,
    RadarRunResult,
    _item_json,
    _minimum_away_satisfied,
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
WINDOW_SLICE_STATES = frozenset({"succeeded", "failed", "not_attempted"})


class ScopedSearchError(ValueError):
    """Raised when a scoped request/runtime violates its machine contract."""


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
        self.execution_policy.validate()
        if self.duration is not None:
            self.duration.validate()
        if self.max_budget_twd is not None and (
            isinstance(self.max_budget_twd, bool)
            or not isinstance(self.max_budget_twd, int)
            or self.max_budget_twd <= 0
        ):
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
    return tuple(sorted(set(windows)))


def _window_id(window: AvailabilityWindow) -> str:
    return f"w-{window.start_date}-{window.end_date}"


def _request_payload(request: ScopedSearchRequest) -> Mapping[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": request.request_id,
        "availability_windows": [asdict(value) for value in _normalized_windows(request.availability_windows)],
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
    """Gate implementation-critical RP-03 machine SSOT against drift."""
    contract = _policy_contract(policy)
    if not contract:
        raise ScopedSearchError("missing ftr_handoff.scoped_search_acquisition policy")
    if contract.get("enabled") is not True or str(contract.get("contract_version") or "") != CONTRACT_VERSION:
        raise ScopedSearchError("scoped-search enablement/contract_version drifted")
    if contract.get("contract_state") != "implemented_pre_activation" or contract.get("mode") != "scoped_search":
        raise ScopedSearchError("scoped-search pre-activation mode drifted")

    request = _mapping(contract.get("request"))
    if tuple(request.get("required_fields") or ()) != ("request_id", "availability_windows", "execution_policy"):
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
    if windows.get("adjacent_date_pair_without_duration") != "allowed_pending_exact_minimum_away_truth":
        raise ScopedSearchError("scoped-search absent-duration adjacent-date semantics drifted")
    if windows.get("planner_calendar_difference_is_minimum_away_truth") is not False:
        raise ScopedSearchError("scoped-search planner must not invent minimum-away truth")

    acquisition = _mapping(contract.get("acquisition"))
    required_acquisition = {
        "reuse_source_router": True,
        "reuse_existing_provider_adapter": True,
        "reuse_exact_revalidation": True,
        "destination_discovery_surface": "gflights_google_flight_deals",
        "broad_horizon_then_post_filter": "forbidden",
        "search_horizon_days_reuse": "forbidden",
        "brute_force_city_date_city_matrix": "forbidden",
        "unconstrainable_surface_action": "not_attempted",
        "rp06_open_jaw_expansion": "out_of_scope",
    }
    for field, expected in required_acquisition.items():
        if acquisition.get(field) != expected:
            raise ScopedSearchError(f"scoped-search acquisition policy drifted: {field}")

    bounded = _mapping(contract.get("bounded_execution"))
    for field in ("max_windows", "max_discovery_calls", "max_exact_revalidations"):
        value = bounded.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ScopedSearchError(f"scoped-search {field} must be a positive integer")
    if bounded.get("request_may_lower_limits_only") is not True:
        raise ScopedSearchError("scoped-search request limit semantics drifted")
    if bounded.get("deterministic_ordering") is not True or bounded.get("deterministic_truncation") is not True:
        raise ScopedSearchError("scoped-search deterministic planning policy drifted")
    if bounded.get("search_horizon_days_is_scoped_budget") is not False:
        raise ScopedSearchError("search.horizon_days must not become scoped budget")
    if bounded.get("truncation_must_not_hide_unattempted_window") is not True:
        raise ScopedSearchError("scoped-search truncation/window coverage semantics drifted")

    identity = _mapping(contract.get("identity"))
    if identity.get("acquisition_identity") != "scoped_search":
        raise ScopedSearchError("scoped-search acquisition identity drifted")
    if identity.get("canonical_claim_consumption") != "forbidden":
        raise ScopedSearchError("scoped-search canonical claim isolation drifted")
    if identity.get("operator_reacquisition_identity_reuse") != "forbidden":
        raise ScopedSearchError("scoped-search operator identity isolation drifted")
    if identity.get("same_day_recovery_masquerade") != "forbidden":
        raise ScopedSearchError("scoped-search recovery identity isolation drifted")
    if identity.get("duplicate_request_semantics") != "replay_identical_fingerprint_reject_request_id_reuse":
        raise ScopedSearchError("scoped-search replay semantics drifted")

    semantics = _mapping(contract.get("semantics"))
    if semantics.get("formal_deal_truth") != "existing_cfr_anomaly_plus_exact_complete_airfare":
        raise ScopedSearchError("scoped-search Deal semantics drifted")
    if semantics.get("generic_signal_promotion") != "forbidden":
        raise ScopedSearchError("scoped-search Signal isolation drifted")
    if semantics.get("absolute_low_selector") != "ftr_handoff.absolute_low_non_deal_producer":
        raise ScopedSearchError("scoped-search RP-02 selector binding drifted")
    if semantics.get("rp06_eligibility_expansion") != "out_of_scope":
        raise ScopedSearchError("scoped-search RP-06 boundary drifted")

    coverage = _mapping(contract.get("coverage"))
    if coverage.get("reuse_ftr_handoff_slice_contract") is not True:
        raise ScopedSearchError("scoped-search coverage contract drifted")
    if coverage.get("zero_candidates_is_failure") is not False:
        raise ScopedSearchError("zero candidates must not imply scoped failure")
    required_coverage = {
        "unqueried_slice_success": "forbidden",
        "unsupported_surface_success": "forbidden",
        "unqueried_window_success": "forbidden",
        "zero_provider_call_status": "not_attempted",
        "missing_window_consumability": "fail_closed",
    }
    for field, expected in required_coverage.items():
        if coverage.get(field) != expected:
            raise ScopedSearchError(f"scoped-search coverage policy drifted: {field}")
    if coverage.get("availability_window_is_terminal_dimension") is not True:
        raise ScopedSearchError("scoped-search window terminal dimension drifted")
    if coverage.get("complete_empty_provider_response_may_succeed_window") is not True:
        raise ScopedSearchError("scoped-search complete-empty coverage semantics drifted")

    persistence = _mapping(contract.get("persistence"))
    if persistence.get("checksum_required") is not True or persistence.get("manifest_write_last") is not True:
        raise ScopedSearchError("scoped-search persistence ordering/checksum drifted")

    isolation = _mapping(contract.get("canonical_isolation"))
    for field in (
        "never_advance_canonical_latest",
        "never_mutate_current_status",
        "never_clear_repair_required",
        "never_replace_repair_incident",
        "never_consume_canonical_claim",
    ):
        if isolation.get(field) is not True:
            raise ScopedSearchError(f"scoped-search isolation flag drifted: {field}")

    activation = _mapping(contract.get("activation"))
    if activation.get("canonical_runtime") != "pending_disabled_until_RP-04" or activation.get("production_launch") != "out_of_scope":
        raise ScopedSearchError("scoped-search activation boundary drifted")
    if _mapping(_mapping(policy.get("ftr_handoff")).get("canonical_activation")).get("enabled") is not False:
        raise ScopedSearchError("RP-03 must not activate canonical FTR runtime")
    return contract


def _pair_allowed(nights: int, duration: DurationConstraint | None) -> bool:
    # Calendar-night difference is only a query-planning dimension. When the
    # user did not supply duration, adjacent dates remain eligible for exact
    # acquisition because actual arrival->departure time may still exceed 24h.
    if duration is None:
        return True
    if duration.min_nights is not None and nights < duration.min_nights:
        return False
    if duration.max_nights is not None and nights > duration.max_nights:
        return False
    return True


def _date_pairs(window: AvailabilityWindow, duration: DurationConstraint | None) -> tuple[tuple[str, str], ...]:
    start, end = window.dates()
    pairs: list[tuple[str, str]] = []
    outbound = start
    while outbound < end:
        returned = outbound + timedelta(days=1)
        while returned <= end:
            nights = (returned - outbound).days
            if _pair_allowed(nights, duration):
                pairs.append((outbound.isoformat(), returned.isoformat()))
            returned += timedelta(days=1)
        outbound += timedelta(days=1)
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
            departure, returned = pairs[pair_index]
            for origin in origins:
                candidates.append((pair_index, window_index, origin, departure, returned))

    selected = candidates[: request.execution_policy.max_discovery_calls]
    tasks: list[ScopedDiscoveryTask] = []
    for _, window_index, origin, departure, returned in selected:
        window = windows[window_index]
        window_id = _window_id(window)
        tasks.append(
            ScopedDiscoveryTask(
                task_id="scoped-discovery-" + _hash([fingerprint, window_id, origin, departure, returned])[:16],
                window_id=window_id,
                origin=origin,
                anchor_departure=departure,
                anchor_return=returned,
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
        if window_id == _window_id(window):
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
    if not result.request_sent:
        row["suppressed"] += 1
        return
    row["provider_calls"] += 1
    if result.coverage_state == "complete" and result.records:
        row["successes"] += 1
    elif result.coverage_state == "failed":
        row["failures"] += 1
    elif result.coverage_state == "unsupported":
        row["unsupported"] += 1
    else:
        row["empty"] += 1


def _window_execution_rows(plan: ScopedSearchPlan) -> dict[str, dict[str, Any]]:
    planned_counts: dict[str, int] = {_window_id(window): 0 for window in plan.windows}
    for task in plan.discovery_tasks:
        planned_counts[task.window_id] += 1
    return {
        _window_id(window): {
            "status": "not_attempted",
            "reason": None,
            "queryable_date_pairs": len(_date_pairs(window, plan.duration)),
            "planned_tasks": planned_counts[_window_id(window)],
            "attempts": 0,
            "provider_calls": 0,
            "records": 0,
            "successes": 0,
            "empty": 0,
            "failures": 0,
            "suppressed": 0,
            "unsupported": 0,
        }
        for window in plan.windows
    }


def _count_window_result(row: dict[str, Any], result: ProviderResult) -> None:
    row["records"] += len(result.records)
    if not result.request_sent:
        row["suppressed"] += 1
        return
    row["provider_calls"] += 1
    if result.coverage_state == "complete" and result.records:
        row["successes"] += 1
    elif result.coverage_state == "failed":
        row["failures"] += 1
    elif result.coverage_state == "unsupported":
        row["unsupported"] += 1
    else:
        row["empty"] += 1


def _finalize_window_execution(rows: Mapping[str, dict[str, Any]]) -> None:
    for row in rows.values():
        if int(row["attempts"]) == 0:
            row["status"] = "not_attempted"
            row["reason"] = "no_queryable_date_pair" if int(row["queryable_date_pairs"]) == 0 else "budget_unattempted"
            continue
        if int(row["failures"]) or int(row["unsupported"]) or int(row["suppressed"]):
            row["status"] = "failed"
            row["reason"] = "provider_or_routing_failure"
            continue
        provider_calls = int(row["provider_calls"])
        completed_calls = int(row["successes"]) + int(row["empty"])
        if provider_calls > 0 and completed_calls == provider_calls:
            row["status"] = "succeeded"
            row["reason"] = None
        else:
            row["status"] = "failed"
            row["reason"] = "inconsistent_execution"


def _normalized_window_coverage(plan: ScopedSearchPlan, rows: Mapping[str, Any]) -> Mapping[str, Any]:
    expected_ids = {_window_id(window) for window in plan.windows}
    if set(str(value) for value in rows) != expected_ids:
        raise FTRHandoffError("scoped window coverage does not match supplied windows")
    normalized: dict[str, Mapping[str, Any]] = {}
    for window in plan.windows:
        window_id = _window_id(window)
        raw = _mapping(rows.get(window_id))
        status = str(raw.get("status") or "")
        if status not in WINDOW_SLICE_STATES:
            raise FTRHandoffError(f"scoped window {window_id} has invalid coverage status")
        integer_fields = (
            "queryable_date_pairs",
            "planned_tasks",
            "attempts",
            "provider_calls",
            "records",
            "successes",
            "empty",
            "failures",
            "suppressed",
            "unsupported",
        )
        counters: dict[str, int] = {}
        for field in integer_fields:
            value = raw.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FTRHandoffError(f"scoped window {window_id}.{field} must be a nonnegative integer")
            counters[field] = value
        expected_pairs = len(_date_pairs(window, plan.duration))
        expected_planned = sum(task.window_id == window_id for task in plan.discovery_tasks)
        if counters["queryable_date_pairs"] != expected_pairs:
            raise FTRHandoffError(f"scoped window {window_id} queryable pair count mismatches request")
        if counters["planned_tasks"] != expected_planned or counters["attempts"] != expected_planned:
            raise FTRHandoffError(f"scoped window {window_id} execution does not match deterministic plan")
        if counters["provider_calls"] + counters["suppressed"] > counters["attempts"]:
            raise FTRHandoffError(f"scoped window {window_id} provider calls exceed attempts")
        if counters["successes"] + counters["empty"] + counters["failures"] > counters["provider_calls"]:
            raise FTRHandoffError(f"scoped window {window_id} provider outcomes exceed calls")
        reason = raw.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise FTRHandoffError(f"scoped window {window_id} reason must be text or null")
        if status == "succeeded":
            if (
                counters["provider_calls"] <= 0
                or counters["failures"]
                or counters["suppressed"]
                or counters["unsupported"]
                or counters["successes"] + counters["empty"] != counters["provider_calls"]
            ):
                raise FTRHandoffError(f"scoped window {window_id} succeeded without complete execution truth")
        elif status == "not_attempted":
            if counters["attempts"] or counters["provider_calls"]:
                raise FTRHandoffError(f"scoped window {window_id} not_attempted contradicts execution")
            expected_reason = "no_queryable_date_pair" if expected_pairs == 0 else "budget_unattempted"
            if reason != expected_reason:
                raise FTRHandoffError(f"scoped window {window_id} not_attempted reason is inconsistent")
        else:
            if not (
                counters["attempts"]
                and (counters["failures"] or counters["suppressed"] or counters["unsupported"] or reason == "inconsistent_execution")
            ):
                raise FTRHandoffError(f"scoped window {window_id} failed without failure evidence")
        normalized[window_id] = {"status": status, "reason": reason, **counters}
    return normalized


def _profile(record: AirfareRecord) -> str:
    market = market_slice(record.destination.country)
    return market if market in {"japan", "korea", "china"} else "world"


def _provider_health(
    *,
    origin_rows: Mapping[str, Mapping[str, Any]],
    flight_deals: Mapping[str, int],
    window_rows: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    statuses = [str(value.get("status") or "") for value in origin_rows.values()]
    attempted_count = sum(value != "not_attempted" for value in statuses)
    all_required_failed = bool(statuses) and attempted_count == len(statuses) and all(value == "failed" for value in statuses)
    window_statuses = [str(value.get("status") or "") for value in window_rows.values()]
    if all_required_failed and int(flight_deals.get("provider_calls", 0)) > 0:
        status = "provider_failed"
        reasons = ["all required scoped Flight Deals origin slices failed"]
    elif any(value != "attempted" for value in statuses) or any(value != "succeeded" for value in window_statuses):
        status = "degraded"
        reasons = ["bounded scoped plan left a required origin or availability window failed/not_attempted"]
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
        result[relative] = (
            path.exists(),
            hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "",
        )
    return result


def _assert_canonical_guard(history_dir: Path, before: Mapping[str, tuple[bool, str]]) -> None:
    if dict(_canonical_guard(history_dir)) != dict(before):
        raise FTRHandoffError("scoped_search mutated canonical latest/current-status isolation guard")


def _scoped_metadata(plan: ScopedSearchPlan, *, execution: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    payload: dict[str, Any] = {
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
    """Validate generic handoff plus query-specific window/identity invariants."""
    validate_snapshot(snapshot)
    if str(snapshot.get("mode") or "") != "scoped_search":
        raise FTRHandoffError("scoped snapshot mode must be scoped_search")
    scoped = _mapping(snapshot.get("scoped_search"))
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
            str(_mapping(value).get("start_date") or ""),
            str(_mapping(value).get("end_date") or ""),
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

    validation_plan = plan
    if validation_plan is None:
        execution_policy_raw = _mapping(scoped.get("execution_policy"))
        validation_plan = ScopedSearchPlan(
            request_id=request_id,
            request_fingerprint=fingerprint,
            plan_id=plan_id,
            windows=windows,
            discovery_tasks=tuple(
                ScopedDiscoveryTask(
                    task_id=str(_mapping(value).get("task_id") or ""),
                    window_id=str(_mapping(value).get("window_id") or ""),
                    origin=str(_mapping(value).get("origin") or ""),
                    anchor_departure=str(_mapping(value).get("anchor_departure") or ""),
                    anchor_return=str(_mapping(value).get("anchor_return") or ""),
                )
                for value in (scoped.get("discovery_plan") or [])
            ),
            discovery_truncated=bool(scoped.get("discovery_truncated")),
            duration=duration,
            max_budget_twd=max_budget,
            execution_policy=ScopedExecutionPolicy(
                max_discovery_calls=int(execution_policy_raw.get("max_discovery_calls") or 0),
                max_exact_revalidations=int(execution_policy_raw.get("max_exact_revalidations") or 0),
            ),
        )
        validation_plan.execution_policy.validate()

    scoped_execution = _mapping(scoped.get("execution"))
    window_execution = _mapping(scoped_execution.get("window_execution"))
    normalized_windows = _normalized_window_coverage(validation_plan, window_execution)
    persisted_windows = _mapping(_mapping(snapshot.get("coverage")).get("windows"))
    if dict(persisted_windows) != dict(normalized_windows):
        raise FTRHandoffError("scoped snapshot coverage.windows mismatches scoped execution truth")
    if any(str(value["status"]) != "succeeded" for value in normalized_windows.values()):
        raise FTRHandoffError("scoped window coverage incomplete; snapshot is not consumable")

    for opportunity in snapshot.get("opportunities") or []:
        for variant in _mapping(opportunity).get("variants") or []:
            try:
                outbound = date.fromisoformat(str(_mapping(variant).get("outbound_date") or ""))
                returned = date.fromisoformat(str(_mapping(variant).get("return_date") or ""))
            except ValueError as exc:
                raise FTRHandoffError("scoped snapshot variant dates invalid") from exc
            fitting_window = next(
                (
                    window
                    for window in windows
                    if window.dates()[0] <= outbound <= returned <= window.dates()[1]
                ),
                None,
            )
            if fitting_window is None:
                raise FTRHandoffError("scoped snapshot contains trip outside all supplied windows")
            nights = (returned - outbound).days
            if duration is not None:
                if duration.min_nights is not None and nights < duration.min_nights:
                    raise FTRHandoffError("scoped snapshot violates min_nights")
                if duration.max_nights is not None and nights > duration.max_nights:
                    raise FTRHandoffError("scoped snapshot violates max_nights")
            if max_budget is not None and int(_mapping(variant).get("complete_airfare_twd") or 0) > max_budget:
                raise FTRHandoffError("scoped snapshot violates request max_budget_twd")

    if plan is not None:
        expected = _scoped_metadata(plan)
        for key in (
            "contract_version",
            "request_id",
            "request_fingerprint",
            "plan_id",
            "availability_windows",
            "duration",
            "max_budget_twd",
            "execution_policy",
            "discovery_truncated",
            "discovery_plan",
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
    """Execute only supplied-window Flight Deals anchors and exact completion."""
    plan = build_scoped_plan(request, policy=policy)
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ScopedSearchError("run_at must be timezone-aware")
    run_id = f"ftr-scoped-{request.request_id}-{plan.request_fingerprint[:12]}"
    run_at_text = run_at.isoformat()
    execution = {name: _execution_row() for name in SCOPED_SURFACES}
    origins = tuple(str(value) for value in _mapping(policy.get("search")).get("origin_airports", ()))
    origin_state: dict[str, dict[str, Any]] = {
        origin: {
            "status": "not_attempted",
            "returned_flight_deals": 0,
            "explore_seeds": 0,
            "errors": [],
        }
        for origin in origins
    }
    market_rows = {
        market: {
            "status": "not_attempted",
            "coverage_basis": "scoped_shared_destination_free_origin_coverage",
            "discovered": 0,
            "qualified": 0,
            "revalidated": 0,
            "deals": 0,
        }
        for market in MARKETS
    }
    provider_failures: list[Mapping[str, str]] = []
    scoped_rows: list[tuple[AirfareRecord, str]] = []
    window_attempts = _window_execution_rows(plan)

    for task in plan.discovery_tasks:
        origin = task.origin
        window = _window_for_id(plan, task.window_id)
        execution["flight_deals"]["attempts"] += 1
        window_attempts[task.window_id]["attempts"] += 1
        scoped_horizon_days = (window.dates()[1] - window.dates()[0]).days + 1
        route_plan = build_source_plan(
            OriginSweepRequest(
                origin=origin,
                horizon_start=window.start_date,
                horizon_days=scoped_horizon_days,
                near_term_days=min(30, scoped_horizon_days),
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
            window_attempts[task.window_id]["unsupported"] += 1
            origin_state[origin]["status"] = "failed"
            message = route_plan.fallback_reason or "scoped Flight Deals routing unavailable"
            origin_state[origin]["errors"].append(message)
            provider_failures.append({
                "provider": "gflights",
                "origin": origin,
                "surface": "source_router",
                "error": message,
            })
            continue

        result = await adapter.flight_deals(
            origin=origin,
            anchor_departure=task.anchor_departure,
            anchor_return=task.anchor_return,
        )
        _count(execution, "flight_deals", result)
        _count_window_result(window_attempts[task.window_id], result)
        if result.coverage_state in {"failed", "unsupported"} or not result.request_sent:
            origin_state[origin]["status"] = "failed"
            message = result.error or result.coverage_state
            origin_state[origin]["errors"].append(message)
            if result.coverage_state == "failed" and result.request_sent:
                provider_failures.append({
                    "provider": result.provider,
                    "origin": origin,
                    "surface": "flight_deals",
                    "error": message,
                })
            continue

        if origin_state[origin]["status"] == "not_attempted":
            origin_state[origin]["status"] = "attempted"
        origin_state[origin]["returned_flight_deals"] += len(result.records)
        for record in result.records:
            if not is_international_asia_oceania(record.destination.country):
                continue
            if not _record_fits_window(record, window) or not _record_duration_allowed(record, plan.duration):
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

    _finalize_window_execution(window_attempts)
    normalized_window_coverage = _normalized_window_coverage(plan, window_attempts)

    if plan.discovery_truncated:
        for origin in origins:
            if origin_state[origin]["status"] == "not_attempted":
                origin_state[origin]["errors"].append("not reached under deterministic scoped discovery budget")

    pool = _dedupe_records(scoped_rows)
    selected = pool[: plan.execution_policy.max_exact_revalidations]
    deals: list[RadarItem] = []
    nondeals: list[RadarItem] = []
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
                "provider": "gflights",
                "origin": discovery.origin.iata,
                "surface": "source_router_exact",
                "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                "error": reason,
            })
            weak_signals.append(
                RadarItem(
                    "Signal",
                    "weak_seed",
                    discovery,
                    None,
                    discovery.anomaly_authority,
                    discovery.discount_percent,
                    reason,
                )
            )
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
                    "provider": exact_result.provider,
                    "origin": discovery.origin.iata,
                    "surface": "exact",
                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}",
                    "error": message,
                })
            weak_signals.append(
                RadarItem(
                    "Signal",
                    "weak_seed",
                    discovery,
                    None,
                    discovery.anomaly_authority,
                    discovery.discount_percent,
                    f"scoped exact revalidation failed closed: {message}",
                )
            )
            continue

        exact = exact_result.records[0]
        if (
            exact.origin.iata != discovery.origin.iata
            or exact.destination.iata != discovery.destination.iata
            or exact.outbound_date != discovery.outbound_date
            or exact.return_date != discovery.return_date
            or not _record_fits_window(exact, window)
            or not _record_duration_allowed(exact, plan.duration)
        ):
            weak_signals.append(
                RadarItem(
                    "Signal",
                    "weak_seed",
                    discovery,
                    None,
                    discovery.anomaly_authority,
                    discovery.discount_percent,
                    "exact provider result violated scoped route/date/window contract",
                )
            )
            continue
        if exact.verification_state != "revalidated" or not exact.complete_airfare or not exact.current_price_twd:
            weak_signals.append(
                RadarItem(
                    "Signal",
                    "exact_revalidated_candidate",
                    discovery,
                    exact,
                    discovery.anomaly_authority,
                    None,
                    "exact surface did not yield revalidated complete airfare",
                )
            )
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
            deals.append(
                RadarItem(
                    "Deal",
                    "deal",
                    discovery,
                    exact,
                    truth.source,
                    discount,
                    "qualified anomaly authority plus current scoped exact complete airfare",
                    observation.observation_id,
                    anomaly_baseline_twd=baseline,
                    anomaly_scope=(
                        "destination_airport_all_taiwan_origins"
                        if truth.source in {"google_flight_deals", "own_price_history"}
                        else "selected_authority_scope"
                    ),
                )
            )
            market_rows[market]["deals"] += 1
        else:
            nondeals.append(
                RadarItem(
                    "Signal",
                    "exact_revalidated_candidate",
                    discovery,
                    exact,
                    truth.source if truth is not None else None,
                    discount,
                    "scoped exact current airfare revalidated, but no qualified positive anomaly truth remained",
                    observation.observation_id,
                )
            )

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

    if all(origin_state[origin]["status"] == "not_attempted" for origin in origins):
        market_status = "not_attempted"
    elif all(origin_state[origin]["status"] == "attempted" for origin in origins):
        market_status = "succeeded"
    else:
        market_status = "failed"
    for market in MARKETS:
        market_rows[market]["status"] = market_status

    health = _provider_health(
        origin_rows=origin_state,
        flight_deals=execution["flight_deals"],
        window_rows=normalized_window_coverage,
    )
    flight_deals_execution = execution["flight_deals"]
    if (
        flight_deals_execution["failures"]
        or flight_deals_execution["unsupported"]
        or flight_deals_execution["suppressed"]
    ):
        provider_slice_status = "failed"
    elif flight_deals_execution["provider_calls"] > 0:
        provider_slice_status = "succeeded"
    else:
        provider_slice_status = "not_attempted"
    coverage = {
        "origins": origin_state,
        "markets": market_rows,
        "windows": normalized_window_coverage,
        "execution": execution,
        "all_origins_attempted": all(value["status"] != "not_attempted" for value in origin_state.values()),
        "destination_scope": "asia_oceania",
        "provider_health": health,
        "provider_execution": {
            "gflights": {
                "status": provider_slice_status,
                "health_status": health["status"],
                "surfaces": ["flight_deals", "exact"],
                "reasons": list(health["reasons"]),
            }
        },
    }
    base = RadarRunResult(
        radar_run_id=run_id,
        run_at=run_at_text,
        deals=tuple(deals),
        signals=tuple([*weak_signals, *nondeals]),
        coverage=coverage,
        provider_failures=tuple(provider_failures),
        exact_non_deal_candidates=tuple(nondeals),
    )
    result = apply_absolute_low_selection(base, policy=policy)
    return plan, result, {
        "window_execution": normalized_window_coverage,
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
    """Execute/stage scoped handoff with replay and canonical byte guards."""
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
        run_json = _run_result_json(
            result,
            provider_health=_mapping(health),
            scoped_execution=scoped_execution,
        )
        base_snapshot = build_snapshot(
            run_json,
            producer_commit_sha=producer_commit_sha,
            mode="scoped_search",
            generated_at=generated_at,
        )
        snapshot = dict(base_snapshot)
        snapshot_coverage = dict(_mapping(snapshot.get("coverage")))
        snapshot_coverage["windows"] = {
            str(key): dict(_mapping(value))
            for key, value in _mapping(scoped_execution.get("window_execution")).items()
        }
        snapshot["coverage"] = snapshot_coverage
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
