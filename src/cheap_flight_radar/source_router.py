"""Source routing driven by the repository SSOT."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import OriginSweepRequest, ProviderPlanEntry, ProviderState, RoutePlan, SearchRequest


KNOWN_ROUTE_WEB_STAGES = {"outbound_probe", "return_expansion", "round_trip_benchmark"}
KEYLESS_EXECUTION_MODES = {"chatgpt_web_direct", "keyless_http_client"}
CANONICAL_BACKEND_EXECUTION_PLANE = "canonical_backend"
INTEGRATED_PROVIDER_STATE = "integrated"


def _unavailable(reason: str, state: str = "unavailable") -> RoutePlan:
    return RoutePlan(entries=(), coverage_state=state, fallback_reason=reason)


def _shared_origin_wide_config(
    profiles: tuple[str, ...],
    selected: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    shared = (selected.get("shared") or {}).get("origin_wide_discovery")
    if not shared:
        return None
    applies = set(shared.get("applies_to_profiles") or ())
    if applies and any(profile not in applies for profile in profiles):
        return None
    return shared


def _shared_known_route_config(
    profiles: tuple[str, ...],
    selected: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    shared = (selected.get("shared") or {}).get("broad_discovery")
    if not shared:
        return None
    applies = set(shared.get("applies_to_profiles") or ())
    if applies and any(profile not in applies for profile in profiles):
        return None
    return shared


def _selected_stage_config(
    request: SearchRequest,
    selected: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    profile_config = selected.get(request.profile) or {}
    stage_config = profile_config.get(request.search_stage)
    if stage_config:
        return stage_config
    if request.search_stage in KNOWN_ROUTE_WEB_STAGES:
        return _shared_known_route_config((request.profile,), selected)
    return None


def _canonical_backend_executable(provider: str, provider_registry: Mapping[str, Any]) -> bool:
    provider_config = provider_registry.get(provider) or {}
    return bool(
        provider_config.get("execution_plane") == CANONICAL_BACKEND_EXECUTION_PLANE
        and provider_config.get("current_integration_state") == INTEGRATED_PROVIDER_STATE
        and provider_config.get("automatic_execution_supported") is True
    )


def build_source_plan(
    request: SearchRequest | OriginSweepRequest,
    policy: Mapping[str, Any],
    provider_states: Mapping[str, ProviderState],
) -> RoutePlan:
    """Return only providers executable by the current caller/execution plane.

    Destination-free discovery is represented by ``OriginSweepRequest``. It may
    yield qualified round-trip Deals directly, or weaker round-trip/one-way/
    destination seeds that are completed only for competitive endpoints.
    A destination-bearing ``SearchRequest(search_stage="broad_discovery")`` is
    therefore not valid evidence of destination-free origin coverage.

    RP-07 makes ``RoutePlan.entries`` an execution contract, not a research
    shortlist. External Web recall surfaces and researched-but-not-integrated
    providers remain in SSOT metadata. The current canonical runtime has no
    fallback dispatcher, so metadata alone can never create a second executable
    plan entry; a future bounded executor package must add that capability first.
    Legacy ``fallback_provider`` drift fails closed instead of reviving a fake
    fallback.
    """

    routing = policy.get("source_routing") or {}
    selected = routing.get("selected_routes") or {}
    provider_registry = routing.get("providers") or {}

    if isinstance(request, OriginSweepRequest):
        stage_config = _shared_origin_wide_config(request.profiles, selected)
        if not stage_config:
            return _unavailable(
                "no shared production provider selected for destination-free discovery",
                state="unconfigured",
            )
        return _plan_stage(
            stage_config=stage_config,
            provider_registry=provider_registry,
            provider_states=provider_states,
            reason=f"selected by SSOT for destination-free {request.origin} origin sweep",
        )

    if request.search_stage == "broad_discovery":
        return _unavailable(
            "known-destination SearchRequest cannot establish destination-free origin coverage; "
            "use OriginSweepRequest",
            state="invalid_contract",
        )

    stage_config = _selected_stage_config(request, selected)
    if not stage_config:
        return _unavailable(
            "no production provider selected for this market/stage",
            state="unconfigured",
        )

    if request.search_stage in {"return_expansion", "round_trip_benchmark"} and not request.return_date:
        return _unavailable(
            f"{request.search_stage} requires an exact return date",
            state="unsupported",
        )

    query_scope = stage_config.get("query_scope")
    if query_scope == "exact_round_trip" and not request.return_date:
        return _unavailable(
            "selected provider route requires an exact return date",
            state="unsupported",
        )

    if request.open_jaw_required and stage_config.get("combined_open_jaw") != "supported":
        return _unavailable(
            "selected provider route cannot represent one combined open-jaw fare",
            state="unsupported",
        )

    return _plan_stage(
        stage_config=stage_config,
        provider_registry=provider_registry,
        provider_states=provider_states,
        reason=(
            f"selected by SSOT for shared known-route {request.search_stage}"
            if request.search_stage in KNOWN_ROUTE_WEB_STAGES
            else f"selected by SSOT for {request.profile}/{request.search_stage}"
        ),
    )


def _plan_stage(
    *,
    stage_config: Mapping[str, Any],
    provider_registry: Mapping[str, Any],
    provider_states: Mapping[str, ProviderState],
    reason: str,
) -> RoutePlan:
    if stage_config.get("fallback_provider"):
        return _unavailable(
            "legacy fallback_provider is not an executable-provider contract; use automatic_executable_fallback",
            state="invalid_contract",
        )

    provider = str(stage_config.get("primary_provider") or "")
    if not provider:
        return _unavailable("selected route has no primary provider", state="unconfigured")
    if not _canonical_backend_executable(provider, provider_registry):
        return _unavailable(
            f"{provider} is not marked as an integrated executable provider for the canonical backend",
            state="unconfigured",
        )

    execution_mode = str(stage_config.get("execution_mode") or "")
    credential_required = bool(stage_config.get("credential_required", execution_mode not in KEYLESS_EXECUTION_MODES))

    if not credential_required and execution_mode in KEYLESS_EXECUTION_MODES:
        entries = [ProviderPlanEntry(provider=provider, reason=reason)]
    else:
        state = provider_states.get(provider)
        if state is None or not state.credential_available:
            return _unavailable(f"{provider} credential unavailable; no silent fallback selected")
        if not state.healthy:
            return _unavailable(f"{provider} unhealthy; no silent lower-fidelity fallback selected")
        entries = [ProviderPlanEntry(provider=provider, reason=reason)]

    fallback = stage_config.get("automatic_executable_fallback")
    if fallback is None:
        return RoutePlan(entries=tuple(entries), coverage_state="planned")

    return _unavailable(
        "automatic_executable_fallback is invalid while the current canonical runtime fallback executor is absent; "
        "provider metadata alone cannot create a second executable RoutePlan entry",
        state="invalid_contract",
    )
