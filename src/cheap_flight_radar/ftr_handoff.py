"""CFR immutable snapshot primitives (downstream FTR feed retired).

This module is a deterministic snapshot/manifest primitive for CFR's own
scoped-search evidence. It does not schedule or perform airfare acquisition.
The Family Trip Radar downstream feed (canonical latest, current status and
repair orchestration) has been retired; only scoped-search snapshots stage here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


# RP-01 advances the pre-activation contract major because coverage slice state
# and freshness meaning change incompatibly from the 1.0 implementation.
SCHEMA_VERSION = "2.0"
SUPPORTED_SCHEMA_MAJOR = 2
VALID_MODES = frozenset({"canonical_daily", "scoped_search", "same_day_recovery"})
VALID_SNAPSHOT_FRESHNESS_STATES = frozenset({"fresh", "degraded"})
VALID_FRESHNESS_STATES = VALID_SNAPSHOT_FRESHNESS_STATES  # compatibility alias
VALID_SLICE_STATES = frozenset({"succeeded", "failed", "not_attempted"})
VALID_CANDIDATE_KINDS = frozenset({"deal", "absolute_low_non_deal"})
VALID_PROVIDER_HEALTH_STATES = frozenset({"healthy", "degraded", "provider_failed"})
REQUIRED_DISCOVERY_SURFACES = frozenset({"flight_deals", "explore"})


class FTRHandoffError(ValueError):
    """Raised when producer data cannot satisfy the FTR handoff contract."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _aware_timestamp(value: Any, *, field: str) -> str:
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FTRHandoffError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FTRHandoffError(f"{field} must be timezone-aware")
    return text


def _safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not safe:
        raise FTRHandoffError("run_id must contain a path-safe component")
    return safe


def _schema_major(version: Any) -> int:
    match = re.fullmatch(r"(\d+)\.(\d+)", str(version or ""))
    if not match:
        raise FTRHandoffError("schema_version must use MAJOR.MINOR")
    return int(match.group(1))


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise FTRHandoffError(f"{field} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FTRHandoffError(f"{field} must be a non-negative integer") from exc
    if result < 0:
        raise FTRHandoffError(f"{field} must be a non-negative integer")
    return result


def _record_for_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(item.get("exact")) or _mapping(item.get("discovery"))


def _record_iata(record: Mapping[str, Any], field: str) -> str:
    value = str(_mapping(record.get(field)).get("iata") or "")
    if len(value) != 3 or value != value.upper() or not value.isalpha():
        raise FTRHandoffError(f"record {field} must contain exact uppercase IATA")
    return value


def _outbound_date(record: Mapping[str, Any]) -> str:
    legs = record.get("legs")
    if not isinstance(legs, Sequence) or isinstance(legs, (str, bytes)) or not legs:
        raise FTRHandoffError("airfare variant requires at least one normalized leg")
    value = str(_mapping(legs[0]).get("date") or "")
    if not value:
        raise FTRHandoffError("airfare variant missing outbound date")
    return value


def _return_date(record: Mapping[str, Any]) -> str:
    requested = _mapping(record.get("reproducible_search")).get("return_date")
    if isinstance(requested, str) and requested:
        return requested
    legs = record.get("legs")
    if isinstance(legs, Sequence) and not isinstance(legs, (str, bytes)) and len(legs) > 1:
        value = str(_mapping(legs[-1]).get("date") or "")
        if value:
            return value
    raise FTRHandoffError("airfare variant missing return date")


def _candidate_kind(item: Mapping[str, Any]) -> str | None:
    if str(item.get("classification") or "") == "Deal" and str(item.get("state") or "") == "deal":
        return "deal"
    if (
        str(item.get("classification") or "") == "Signal"
        and str(item.get("state") or "") == "ftr_absolute_low_non_deal"
    ):
        return "absolute_low_non_deal"
    return None


def _destination_route_shape(record: Mapping[str, Any]) -> tuple[str, str]:
    arrival = _record_iata(record, "destination")
    departure = arrival
    if str(record.get("surface") or "") == "open_jaw":
        legs = record.get("legs")
        if isinstance(legs, Sequence) and not isinstance(legs, (str, bytes)) and len(legs) >= 2:
            candidate = str(_mapping(legs[-1]).get("origin") or "")
            if len(candidate) == 3 and candidate == candidate.upper() and candidate.isalpha():
                departure = candidate
    return arrival, departure


def _taiwan_return_gateway(record: Mapping[str, Any], *, outbound_gateway: str) -> str:
    if str(record.get("surface") or "") == "open_jaw":
        legs = record.get("legs")
        if isinstance(legs, Sequence) and not isinstance(legs, (str, bytes)) and len(legs) >= 2:
            candidate = str(_mapping(legs[-1]).get("destination") or "")
            if len(candidate) == 3 and candidate == candidate.upper() and candidate.isalpha():
                return candidate
    return outbound_gateway


def _variant_from_item(item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    kind = _candidate_kind(item)
    if kind is None:
        return None
    record = _record_for_item(item)
    if not record:
        raise FTRHandoffError("eligible airfare item is missing a normalized record")
    if not bool(record.get("complete_airfare")):
        raise FTRHandoffError("eligible airfare item must contain complete airfare")
    try:
        fare = int(item.get("current_complete_airfare_twd") or record.get("current_price_twd") or 0)
    except (TypeError, ValueError) as exc:
        raise FTRHandoffError("complete airfare must be an integer TWD amount") from exc
    if fare <= 0:
        raise FTRHandoffError("complete airfare must be positive")

    outbound_gateway = _record_iata(record, "origin")
    arrival_airport, departure_airport = _destination_route_shape(record)
    record_id = str(record.get("record_id") or "")
    if not record_id:
        raise FTRHandoffError("eligible airfare item missing record_id")
    airlines = record.get("airlines")
    if not isinstance(airlines, Sequence) or isinstance(airlines, (str, bytes)):
        airlines = ()
    legs = record.get("legs")
    normalized_legs = list(legs) if isinstance(legs, Sequence) and not isinstance(legs, (str, bytes)) else []
    origin_identity = _mapping(record.get("origin"))
    destination_identity = _mapping(record.get("destination"))
    return {
        "variant_id": record_id,
        "candidate_kind": kind,
        "source_type": "cfr_deal" if kind == "deal" else "cfr_absolute_low_non_deal",
        "observed_at": _aware_timestamp(record.get("observed_at"), field="variant.observed_at"),
        "complete_airfare_twd": fare,
        "outbound_date": _outbound_date(record),
        "return_date": _return_date(record),
        "taiwan_origin_gateway": outbound_gateway,
        "taiwan_return_gateway": _taiwan_return_gateway(record, outbound_gateway=outbound_gateway),
        "destination_route_shape": {"arrival_airport": arrival_airport, "departure_airport": departure_airport},
        "destination": {"city": destination_identity.get("city"), "country": destination_identity.get("country")},
        "airlines": [str(value) for value in airlines],
        "legs": normalized_legs,
        "verification_state": record.get("verification_state"),
        "evidence": {
            "classification": item.get("classification"),
            "state": item.get("state"),
            "observation_id": item.get("observation_id"),
            "record_id": record_id,
            "provider": record.get("provider"),
            "surface": record.get("surface"),
            "url": record.get("evidence_url") or record.get("booking_url"),
        },
        "taiwan_origin_city": origin_identity.get("city"),
    }


def _surface_state(name: str, raw: Mapping[str, Any]) -> Mapping[str, Any]:
    required = ("attempts", "provider_calls", "records", "successes", "empty", "failures", "suppressed", "unsupported")
    counters = {key: _nonnegative_int(raw.get(key), field=f"coverage.execution.{name}.{key}") for key in required}
    attempts = counters["attempts"]
    provider_calls = counters["provider_calls"]
    if provider_calls + counters["suppressed"] > attempts:
        raise FTRHandoffError(f"coverage.execution.{name} has more provider/suppressed calls than attempts")
    if counters["successes"] + counters["empty"] + counters["failures"] > provider_calls:
        raise FTRHandoffError(f"coverage.execution.{name} outcomes exceed provider_calls")

    exact_keys = ("exact_attempts", "exact_provider_calls", "exact_successes", "exact_empty", "exact_failures", "exact_suppressed")
    for key in exact_keys:
        if key in raw:
            counters[key] = _nonnegative_int(raw.get(key), field=f"coverage.execution.{name}.{key}")
    if "exact_attempts" in counters:
        if counters.get("exact_provider_calls", 0) + counters.get("exact_suppressed", 0) > counters["exact_attempts"]:
            raise FTRHandoffError(f"coverage.execution.{name} exact calls exceed exact_attempts")
        if counters.get("exact_successes", 0) + counters.get("exact_empty", 0) + counters.get("exact_failures", 0) > counters.get("exact_provider_calls", 0):
            raise FTRHandoffError(f"coverage.execution.{name} exact outcomes exceed exact_provider_calls")

    failed = bool(
        counters["failures"] or counters["suppressed"] or counters["unsupported"]
        or counters.get("exact_failures", 0) or counters.get("exact_suppressed", 0)
    )
    if attempts == 0 and counters["unsupported"] == 0:
        status = "not_attempted"
    elif failed:
        status = "failed"
    else:
        status = "succeeded"
    return {"status": status, "execution": counters}


def _origin_state(origin: str, raw: Mapping[str, Any]) -> Mapping[str, Any]:
    source_status = str(raw.get("status") or "")
    source_to_slice = {
        "attempted": "succeeded", "complete": "succeeded", "degraded": "failed",
        "failed": "failed", "not_attempted": "not_attempted",
    }
    if source_status not in source_to_slice:
        raise FTRHandoffError(f"unknown origin coverage state for {origin}: {source_status or '<missing>'}")
    return {
        "status": source_to_slice[source_status],
        "source_status": source_status,
        "returned_flight_deals": _nonnegative_int(raw.get("returned_flight_deals", 0), field=f"coverage.origins.{origin}.returned_flight_deals"),
        "explore_seeds": _nonnegative_int(raw.get("explore_seeds", 0), field=f"coverage.origins.{origin}.explore_seeds"),
        "errors": [str(value) for value in (raw.get("errors") or [])],
    }


def _market_state(market: str, raw: Mapping[str, Any], origin_states: Sequence[str]) -> Mapping[str, Any]:
    source_status = raw.get("status")
    if source_status is None:
        if origin_states and all(value == "succeeded" for value in origin_states):
            status, basis = "succeeded", "shared_destination_free_origin_coverage"
        elif origin_states and all(value == "not_attempted" for value in origin_states):
            status, basis = "not_attempted", "shared_destination_free_origin_coverage"
        elif origin_states:
            status, basis = "failed", "shared_destination_free_origin_coverage"
        else:
            raise FTRHandoffError(f"market coverage for {market} has no execution basis")
    else:
        source_to_slice = {
            "attempted": "succeeded", "complete": "succeeded", "succeeded": "succeeded",
            "degraded": "failed", "failed": "failed", "not_attempted": "not_attempted",
        }
        source = str(source_status)
        if source not in source_to_slice:
            raise FTRHandoffError(f"unknown market coverage state for {market}: {source}")
        status = source_to_slice[source]
        basis = str(raw.get("coverage_basis") or "explicit_market_execution")
    metrics: dict[str, int] = {}
    for key, value in raw.items():
        if key not in {"status", "coverage_basis"}:
            metrics[str(key)] = _nonnegative_int(value, field=f"coverage.markets.{market}.{key}")
    return {"status": status, "basis": basis, "metrics": metrics}


def _provider_ids(run_result: Mapping[str, Any], coverage: Mapping[str, Any]) -> tuple[str, ...]:
    providers: set[str] = set()
    explicit = coverage.get("provider_execution")
    if isinstance(explicit, Mapping):
        providers.update(str(value) for value in explicit.keys() if str(value))
    for raw in [*(run_result.get("deals") or []), *(run_result.get("signals") or [])]:
        if isinstance(raw, Mapping):
            provider = str(_record_for_item(raw).get("provider") or "")
            if provider:
                providers.add(provider)
    for raw in run_result.get("provider_failures") or []:
        if isinstance(raw, Mapping):
            provider = str(raw.get("provider") or "")
            if provider:
                providers.add(provider)
    return tuple(sorted(providers))


def summarize_coverage(run_result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Normalize real execution evidence into slice-faithful FTR coverage."""
    coverage = _mapping(run_result.get("coverage"))
    if not coverage:
        raise FTRHandoffError("producer run is missing coverage evidence")
    provider_health = _mapping(run_result.get("provider_health") or coverage.get("provider_health"))
    health_status = str(provider_health.get("status") or "")
    if health_status not in VALID_PROVIDER_HEALTH_STATES:
        raise FTRHandoffError("producer run is missing recognized provider_health status")

    execution_raw = _mapping(coverage.get("execution"))
    if not execution_raw:
        raise FTRHandoffError("producer run is missing surface execution evidence")
    surfaces = {str(name): _surface_state(str(name), _mapping(raw)) for name, raw in execution_raw.items()}
    missing_required = REQUIRED_DISCOVERY_SURFACES.difference(surfaces)
    if missing_required:
        raise FTRHandoffError("producer run is missing required discovery surfaces: " + ", ".join(sorted(missing_required)))

    origins_raw = _mapping(coverage.get("origins"))
    if not origins_raw:
        raise FTRHandoffError("producer run is missing origin coverage evidence")
    origins = {str(origin): _origin_state(str(origin), _mapping(raw)) for origin, raw in origins_raw.items()}
    origin_states = [str(value["status"]) for value in origins.values()]
    all_origins_attempted = coverage.get("all_origins_attempted")
    if all_origins_attempted is True and any(value == "not_attempted" for value in origin_states):
        raise FTRHandoffError("all_origins_attempted contradicts a not_attempted origin slice")
    if all_origins_attempted is False and all(value == "succeeded" for value in origin_states):
        raise FTRHandoffError("all_origins_attempted=false contradicts succeeded origin slices")
    if health_status == "healthy" and any(value != "succeeded" for value in origin_states):
        raise FTRHandoffError("healthy provider status contradicts failed/not-attempted origin coverage")

    markets_raw = _mapping(coverage.get("markets"))
    if not markets_raw:
        raise FTRHandoffError("producer run is missing market coverage evidence")
    markets = {str(name): _market_state(str(name), _mapping(raw), origin_states) for name, raw in markets_raw.items()}

    provider_ids = _provider_ids(run_result, coverage)
    if not provider_ids:
        raise FTRHandoffError("provider identity cannot be traced from execution/record evidence")
    explicit_provider_execution = _mapping(coverage.get("provider_execution"))
    if len(provider_ids) > 1 and not explicit_provider_execution:
        raise FTRHandoffError("multiple providers require explicit per-provider execution evidence")

    providers: dict[str, Mapping[str, Any]] = {}
    if explicit_provider_execution:
        for provider in provider_ids:
            raw = _mapping(explicit_provider_execution.get(provider))
            status = str(raw.get("status") or "")
            if status not in VALID_SLICE_STATES:
                raise FTRHandoffError(f"provider {provider} requires explicit succeeded/failed/not_attempted state")
            providers[provider] = {
                "status": status,
                "health_status": str(raw.get("health_status") or health_status),
                "surfaces": [str(value) for value in (raw.get("surfaces") or [])],
                "reasons": [str(value) for value in (raw.get("reasons") or provider_health.get("reasons") or [])],
            }
    else:
        provider = provider_ids[0]
        providers[provider] = {
            "status": "succeeded" if health_status == "healthy" else "failed",
            "health_status": health_status,
            "surfaces": sorted(surfaces),
            "reasons": [str(value) for value in (provider_health.get("reasons") or [])],
        }

    if health_status == "provider_failed" and all(value["status"] == "succeeded" for value in providers.values()):
        raise FTRHandoffError("provider_failed health contradicts succeeded provider execution")

    failed_slice = any(value["status"] == "failed" for value in surfaces.values())
    failed_slice = failed_slice or any(value["status"] != "succeeded" for value in origins.values())
    failed_slice = failed_slice or any(value["status"] != "succeeded" for value in markets.values())
    required_surface_gap = any(surfaces[name]["status"] != "succeeded" for name in REQUIRED_DISCOVERY_SURFACES)
    if health_status == "provider_failed":
        overall_state = "failed"
    elif health_status == "degraded" or failed_slice or required_surface_gap:
        overall_state = "degraded"
    else:
        overall_state = "complete"
    return {
        "providers": providers,
        "surfaces": surfaces,
        "origins": origins,
        "markets": markets,
        "provider_health": dict(provider_health),
        "provider_failures": [dict(value) for value in (run_result.get("provider_failures") or []) if isinstance(value, Mapping)],
        "overall_state": overall_state,
        "semantics": "execution_and_coverage_evidence_not_candidate_or_deal_count",
    }


def build_snapshot(
    run_result: Mapping[str, Any], *, producer_commit_sha: str,
    mode: str | None = None, generated_at: str | None = None,
) -> Mapping[str, Any]:
    run_id = str(run_result.get("radar_run_id") or run_result.get("run_id") or "")
    if not run_id:
        raise FTRHandoffError("run_result missing run_id")
    observed_at = _aware_timestamp(run_result.get("run_at") or run_result.get("observed_at"), field="observed_at")
    resolved_mode = str(mode or run_result.get("execution_mode") or "canonical_daily")
    if resolved_mode not in VALID_MODES:
        raise FTRHandoffError(f"unsupported handoff mode: {resolved_mode}")
    if not str(producer_commit_sha or "").strip():
        raise FTRHandoffError("producer_commit_sha is required")
    generated = _aware_timestamp(generated_at or datetime.now(timezone.utc).isoformat(), field="generated_at")

    coverage = summarize_coverage(run_result)
    coverage_state = str(coverage["overall_state"])
    if coverage_state == "failed":
        raise FTRHandoffError("provider_failed run is not consumable as a fresh FTR snapshot")
    freshness_state = "fresh" if coverage_state == "complete" else "degraded"

    items: list[Mapping[str, Any]] = []
    for raw in run_result.get("deals") or []:
        if not isinstance(raw, Mapping):
            raise FTRHandoffError("run_result deals must contain JSON objects")
        variant = _variant_from_item(raw)
        if variant is None or variant["candidate_kind"] != "deal":
            raise FTRHandoffError("run_result deals must retain formal Deal identity")
        items.append(variant)
    for raw in run_result.get("ftr_absolute_low_non_deals") or []:
        if not isinstance(raw, Mapping):
            raise FTRHandoffError("run_result ftr_absolute_low_non_deals must contain JSON objects")
        variant = _variant_from_item(raw)
        if variant is None or variant["candidate_kind"] != "absolute_low_non_deal":
            raise FTRHandoffError("dedicated absolute-low collection contains a non-selected item")
        items.append(variant)

    by_variant: dict[str, Mapping[str, Any]] = {}
    for variant in items:
        variant_id = str(variant["variant_id"])
        incumbent = by_variant.get(variant_id)
        if incumbent is None:
            by_variant[variant_id] = variant
            continue
        incumbent_rank = 0 if incumbent["candidate_kind"] == "deal" else 1
        variant_rank = 0 if variant["candidate_kind"] == "deal" else 1
        if (variant_rank, int(variant["complete_airfare_twd"])) < (incumbent_rank, int(incumbent["complete_airfare_twd"])):
            by_variant[variant_id] = variant

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for variant in by_variant.values():
        shape = _mapping(variant["destination_route_shape"])
        grouped.setdefault((str(shape["arrival_airport"]), str(shape["departure_airport"])), []).append(variant)

    opportunities: list[Mapping[str, Any]] = []
    for (arrival, departure), variants in sorted(grouped.items()):
        variants.sort(key=lambda value: (
            int(value["complete_airfare_twd"]), str(value["outbound_date"]),
            str(value["return_date"]), str(value["variant_id"]),
        ))
        opportunities.append({
            "opportunity_id": f"air-{arrival.lower()}-{departure.lower()}",
            "destination_route_shape": {"arrival_airport": arrival, "departure_airport": departure},
            "variants": variants,
        })

    snapshot: Mapping[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "mode": resolved_mode,
        "observed_at": observed_at,
        "generated_at": generated,
        "producer_commit_sha": str(producer_commit_sha),
        "terminal_state": "success",
        "coverage_state": coverage_state,
        "freshness_state": freshness_state,
        "coverage": coverage,
        "candidate_counts": {
            "opportunities": len(opportunities),
            "variants": sum(len(value["variants"]) for value in opportunities),
            "deals": sum(1 for value in opportunities for variant in value["variants"] if variant["candidate_kind"] == "deal"),
            "absolute_low_non_deals": sum(1 for value in opportunities for variant in value["variants"] if variant["candidate_kind"] == "absolute_low_non_deal"),
        },
        "opportunities": opportunities,
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: Mapping[str, Any], *, supported_major: int = SUPPORTED_SCHEMA_MAJOR) -> None:
    major = _schema_major(snapshot.get("schema_version"))
    if major != supported_major:
        raise FTRHandoffError(f"unsupported schema major: {major}")
    if str(snapshot.get("mode") or "") not in VALID_MODES:
        raise FTRHandoffError("snapshot mode is unsupported")
    _aware_timestamp(snapshot.get("observed_at"), field="observed_at")
    _aware_timestamp(snapshot.get("generated_at"), field="generated_at")
    if str(snapshot.get("terminal_state") or "") != "success":
        raise FTRHandoffError("snapshot terminal_state must be success")
    coverage_state = str(snapshot.get("coverage_state") or "")
    if coverage_state not in {"complete", "degraded"}:
        raise FTRHandoffError("snapshot coverage_state must be complete or degraded")
    freshness_state = str(snapshot.get("freshness_state") or "")
    if freshness_state not in VALID_SNAPSHOT_FRESHNESS_STATES:
        raise FTRHandoffError("snapshot freshness_state must be fresh or degraded; stale_reference belongs to current status")
    if (coverage_state == "complete") != (freshness_state == "fresh"):
        raise FTRHandoffError("snapshot coverage/freshness states are inconsistent")
    coverage = _mapping(snapshot.get("coverage"))
    if str(coverage.get("overall_state") or "") != coverage_state:
        raise FTRHandoffError("snapshot coverage_state does not match normalized coverage")
    for dimension in ("providers", "surfaces", "origins", "markets"):
        slices = _mapping(coverage.get(dimension))
        if not slices:
            raise FTRHandoffError(f"snapshot coverage missing {dimension}")
        for name, raw in slices.items():
            if str(_mapping(raw).get("status") or "") not in VALID_SLICE_STATES:
                raise FTRHandoffError(f"snapshot {dimension}.{name} has unknown coverage state")
    if not str(snapshot.get("run_id") or ""):
        raise FTRHandoffError("snapshot run_id is required")
    if not str(snapshot.get("producer_commit_sha") or ""):
        raise FTRHandoffError("snapshot producer_commit_sha is required")
    opportunities = snapshot.get("opportunities")
    if not isinstance(opportunities, list):
        raise FTRHandoffError("snapshot opportunities must be a list")
    for opportunity in opportunities:
        if not isinstance(opportunity, Mapping):
            raise FTRHandoffError("opportunity must be an object")
        shape = _mapping(opportunity.get("destination_route_shape"))
        for key in ("arrival_airport", "departure_airport"):
            value = str(shape.get(key) or "")
            if len(value) != 3 or value != value.upper() or not value.isalpha():
                raise FTRHandoffError(f"opportunity route shape missing valid {key}")
        variants = opportunity.get("variants")
        if not isinstance(variants, list) or not variants:
            raise FTRHandoffError("opportunity must retain at least one variant")
        for variant in variants:
            if not isinstance(variant, Mapping):
                raise FTRHandoffError("variant must be an object")
            if str(variant.get("candidate_kind") or "") not in VALID_CANDIDATE_KINDS:
                raise FTRHandoffError("variant candidate_kind is unsupported")
            if int(variant.get("complete_airfare_twd") or 0) <= 0:
                raise FTRHandoffError("variant complete_airfare_twd must be positive")
            _aware_timestamp(variant.get("observed_at"), field="variant.observed_at")
            for gateway_field in ("taiwan_origin_gateway", "taiwan_return_gateway"):
                gateway = str(variant.get(gateway_field) or "")
                if len(gateway) != 3 or gateway != gateway.upper() or not gateway.isalpha():
                    raise FTRHandoffError(f"variant missing valid {gateway_field}")


def snapshot_repository_path(snapshot: Mapping[str, Any]) -> str:
    observed = datetime.fromisoformat(_aware_timestamp(snapshot.get("observed_at"), field="observed_at").replace("Z", "+00:00"))
    return f"data/scoped-search/{observed:%Y/%m/%d}/{_safe_component(str(snapshot.get('run_id') or ''))}.json"


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def snapshot_checksum(snapshot: Mapping[str, Any]) -> str:
    validate_snapshot(snapshot)
    return hashlib.sha256(_json_bytes(snapshot)).hexdigest()


def manifest_for_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_snapshot(snapshot)
    return {
        "schema_version": str(snapshot["schema_version"]),
        "run_id": str(snapshot["run_id"]),
        "mode": str(snapshot["mode"]),
        "observed_at": str(snapshot["observed_at"]),
        "generated_at": str(snapshot["generated_at"]),
        "producer_commit_sha": str(snapshot["producer_commit_sha"]),
        "coverage_state": str(snapshot["coverage_state"]),
        "freshness_state": str(snapshot["freshness_state"]),
        "terminal_state": str(snapshot["terminal_state"]),
        "snapshot_path": snapshot_repository_path(snapshot),
        "snapshot_sha256": snapshot_checksum(snapshot),
    }


def manifest_repository_path(snapshot: Mapping[str, Any]) -> str:
    mode = str(snapshot.get("mode") or "")
    if mode == "scoped_search":
        return f"data/scoped-search/{_safe_component(str(snapshot.get('run_id') or ''))}.json"
    raise FTRHandoffError(f"retired handoff mode is no longer stageable: {mode}")


def _read_json_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FTRHandoffError(f"{label} is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise FTRHandoffError(f"{label} must be a JSON object")
    return raw


def stage_snapshot(*, history_dir: Path, snapshot: Mapping[str, Any]) -> Mapping[str, str]:
    """Write immutable snapshot first and manifest last."""
    validate_snapshot(snapshot)
    snapshot_rel = snapshot_repository_path(snapshot)
    manifest_rel = manifest_repository_path(snapshot)

    snapshot_path = history_dir / snapshot_rel
    snapshot_data = _json_bytes(snapshot)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.exists():
        if snapshot_path.read_bytes() != snapshot_data:
            raise FileExistsError(f"immutable FTR snapshot already exists with different content: {snapshot_path}")
    else:
        _atomic_write(snapshot_path, snapshot_data)
    manifest = manifest_for_snapshot(snapshot)
    _atomic_write(history_dir / manifest_rel, _json_bytes(manifest))
    return {"snapshot_path": snapshot_rel, "manifest_path": manifest_rel, "snapshot_sha256": str(manifest["snapshot_sha256"])}


def load_manifest_snapshot(
    *, history_dir: Path, manifest_path: str,
    supported_major: int = SUPPORTED_SCHEMA_MAJOR,
) -> Mapping[str, Any]:
    manifest_file = history_dir / manifest_path
    if not manifest_file.exists():
        raise FTRHandoffError(f"handoff manifest missing: {manifest_path}")
    manifest = _read_json_mapping(manifest_file, label="handoff manifest")
    if _schema_major(manifest.get("schema_version")) != supported_major:
        raise FTRHandoffError("handoff manifest schema major unsupported")
    if str(manifest.get("terminal_state") or "") != "success":
        raise FTRHandoffError("handoff manifest is not terminal success")
    snapshot_rel = str(manifest.get("snapshot_path") or "")
    if not snapshot_rel:
        raise FTRHandoffError("handoff manifest missing snapshot_path")
    snapshot_file = history_dir / snapshot_rel
    if not snapshot_file.exists():
        raise FTRHandoffError("handoff snapshot referenced by manifest is missing")
    payload = snapshot_file.read_bytes()
    if hashlib.sha256(payload).hexdigest() != str(manifest.get("snapshot_sha256") or ""):
        raise FTRHandoffError("handoff snapshot checksum mismatch")
    try:
        snapshot = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FTRHandoffError("handoff snapshot is unreadable") from exc
    if not isinstance(snapshot, Mapping):
        raise FTRHandoffError("handoff snapshot must be a JSON object")
    validate_snapshot(snapshot, supported_major=supported_major)
    if str(snapshot.get("run_id")) != str(manifest.get("run_id")):
        raise FTRHandoffError("handoff manifest/snapshot run_id mismatch")
    return snapshot
