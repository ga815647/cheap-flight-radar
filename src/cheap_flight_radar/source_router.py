"""Source routing driven by the repository SSOT."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ProviderPlanEntry, ProviderState, RoutePlan, SearchRequest


def _unavailable(reason: str, state: str = "unavailable") -> RoutePlan:
    return RoutePlan(entries=(), coverage_state=state, fallback_reason=reason)


def _selected_stage_config(
    request: SearchRequest,
    selected: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    profile_config = selected.get(request.profile) or {}
    stage_config = profile_config.get(request.search_stage)
    if stage_config:
        return stage_config

    if request.search_stage != "broad_discovery":
        return None

    shared = (selected.get("shared") or {}).get("broad_discovery")
    if not shared:
        return None

    profiles = shared.get("applies_to_profiles") or []
    if profiles and request.profile not in profiles:
        return None
    return shared


def build_source_plan(
    request: SearchRequest,
    policy: Mapping[str, Any],
    provider_states: Mapping[str, ProviderState],
) -> RoutePlan:
    """Return the ordered provider plan without silently degrading query fidelity."""

    routing = policy.get("source_routing") or {}
    selected = routing.get("selected_routes") or {}
    stage_config = _selected_stage_config(request, selected)
    if not stage_config:
        return _unavailable(
            "no production provider selected for this market/stage",
            state="unconfigured",
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

    provider = stage_config.get("primary_provider")
    if not provider:
        return _unavailable("selected route has no primary provider", state="unconfigured")

    if stage_config.get("execution_mode") == "chatgpt_web_direct":
        return RoutePlan(
            entries=(
                ProviderPlanEntry(
                    provider=provider,
                    reason=(
                        f"selected by SSOT for shared {request.search_stage} via "
                        "ChatGPT Web"
                    ),
                ),
            ),
            coverage_state="planned",
        )

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
        entries=(
            ProviderPlanEntry(
                provider=provider,
                reason=f"selected by SSOT for {request.profile}/{request.search_stage}",
            ),
        ),
        coverage_state="planned",
    )
