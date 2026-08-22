"""Deterministic operational-health and notification semantics.

Deal count is a market/result signal, never a provider-health signal. Provider
health is derived from actual execution/coverage evidence so a broad substrate
collapse cannot masquerade as a normal zero-Deal run.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

HEALTH_STATES = ("healthy", "degraded", "provider_failed")

# Source-routing identifiers describe provider roles while normalized airfare
# records retain the adapter's runtime provider identity. FTR coverage is keyed
# by the latter, so executable fallback events need one explicit, bounded alias
# normalization before they become per-provider execution truth.
_PROVIDER_EXECUTION_ID_ALIASES = {
    "gflights_google_exact": "gflights",
    "gflights_google_flight_deals": "gflights",
    "gflights_google_explore": "gflights",
    "kiwi_mcp_exact": "kiwi_mcp",
}


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


def _counter_failure_requirements(coverage: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    """Return technical failure evidence that execution counters require.

    The counter surface and failure-evidence surface differ for conventional
    exact completion and flexible-date exact completion, so normalize those
    names here. Legacy execution rows are excluded because their ``failures``
    field also counted complete-but-empty responses.
    """

    execution = _execution(coverage)
    if not _explicit_empty_schema(execution):
        return ()
    required: list[tuple[str, int]] = []
    for counter_surface, raw in execution.items():
        details = _mapping(raw)
        failure_count = _as_int(details.get("failures"))
        if failure_count:
            evidence_surface = "exact" if counter_surface == "conventional_exact" else str(counter_surface)
            required.append((evidence_surface, failure_count))
        exact_failure_count = _as_int(details.get("exact_failures"))
        if exact_failure_count:
            required.append(("flexible_exact", exact_failure_count))
    return tuple(required)


def technical_failure_count(coverage: Mapping[str, Any]) -> int:
    return sum(count for _, count in _counter_failure_requirements(coverage))


def suppressed_request_count(coverage: Mapping[str, Any]) -> int:
    total = 0
    for raw in _execution(coverage).values():
        details = _mapping(raw)
        total += _as_int(details.get("suppressed"))
        total += _as_int(details.get("exact_suppressed"))
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


def _runtime_provider_id(value: Any) -> str:
    provider = str(value or "")
    return _PROVIDER_EXECUTION_ID_ALIASES.get(provider, provider)


def _fallback_provider_execution(coverage: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    """Promote explicit executable-fallback events to provider slice truth.

    The production adapter records one access-redundancy event for every actual
    known-route fallback invocation. Those rows already contain the primary and
    fallback provider identities, terminal states, request-sent truth, surfaces,
    and errors. When both provider identities are unambiguous, this function
    converts only that existing evidence into the top-level provider dimension
    required by the FTR handoff. Unknown/inconsistent evidence intentionally
    returns no synthesized map so the downstream contract continues to fail
    closed instead of inferring provider success.
    """

    lane = _mapping(_mapping(coverage.get("access_redundancy")).get("known_route_exact_flexible"))
    raw_events = lane.get("events")
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, (str, bytes)) or not raw_events:
        return {}
    events = [item for item in raw_events if isinstance(item, Mapping)]
    if len(events) != len(raw_events):
        return {}

    primary_ids = {_runtime_provider_id(item.get("primary_provider")) for item in events}
    fallback_ids = {_runtime_provider_id(item.get("fallback_provider")) for item in events}
    if "" in primary_ids or "" in fallback_ids or len(primary_ids) != 1 or len(fallback_ids) != 1:
        return {}
    primary_provider = next(iter(primary_ids))
    fallback_provider = next(iter(fallback_ids))
    if primary_provider == fallback_provider:
        return {}

    declared_primary = _runtime_provider_id(lane.get("primary"))
    declared_fallback = _runtime_provider_id(lane.get("automatic_executable_fallback"))
    if declared_primary and declared_primary != primary_provider:
        return {}
    if declared_fallback and declared_fallback != fallback_provider:
        return {}

    valid_states = {"complete", "failed"}
    primary_states = [str(item.get("primary_state") or "") for item in events]
    fallback_states = [str(item.get("fallback_state") or "") for item in events]
    if any(state not in valid_states for state in (*primary_states, *fallback_states)):
        return {}

    surfaces = sorted({str(item.get("surface") or "") for item in events if str(item.get("surface") or "")})
    primary_errors = sorted({str(item.get("primary_error")) for item in events if item.get("primary_error")})
    fallback_errors = sorted({str(item.get("fallback_error")) for item in events if item.get("fallback_error")})
    return {
        primary_provider: {
            "status": "failed" if "failed" in primary_states else "succeeded",
            "surfaces": surfaces,
            "reasons": primary_errors,
        },
        fallback_provider: {
            "status": "failed" if "failed" in fallback_states else "succeeded",
            "surfaces": surfaces,
            "reasons": fallback_errors,
        },
    }


def derive_provider_health(
    coverage: Mapping[str, Any],
    provider_failures: Sequence[Mapping[str, Any]] = (),
) -> Mapping[str, Any]:
    # ``attach_access_redundancy_truth`` inserts the executable fallback events
    # immediately before calling this function. Preserve their already-explicit
    # provider execution truth on the same mutable coverage object so FTR does
    # not have to infer provider success from fare records or global health.
    if isinstance(coverage, dict) and "provider_execution" not in coverage:
        provider_execution = _fallback_provider_execution(coverage)
        if provider_execution:
            coverage["provider_execution"] = provider_execution

    failed_origins, degraded_origins = _origin_gaps(coverage)
    technical_failures = technical_failure_count(coverage)
    suppressed_requests = suppressed_request_count(coverage)
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
        status = "healthy"

    if technical_failures:
        reasons.append(f"{technical_failures} technical provider execution failure(s) recorded")
    if suppressed_requests:
        reasons.append(f"{suppressed_requests} provider request(s) circuit-suppressed after sticky rate-limit state")
    if provider_failures:
        reasons.append(f"{len(provider_failures)} provider/operational failure evidence item(s) recorded")
    if not collapse and reasons:
        status = "degraded"

    return {
        "status": status,
        "technical_failure_count": technical_failures,
        "suppressed_request_count": suppressed_requests,
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
    """Keep explicit failures and fill any counter-to-evidence gaps fail-safely."""

    failures: list[Mapping[str, str]] = list(provider_failures)
    for surface, expected_count in _counter_failure_requirements(coverage):
        observed_count = sum(1 for item in failures if str(item.get("surface") or "") == surface)
        missing_count = max(0, expected_count - observed_count)
        if missing_count:
            failures.append({
                "origin": "run",
                "surface": surface,
                "kind": "counter_reconciliation",
                "error": (
                    f"execution counters recorded {expected_count} technical failure(s) on {surface}; "
                    f"{missing_count} lacked explicit per-call failure evidence"
                ),
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
