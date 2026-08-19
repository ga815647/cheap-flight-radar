"""Durable Cheap Flight Radar -> Family Trip Radar handoff contract.

The handoff is deliberately narrower than CFR's own evidence archive.  It
contains normalized, current airfare opportunity variants that FTR can combine
with home access, lodging and whole-trip reasoning without inheriting CFR's
anomaly score as a travel-value score.

This module is a deterministic contract/persistence primitive.  It does not
schedule acquisition and it does not decide which non-Deal fares deserve the
``absolute_low_non_deal`` label.  That label must be produced explicitly by the
upstream acquisition path; arbitrary Signals are never promoted here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_MAJOR = 1
VALID_MODES = frozenset({"canonical_daily", "scoped_search", "same_day_recovery"})
VALID_FRESHNESS_STATES = frozenset({"fresh", "degraded", "stale_reference"})
VALID_COVERAGE_STATES = frozenset({"complete", "degraded", "failed"})
VALID_CANDIDATE_KINDS = frozenset({"deal", "absolute_low_non_deal"})
CANONICAL_LATEST_PATH = "data/ftr-feed/latest.json"


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
    text = str(version or "")
    match = re.fullmatch(r"(\d+)\.(\d+)", text)
    if not match:
        raise FTRHandoffError("schema_version must use MAJOR.MINOR")
    return int(match.group(1))


def _record_for_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    exact = _mapping(item.get("exact"))
    if exact:
        return exact
    return _mapping(item.get("discovery"))


def _record_iata(record: Mapping[str, Any], field: str) -> str:
    identity = _mapping(record.get(field))
    value = str(identity.get("iata") or "")
    if len(value) != 3 or value != value.upper() or not value.isalpha():
        raise FTRHandoffError(f"record {field} must contain exact uppercase IATA")
    return value


def _outbound_date(record: Mapping[str, Any]) -> str:
    legs = record.get("legs")
    if not isinstance(legs, Sequence) or isinstance(legs, (str, bytes)) or not legs:
        raise FTRHandoffError("airfare variant requires at least one normalized leg")
    first = _mapping(legs[0])
    value = str(first.get("date") or "")
    if not value:
        raise FTRHandoffError("airfare variant missing outbound date")
    return value


def _return_date(record: Mapping[str, Any]) -> str:
    reproducible = _mapping(record.get("reproducible_search"))
    requested = reproducible.get("return_date")
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
    # Absolute-low non-Deals must be explicitly selected upstream.  Do not
    # reinterpret generic Signals or exact-revalidated rows as price-floor truth.
    if str(item.get("state") or "") == "ftr_absolute_low_non_deal":
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
    return_gateway = _taiwan_return_gateway(record, outbound_gateway=outbound_gateway)
    outbound_date = _outbound_date(record)
    return_date = _return_date(record)
    observed_at = _aware_timestamp(record.get("observed_at"), field="variant.observed_at")
    origin_identity = _mapping(record.get("origin"))
    destination_identity = _mapping(record.get("destination"))
    record_id = str(record.get("record_id") or "")
    if not record_id:
        raise FTRHandoffError("eligible airfare item missing record_id")

    evidence_url = record.get("evidence_url") or record.get("booking_url")
    airlines = record.get("airlines")
    if not isinstance(airlines, Sequence) or isinstance(airlines, (str, bytes)):
        airlines = ()
    legs = record.get("legs")
    normalized_legs = list(legs) if isinstance(legs, Sequence) and not isinstance(legs, (str, bytes)) else []
    return {
        "variant_id": record_id,
        "candidate_kind": kind,
        "source_type": "cfr_deal" if kind == "deal" else "cfr_absolute_low_non_deal",
        "observed_at": observed_at,
        "complete_airfare_twd": fare,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "taiwan_origin_gateway": outbound_gateway,
        "taiwan_return_gateway": return_gateway,
        "destination_route_shape": {
            "arrival_airport": arrival_airport,
            "departure_airport": departure_airport,
        },
        "destination": {
            "city": destination_identity.get("city"),
            "country": destination_identity.get("country"),
        },
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
            "url": evidence_url,
        },
        "taiwan_origin_city": origin_identity.get("city"),
    }


def _coverage_summary(run_result: Mapping[str, Any]) -> Mapping[str, Any]:
    coverage = _mapping(run_result.get("coverage"))
    provider_health = _mapping(run_result.get("provider_health") or coverage.get("provider_health"))
    health_status = str(provider_health.get("status") or "")
    if health_status not in {"healthy", "degraded", "provider_failed"}:
        raise FTRHandoffError("producer run is missing recognized provider_health status")

    origins: dict[str, Mapping[str, Any]] = {}
    for origin, raw in _mapping(coverage.get("origins")).items():
        details = _mapping(raw)
        raw_status = str(details.get("status") or "")
        status = "failed" if raw_status == "failed" else "succeeded"
        origins[str(origin)] = {
            "status": status,
            "source_status": raw_status or None,
            "returned_flight_deals": int(details.get("returned_flight_deals") or 0),
            "explore_seeds": int(details.get("explore_seeds") or 0),
        }

    market_status = "failed" if health_status == "provider_failed" else "succeeded"
    markets: dict[str, Mapping[str, Any]] = {}
    for market, raw in _mapping(coverage.get("markets")).items():
        details = _mapping(raw)
        markets[str(market)] = {
            "status": market_status,
            "metrics": {str(key): int(value or 0) for key, value in details.items()},
        }

    provider_status = "failed" if health_status == "provider_failed" else "succeeded"
    return {
        "providers": {
            "gflights": {
                "status": provider_status,
                "health_status": health_status,
                "reasons": list(provider_health.get("reasons") or []),
            }
        },
        "origins": origins,
        "markets": markets,
        "provider_health": dict(provider_health),
        "provider_failures": list(run_result.get("provider_failures") or []),
        "semantics": "execution_and_coverage_evidence_not_candidate_count",
    }


def build_snapshot(
    run_result: Mapping[str, Any],
    *,
    producer_commit_sha: str,
    mode: str | None = None,
    generated_at: str | None = None,
) -> Mapping[str, Any]:
    """Build one normalized, consumable FTR airfare-feed snapshot.

    Healthy and truthfully degraded terminal runs are consumable.  A broad
    provider failure is not published as a fresh snapshot because FTR must not
    mistake coverage collapse for a healthy empty market.
    """

    run_id = str(run_result.get("radar_run_id") or run_result.get("run_id") or "")
    if not run_id:
        raise FTRHandoffError("run_result missing run_id")
    observed_at = _aware_timestamp(run_result.get("run_at") or run_result.get("observed_at"), field="observed_at")
    resolved_mode = str(mode or run_result.get("execution_mode") or "canonical_daily")
    if resolved_mode not in VALID_MODES:
        raise FTRHandoffError(f"unsupported handoff mode: {resolved_mode}")
    if not str(producer_commit_sha or "").strip():
        raise FTRHandoffError("producer_commit_sha is required")
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    generated = _aware_timestamp(generated, field="generated_at")

    coverage = _coverage_summary(run_result)
    health = str(_mapping(coverage.get("provider_health")).get("status") or "")
    if health == "provider_failed":
        raise FTRHandoffError("provider_failed run is not consumable as a fresh FTR snapshot")
    coverage_state = "complete" if health == "healthy" else "degraded"
    freshness_state = "fresh" if health == "healthy" else "degraded"

    items: list[Mapping[str, Any]] = []
    for raw in [*(run_result.get("deals") or []), *(run_result.get("signals") or [])]:
        if not isinstance(raw, Mapping):
            raise FTRHandoffError("run_result deals/signals must contain JSON objects")
        variant = _variant_from_item(raw)
        if variant is not None:
            items.append(variant)

    # A variant may be surfaced through more than one upstream evidence path.
    # Prefer formal Deal semantics over absolute-low when the exact record id is
    # identical, then prefer the lower fare only as a deterministic tie-break.
    by_variant: dict[str, Mapping[str, Any]] = {}
    for variant in items:
        variant_id = str(variant["variant_id"])
        incumbent = by_variant.get(variant_id)
        if incumbent is None:
            by_variant[variant_id] = variant
            continue
        incumbent_rank = 0 if incumbent["candidate_kind"] == "deal" else 1
        variant_rank = 0 if variant["candidate_kind"] == "deal" else 1
        if (variant_rank, int(variant["complete_airfare_twd"])) < (
            incumbent_rank,
            int(incumbent["complete_airfare_twd"]),
        ):
            by_variant[variant_id] = variant

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for variant in by_variant.values():
        shape = _mapping(variant["destination_route_shape"])
        key = (str(shape["arrival_airport"]), str(shape["departure_airport"]))
        grouped.setdefault(key, []).append(variant)

    opportunities: list[Mapping[str, Any]] = []
    for (arrival, departure), variants in sorted(grouped.items()):
        variants.sort(
            key=lambda value: (
                int(value["complete_airfare_twd"]),
                str(value["outbound_date"]),
                str(value["return_date"]),
                str(value["variant_id"]),
            )
        )
        opportunities.append(
            {
                "opportunity_id": f"air-{arrival.lower()}-{departure.lower()}",
                "destination_route_shape": {
                    "arrival_airport": arrival,
                    "departure_airport": departure,
                },
                "variants": variants,
            }
        )

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
            "variants": sum(len(item["variants"]) for item in opportunities),
            "deals": sum(
                1
                for item in opportunities
                for variant in item["variants"]
                if variant["candidate_kind"] == "deal"
            ),
            "absolute_low_non_deals": sum(
                1
                for item in opportunities
                for variant in item["variants"]
                if variant["candidate_kind"] == "absolute_low_non_deal"
            ),
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
    if str(snapshot.get("coverage_state") or "") not in VALID_COVERAGE_STATES:
        raise FTRHandoffError("snapshot coverage_state is unsupported")
    if str(snapshot.get("freshness_state") or "") not in VALID_FRESHNESS_STATES:
        raise FTRHandoffError("snapshot freshness_state is unsupported")
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
    run_id = _safe_component(str(snapshot.get("run_id") or ""))
    return f"data/ftr-feed/{observed:%Y/%m/%d}/{run_id}.json"


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def snapshot_checksum(snapshot: Mapping[str, Any]) -> str:
    validate_snapshot(snapshot)
    return hashlib.sha256(_json_bytes(snapshot)).hexdigest()


def manifest_for_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_snapshot(snapshot)
    mode = str(snapshot["mode"])
    snapshot_path = snapshot_repository_path(snapshot)
    manifest = {
        "schema_version": str(snapshot["schema_version"]),
        "run_id": str(snapshot["run_id"]),
        "mode": mode,
        "observed_at": str(snapshot["observed_at"]),
        "generated_at": str(snapshot["generated_at"]),
        "producer_commit_sha": str(snapshot["producer_commit_sha"]),
        "coverage_state": str(snapshot["coverage_state"]),
        "freshness_state": str(snapshot["freshness_state"]),
        "terminal_state": str(snapshot["terminal_state"]),
        "snapshot_path": snapshot_path,
        "snapshot_sha256": snapshot_checksum(snapshot),
    }
    return manifest


def manifest_repository_path(snapshot: Mapping[str, Any]) -> str:
    mode = str(snapshot.get("mode") or "")
    if mode in {"canonical_daily", "same_day_recovery"}:
        return CANONICAL_LATEST_PATH
    if mode == "scoped_search":
        return f"data/ftr-feed/scoped/{_safe_component(str(snapshot.get('run_id') or ''))}.json"
    raise FTRHandoffError(f"unsupported handoff mode: {mode}")


def stage_snapshot(*, history_dir: Path, snapshot: Mapping[str, Any]) -> Mapping[str, str]:
    """Write immutable snapshot first and its manifest last.

    Canonical/recovery modes update ``latest.json``.  Scoped Search writes a
    run-specific manifest and can never advance canonical latest.  Existing
    immutable snapshots may only be reused when their bytes are identical.
    """

    validate_snapshot(snapshot)
    snapshot_rel = snapshot_repository_path(snapshot)
    manifest_rel = manifest_repository_path(snapshot)
    snapshot_path = history_dir / snapshot_rel
    manifest_path = history_dir / manifest_rel
    snapshot_data = _json_bytes(snapshot)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.exists():
        if snapshot_path.read_bytes() != snapshot_data:
            raise FileExistsError(f"immutable FTR snapshot already exists with different content: {snapshot_path}")
    else:
        temporary = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
        temporary.write_bytes(snapshot_data)
        temporary.replace(snapshot_path)

    # Manifest is intentionally generated only after the immutable payload has
    # been durably written and validated.
    manifest = manifest_for_snapshot(snapshot)
    manifest_data = _json_bytes(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_manifest.write_bytes(manifest_data)
    temporary_manifest.replace(manifest_path)
    return {
        "snapshot_path": snapshot_rel,
        "manifest_path": manifest_rel,
        "snapshot_sha256": str(manifest["snapshot_sha256"]),
    }


def load_manifest_snapshot(
    *,
    history_dir: Path,
    manifest_path: str = CANONICAL_LATEST_PATH,
    supported_major: int = SUPPORTED_SCHEMA_MAJOR,
) -> Mapping[str, Any]:
    """Fail-closed consumer helper used by contract tests and future FTR code."""

    manifest_file = history_dir / manifest_path
    if not manifest_file.exists():
        raise FTRHandoffError(f"handoff manifest missing: {manifest_path}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise FTRHandoffError("handoff manifest must be a JSON object")
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
    checksum = hashlib.sha256(payload).hexdigest()
    if checksum != str(manifest.get("snapshot_sha256") or ""):
        raise FTRHandoffError("handoff snapshot checksum mismatch")
    snapshot = json.loads(payload.decode("utf-8"))
    if not isinstance(snapshot, Mapping):
        raise FTRHandoffError("handoff snapshot must be a JSON object")
    validate_snapshot(snapshot, supported_major=supported_major)
    if str(snapshot.get("run_id")) != str(manifest.get("run_id")):
        raise FTRHandoffError("handoff manifest/snapshot run_id mismatch")
    return snapshot
