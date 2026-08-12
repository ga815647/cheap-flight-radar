"""Source routing driven by the repository SSOT."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import OriginSweepRequest, ProviderPlanEntry, ProviderState, RoutePlan, SearchRequest


KNOWN_ROUTE_WEB_STAGES = {"outbound_probe", "return_expansion", "round_trip_benchmark"}


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


def build_source_plan(
    request: SearchRequest | OriginSweepRequest,
    policy: Mapping[str, Any],
    provider_states: Mapping[str, ProviderState],
) -> RoutePlan:
    """Return the ordered provider plan without silently degrading query fidelity.

    ``OriginSweepRequest`` is the only valid Stage A discovery request. A legacy
    ``SearchRequest(search_stage="broad_discovery")`` already contains a caller-
    selected destination and therefore cannot establish outbound-first coverage.
    """

    routing = policy.get("source_routing") or {}
    selected = routing.get("selected_routes") or {}

    if isinstance(request, OriginSweepRequest):
        stage_config = _shared_origin_wide_config(request.profiles, selected)
        if not stage_config:
            return _unavailable(
                "no shared production provider selected for origin-wide discovery",
                state="unconfigured",
            )
        return _plan_stage(
            stage_config=stage_config,
            provider_states=provider_states,
            reason=(
                f"selected by SSOT for destination-free {request.origin} origin sweep"
            ),
            include_fallback=True,
        )

    if request.search_stage == "broad_discovery":
        return _unavailable(
            "known-destination SearchRequest cannot establish outbound-first coverage; "
            "use destination-free OriginSweepRequest",
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
        provider_states=provider_states,
        reason=(
            f"selected by SSOT for shared known-route {request.search_stage} via ChatGPT Web"
            if request.search_stage in KNOWN_ROUTE_WEB_STAGES
            else f"selected by SSOT for {request.profile}/{request.search_stage}"
        ),
    )


def _plan_stage(
    *,
    stage_config: Mapping[str, Any],
    provider_states: Mapping[str, ProviderState],
    reason: str,
    include_fallback: bool = False,
) -> RoutePlan:
    provider = stage_config.get("primary_provider")
    if not provider:
        return _unavailable("selected route has no primary provider", state="unconfigured")

    if stage_config.get("execution_mode") == "chatgpt_web_direct":
        entries = [ProviderPlanEntry(provider=provider, reason=reason)]
        fallback = stage_config.get("fallback_provider") if include_fallback else None
        if fallback and fallback != provider:
            entries.append(
                ProviderPlanEntry(
                    provider=str(fallback),
                    reason="best-effort fallback after primary origin-wide surface failure",
                )
            )
        return RoutePlan(entries=tuple(entries), coverage_state="planned")

    state = provider_states.get(provider)
    if state is None or not state.credential_available:
        return _unavailable(
            f"{provider} credential unavailable; no silent fallback selected"
        )
    if not state.healthy:
        return _unavailable(
            f"{provider} unhealthy; no silent lower-fidelity fallback selected"
        )

    return RoutePlan(
        entries=(ProviderPlanEntry(provider=provider, reason=reason),),
        coverage_state="planned",
    )
