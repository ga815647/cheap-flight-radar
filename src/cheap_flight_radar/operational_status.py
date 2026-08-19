"""Deterministic operational-health and notification semantics.

Deal count is a market/result signal, never a provider-health signal. Provider
health is derived from actual execution/coverage evidence so a broad substrate
collapse cannot masquerade as a normal zero-Deal run.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

HEALTH_STATES = ("healthy", "degraded", "provider_failed")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _execution(coverage: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(coverage.get("execution"))


def _explicit_empty_schema(execution: Mapping[str, Any]) -> bool:
    """Whether failure counters have the corrected technical-only semantics.

    Historical manifests before the operational-correctness fix counted a
    complete-but-empty provider response as ``failures``. The corrected schema
    exposes ``empty`` (and ``exact_empty``) separately. Legacy Pages rebuilds
    therefore must not reinterpret old ``failures`` counters as technical
    failures; their raw origin coverage remains usable for health derivation.
    """

    return any(
        isinstance(details, Mapping) and ("empty" in details or "exact_empty" in details)
        for details in execution.values()
    )


def technical_failure_count(coverage: Mapping[str, Any]) -> int:
    execution = _execution(coverage)
    if not _explicit_empty_schema(execution):
        return 0
    total = 0
    for details in execution.values():
        if not isinstance(details, Mapping):
            continue
        total += _as_int(details.get("failures"))
        total += _as_int(details.get("exact_failures"))
    return total


def _origin_gaps(coverage: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    origins = _mapping(coverage.get("origins"))
    failed: list[str] = []
    degraded: list[str] = []
    for origin, raw in origins.items():
        details = _mapping(raw)
        status = str(details.get("status") or "")
        flight_deals = _as_int(details.get("returned_flight_deals"))
        explore = _as_int(details.get("explore_seeds"))
        if status == "failed" or (flight_deals == 0 and explore == 0):
            failed.append(str(origin))
        elif status == "degraded" or flight_deals == 0:
            degraded.append(str(origin))
    return failed, degraded


def _discovery_collapse(coverage: Mapping[str, Any]) -> bool:
    origins = _mapping(coverage.get("origins"))
    failed_origins, _ = _origin_gaps(coverage)
    if origins and len(failed_origins) == len(origins):
        return True

    execution = _execution(coverage)
    flight_deals = _mapping(execution.get("flight_deals"))
    explore = _mapping(execution.get("explore"))
    attempts = _as_int(flight_deals.get("attempts")) + _as_int(explore.get("attempts"))
    records = _as_int(flight_deals.get("records")) + _as_int(explore.get("records"))
    return bool(coverage.get("all_origins_attempted") and attempts > 0 and records == 0)


def derive_provider_health(
    coverage: Mapping[str, Any],
    provider_failures: Sequence[Mapping[str, Any]] = (),
) -> Mapping[str, Any]:
    failed_origins, degraded_origins = _origin_gaps(coverage)
    technical_failures = technical_failure_count(coverage)
    collapse = _discovery_collapse(coverage)
    reasons: list[str] = []

    if collapse:
        status = "provider_failed"
        reasons.append("required Flight Deals/Explore discovery coverage collapsed across all configured origins")
    else:
        if failed_origins:
            reasons.append("no usable Flight Deals or Explore coverage for: " + ", ".join(sorted(failed_origins)))
        if degraded_origins:
            reasons.append("primary Flight Deals coverage missing but fallback coverage survived for: " + ", ".join(sorted(degraded_origins)))
        if technical_failures:
            reasons.append(f"{technical_failures} technical provider execution failure(s) recorded")
        if provider_failures:
            reasons.append(f"{len(provider_failures)} provider/operational failure evidence item(s) recorded")
        status = "degraded" if reasons else "healthy"

    return {
        "status": status,
        "technical_failure_count": technical_failures,
        "coverage_collapse": collapse,
        "failed_origins": sorted(failed_origins),
        "degraded_origins": sorted(degraded_origins),
        "reasons": reasons,
        "deal_count_is_health_signal": False,
    }


def reconcile_provider_failures(
    coverage: Mapping[str, Any],
    provider_failures: Sequence[Mapping[str, str]],
) -> tuple[Mapping[str, str], ...]:
    """Keep explicit failures and add fail-safe evidence for impossible gaps."""

    failures: list[Mapping[str, str]] = list(provider_failures)
    technical_failures = technical_failure_count(coverage)
    if technical_failures and not failures:
        failures.append({
            "origin": "run",
            "surface": "execution_counters",
            "kind": "counter_reconciliation",
            "error": f"execution counters recorded {technical_failures} technical provider failure(s)",
        })
    if _discovery_collapse(coverage) and not any(item.get("kind") == "coverage_collapse" for item in failures):
        failures.append({
            "origin": "all",
            "surface": "discovery_coverage",
            "kind": "coverage_collapse",
            "error": "Flight Deals and Explore returned zero usable discovery records across all configured origins",
        })
    return tuple(failures)


def decide_notification(
    *,
    meaningful_deal_count: int,
    provider_health_status: str,
    operational_failure: bool = False,
) -> Mapping[str, Any]:
    """Pure decision contract used by tests and ChatGPT orchestration docs."""

    if provider_health_status not in HEALTH_STATES:
        raise ValueError(f"unknown provider health status: {provider_health_status}")
    if operational_failure:
        return {"notify": True, "reason": "operational_failure"}
    if provider_health_status in {"degraded", "provider_failed"}:
        return {"notify": True, "reason": "provider_or_coverage_degradation"}
    if meaningful_deal_count > 0:
        return {"notify": True, "reason": "meaningful_new_deal"}
    return {"notify": False, "reason": "routine_no_meaningful_change"}
