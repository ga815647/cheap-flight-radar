from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, addition: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if addition.strip() in text:
        raise SystemExit(f"addition already present in {path}")
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"expected one marker in {path}, found {count}: {marker[:100]!r}")
    target.write_text(text.replace(marker, marker + addition, 1), encoding="utf-8")


operational_status = r'''"""Deterministic operational-health and notification semantics.

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
'''
Path("src/cheap_flight_radar/operational_status.py").write_text(operational_status, encoding="utf-8")

replace_once(
    "PRODUCT_INTENT.md",
    "- An operator-requested same-day reacquisition must be explicitly identified and append immutable evidence. It must not weaken duplicate protection for the routine daily trigger, silently retry a failed automatic run, or overwrite the canonical daily observation.\n",
    "- An operator-requested same-day reacquisition must be explicitly identified and append immutable evidence. It must not weaken duplicate protection for the routine daily trigger, silently retry a failed automatic run, or overwrite the canonical daily observation.\n"
    "- Provider/acquisition health is determined from technical execution and coverage evidence, **never from Deal count**. A partially degraded run may still publish already exact-revalidated valid Deals, but a broad provider/coverage collapse must be visibly distinct from a healthy zero-Deal market result.\n"
    "- Scheduled notification decisions happen only after the workflow reaches a terminal state and ChatGPT reads the final immutable run evidence. Meaningful new Deals and operational/provider/coverage failures notify; a healthy routine run with no meaningful change may stay silent. A UI notification toggle is only a delivery mechanism, not product policy.\n",
)

replace_once(
    "flight-radar.yaml",
    "publication:\n",
    "operational_health:\n"
    "  provider_acquisition:\n"
    "    states:\n"
    "    - healthy\n"
    "    - degraded\n"
    "    - provider_failed\n"
    "    derive_from:\n"
    "    - technical_execution_counters\n"
    "    - surface_failure_evidence\n"
    "    - required_origin_discovery_coverage\n"
    "    deal_count_is_health_signal: false\n"
    "    complete_empty_provider_response_is_not_technical_failure: true\n"
    "    all_required_discovery_surfaces_zero_usable_records: provider_failed\n"
    "    partial_degradation_preserves_exact_revalidated_deals: true\n"
    "    provider_failed_must_not_render_as_normal_zero_deal: true\n"
    "publication:\n",
)
replace_once(
    "flight-radar.yaml",
    "    publication_recovery: immutable_run_evidence_without_reacquisition\n    github_actions_role: disposable_static_build_gate_and_deploy_backend\n",
    "    publication_recovery: immutable_run_evidence_without_reacquisition\n"
    "    completion_evidence:\n"
    "      control_request_submission_is_not_completion: true\n"
    "      wait_for_workflow_terminal_state: true\n"
    "      read_final_immutable_run_evidence_before_notification_decision: true\n"
    "      required_final_evidence:\n"
    "      - pre_acquisition_claim\n"
    "      - immutable_price_history_snapshot\n"
    "      - immutable_run_result\n"
    "      - immutable_recovery_manifest\n"
    "      - active_publication_manifest\n"
    "      terminal_or_final_evidence_unavailable_action: notify_operational_failure\n"
    "    github_actions_role: disposable_static_build_gate_and_deploy_backend\n",
)
replace_once(
    "flight-radar.yaml",
    "notifications:\n  enabled_when_automation_exists: true\n  notify_on:\n  - new_top_ranked_deal\n  - meaningful_new_route_low\n  - unusually_cheap_long_haul\n  suppress_routine_no_change_runs: true\n",
    "notifications:\n"
    "  enabled_when_automation_exists: true\n"
    "  ui_notification_toggle_is_delivery_mechanism_not_product_policy: true\n"
    "  decision_requires_final_immutable_evidence: true\n"
    "  notify_on:\n"
    "  - meaningful_new_deal\n"
    "  - operational_workflow_failure\n"
    "  - provider_or_coverage_degradation\n"
    "  suppress_routine_no_change_runs: true\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "from .models import OriginSweepRequest, SearchRequest\nfrom .source_router import build_source_plan\n",
    "from .models import OriginSweepRequest, SearchRequest\nfrom .operational_status import derive_provider_health, reconcile_provider_failures\nfrom .source_router import build_source_plan\n",
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''def _execution_template() -> dict[str, dict[str, int]]:\n    return {\n        surface: {"attempts": 0, "records": 0, "successes": 0, "failures": 0, "unsupported": 0}\n        for surface in EXECUTION_SURFACES\n    }\n\n\ndef _count_provider_result(execution: dict[str, dict[str, int]], surface: str, result: ProviderResult) -> None:\n    counter = execution[surface]\n    counter["records"] += len(result.records)\n    if result.coverage_state == "complete" and result.records:\n        counter["successes"] += 1\n    elif result.coverage_state == "unsupported":\n        counter["unsupported"] += 1\n    else:\n        counter["failures"] += 1\n''',
    '''def _execution_template() -> dict[str, dict[str, int]]:\n    return {\n        surface: {"attempts": 0, "records": 0, "successes": 0, "empty": 0, "failures": 0, "unsupported": 0}\n        for surface in EXECUTION_SURFACES\n    }\n\n\ndef _count_provider_result(execution: dict[str, dict[str, int]], surface: str, result: ProviderResult) -> None:\n    counter = execution[surface]\n    counter["records"] += len(result.records)\n    if result.coverage_state == "complete" and result.records:\n        counter["successes"] += 1\n    elif result.coverage_state == "failed":\n        counter["failures"] += 1\n    elif result.coverage_state == "unsupported":\n        counter["unsupported"] += 1\n    else:\n        counter["empty"] += 1\n''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''            origin_coverage[origin] = {\n                "status": "failed" if not origin_records and origin_errors else "attempted",\n                "returned_flight_deals": len(origin_records),\n                "asia_oceania_records": len(region_records),\n                "qualified_deals": len(qualified_records),\n                "explore_seeds": explore_count,\n                "errors": origin_errors,\n            }\n''',
    '''            if not origin_records and explore_count == 0:\n                origin_status = "failed"\n            elif not origin_records:\n                origin_status = "degraded"\n            else:\n                origin_status = "attempted"\n            origin_coverage[origin] = {\n                "status": origin_status,\n                "returned_flight_deals": len(origin_records),\n                "asia_oceania_records": len(region_records),\n                "qualified_deals": len(qualified_records),\n                "explore_seeds": explore_count,\n                "errors": origin_errors,\n            }\n''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''            if exact_result.coverage_state != "complete" or not exact_result.records:\n                message = exact_result.error or exact_result.coverage_state\n                provider_failures.append({\n                    "origin": discovery.origin.iata,\n                    "surface": "exact",\n                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}",\n                    "error": message,\n                })\n                exact_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, f"exact revalidation failed closed: {message}"))\n                continue\n''',
    '''            if exact_result.coverage_state != "complete" or not exact_result.records:\n                message = exact_result.error or exact_result.coverage_state\n                if exact_result.coverage_state == "failed":\n                    provider_failures.append({\n                        "origin": discovery.origin.iata,\n                        "surface": "exact",\n                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}",\n                        "error": message,\n                    })\n                exact_signals.append(RadarItem("Signal", "weak_seed", discovery, None, discovery.anomaly_authority, discovery.discount_percent, f"exact revalidation failed closed: {message}"))\n                continue\n''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''            execution["flexible_dates"].setdefault("exact_attempts", 0)\n            execution["flexible_dates"].setdefault("exact_successes", 0)\n            execution["flexible_dates"].setdefault("exact_failures", 0)\n''',
    '''            execution["flexible_dates"].setdefault("exact_attempts", 0)\n            execution["flexible_dates"].setdefault("exact_successes", 0)\n            execution["flexible_dates"].setdefault("exact_empty", 0)\n            execution["flexible_dates"].setdefault("exact_failures", 0)\n''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''            else:\n                execution["flexible_dates"]["exact_failures"] += 1\n                message = exact_result.error or exact_result.coverage_state\n                provider_failures.append({\n                    "origin": discovery.origin.iata,\n                    "surface": "flexible_exact",\n                    "route": f"{discovery.origin.iata}-{discovery.destination.iata}",\n                    "error": message,\n                })\n\n        best_same_destination:''',
    '''            else:\n                message = exact_result.error or exact_result.coverage_state\n                if exact_result.coverage_state == "failed":\n                    execution["flexible_dates"]["exact_failures"] += 1\n                    provider_failures.append({\n                        "origin": discovery.origin.iata,\n                        "surface": "flexible_exact",\n                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}",\n                        "error": message,\n                    })\n                else:\n                    execution["flexible_dates"]["exact_empty"] += 1\n\n        best_same_destination:''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''                else:\n                    provider_failures.append({\n                        "origin": discovery.origin.iata,\n                        "surface": "mixed_taiwan_return",\n                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}-{alternate_return}",\n                        "error": mixed_result.error or mixed_result.coverage_state,\n                    })\n\n            exit_seed''',
    '''                elif mixed_result.coverage_state == "failed":\n                    provider_failures.append({\n                        "origin": discovery.origin.iata,\n                        "surface": "mixed_taiwan_return",\n                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}-{alternate_return}",\n                        "error": mixed_result.error or mixed_result.coverage_state,\n                    })\n\n            exit_seed''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''                else:\n                    provider_failures.append({\n                        "origin": discovery.origin.iata,\n                        "surface": "open_jaw",\n                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}/{exit_seed.destination.iata}-{discovery.origin.iata}",\n                        "error": open_jaw_result.error or open_jaw_result.coverage_state,\n                    })\n\n        signal_by_key''',
    '''                elif open_jaw_result.coverage_state == "failed":\n                    provider_failures.append({\n                        "origin": discovery.origin.iata,\n                        "surface": "open_jaw",\n                        "route": f"{discovery.origin.iata}-{discovery.destination.iata}/{exit_seed.destination.iata}-{discovery.origin.iata}",\n                        "error": open_jaw_result.error or open_jaw_result.coverage_state,\n                    })\n\n        signal_by_key''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''            "fixed_watch_is_deal_coverage_authority": False,\n        }\n        return RadarRunResult(run_id, local_run_at.isoformat(), tuple(deals), tuple(signal_by_key.values()), coverage, tuple(provider_failures))\n''',
    '''            "fixed_watch_is_deal_coverage_authority": False,\n        }\n        provider_failures = list(reconcile_provider_failures(coverage, provider_failures))\n        coverage["provider_health"] = derive_provider_health(coverage, provider_failures)\n        return RadarRunResult(run_id, local_run_at.isoformat(), tuple(deals), tuple(signal_by_key.values()), coverage, tuple(provider_failures))\n''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''        "coverage": result.coverage,\n        "provider_failures": list(result.provider_failures),\n        "anomaly_truth_priority": list(policy["source_routing"]["anomaly_truth_priority"]),\n''',
    '''        "coverage": result.coverage,\n        "provider_health": result.coverage.get("provider_health", {}),\n        "provider_failures": list(result.provider_failures),\n        "anomaly_truth_priority": list(policy["source_routing"]["anomaly_truth_priority"]),\n''',
)
replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''                "deals": [_item_json(item) for item in result.deals],\n                "coverage": result.coverage,\n                "provider_failures": list(result.provider_failures),\n''',
    '''                "deals": [_item_json(item) for item in result.deals],\n                "coverage": result.coverage,\n                "provider_health": result.coverage.get("provider_health", {}),\n                "provider_failures": list(result.provider_failures),\n''',
)

replace_once(
    "src/cheap_flight_radar/production_runtime.py",
    '''        "coverage": summary["coverage"],\n        "provider_failures": summary["provider_failures"],\n''',
    '''        "coverage": summary["coverage"],\n        "provider_health": summary["provider_health"],\n        "provider_failures": summary["provider_failures"],\n''',
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    "from .price_history import FareHistorySnapshot, FareObservation, compare_with_history, snapshot_from_json\n",
    "from .operational_status import derive_provider_health\nfrom .price_history import FareHistorySnapshot, FareObservation, compare_with_history, snapshot_from_json\n",
)
publication_health_helpers = r'''

def _provider_health(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    health = manifest.get("provider_health")
    if isinstance(health, Mapping) and health.get("status"):
        return health
    coverage = manifest.get("coverage")
    failures = manifest.get("provider_failures")
    failure_rows = (
        tuple(item for item in failures if isinstance(item, Mapping))
        if isinstance(failures, Sequence) and not isinstance(failures, (str, bytes))
        else ()
    )
    return derive_provider_health(coverage if isinstance(coverage, Mapping) else {}, failure_rows)


def _health_warning_html(manifest: Mapping[str, Any]) -> str:
    health = _provider_health(manifest)
    status = str(health.get("status") or "unknown")
    if status == "healthy":
        return ""
    reasons = health.get("reasons")
    if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)):
        reason_text = "; ".join(str(item) for item in reasons if item)
    else:
        reason_text = "provider/coverage health is not fully healthy"
    if status == "provider_failed":
        title = "Provider acquisition failed"
        body = "This run does not represent a normal zero-Deal market result. Required provider/coverage evidence collapsed; inspect execution evidence before interpreting absence of Deals."
    else:
        title = "Coverage degraded"
        body = "Some provider or origin coverage was degraded. Already exact-revalidated Deals remain valid and are retained, but missing coverage must not be interpreted as market absence."
    return (
        '<section class="details-card"><p class="eyebrow">Operational warning</p>'
        f'<h2>{escape(title)}</h2><p class="sparse-note">{escape(body)}</p>'
        f'<p class="sparse-note">{escape(reason_text)}</p></section>'
    )
'''
replace_once(
    "src/cheap_flight_radar/production_publication.py",
    "\ndef _coverage_html(manifest: Mapping[str, Any]) -> str:\n",
    publication_health_helpers + "\n\ndef _coverage_html(manifest: Mapping[str, Any]) -> str:\n",
)
replace_once(
    "src/cheap_flight_radar/production_publication.py",
    '''                f"{details.get('attempts', 0)} attempts · {details.get('successes', 0)} success · "\n                f"{details.get('records', 0)} records · {details.get('failures', 0)} failed · {details.get('unsupported', 0)} unsupported"\n''',
    '''                f"{details.get('attempts', 0)} attempts · {details.get('successes', 0)} success · "\n                f"{details.get('records', 0)} records · {details.get('empty', 0)} empty · "\n                f"{details.get('failures', 0)} technical failed · {details.get('unsupported', 0)} unsupported"\n''',
)
replace_once(
    "src/cheap_flight_radar/production_publication.py",
    '''    deal_cards = "".join(\n        _deal_card(item, by_id=by_id, all_history=all_history, policy=policy)\n        for item in deals if isinstance(item, Mapping)\n    ) or '<p class="empty">No qualified current Deal survived exact revalidation in this run.</p>'\n''',
    '''    health = _provider_health(manifest)\n    empty_deals = (\n        '<p class="empty">Deal result unavailable as a normal market-zero interpretation because provider acquisition failed.</p>'\n        if health.get("status") == "provider_failed"\n        else '<p class="empty">No qualified current Deal survived exact revalidation in this run.</p>'\n    )\n    deal_cards = "".join(\n        _deal_card(item, by_id=by_id, all_history=all_history, policy=policy)\n        for item in deals if isinstance(item, Mapping)\n    ) or empty_deals\n''',
)
replace_once(
    "src/cheap_flight_radar/production_publication.py",
    '''        '<span class="chip">Flight Deals → exact / flexible / multi-city</span></div></header>'\n        '<div class="section-heading"><div><h2>Deals</h2><p>Qualified external anomaly truth + current exact complete airfare.</p></div></div>'\n''',
    '''        '<span class="chip">Flight Deals → exact / flexible / multi-city</span></div></header>'\n        + _health_warning_html(manifest)\n        + '<div class="section-heading"><div><h2>Deals</h2><p>Qualified external anomaly truth + current exact complete airfare.</p></div></div>'\n''',
)

append_once(
    "docs/production-operationalization-2026-08-14.md",
    "This path is for explicit refreshed evidence, diagnosis, or provider-health comparison. It must never be scheduled automatically and does not relax the routine canonical one-attempt guard.",
    "\n\n## Provider acquisition health and notification completion\n\n"
    "A workflow finishing with a syntactically valid snapshot/manifest is not enough to call the market result healthy. Every new run derives `provider_health.status` from technical execution counters, provider/surface failure evidence, and required-origin discovery coverage. The states are `healthy`, `degraded`, and `provider_failed`; Deal count is never an input to that classification. Complete-but-empty provider responses are recorded separately from technical failures. A whole-run Flight Deals + Explore discovery collapse is `provider_failed`, while partial origin/provider degradation is `degraded`. Already exact-revalidated Deals are retained under degradation rather than discarded.\n\n"
    "Publication must make degraded/provider-failed state visible. In particular, `provider_failed` with zero Deals must not render as the same normal-empty message as a healthy zero-Deal run. Historical schema-v2 manifests can be reclassified at render time from their stored coverage evidence, so the 2026-08-17 all-zero discovery collapse is not silently preserved as a normal market-zero presentation.\n\n"
    "For the ChatGPT daily scheduler, writing `requests/daily.json` is only the control request, not completion. The scheduler must identify the triggered canonical workflow, wait until it reaches a terminal state, then read the final immutable claim/snapshot/run-result/recovery manifest and active publication evidence before deciding whether to notify. If terminal state or final evidence cannot be obtained, that is an operational completion-verification failure and must not be reported as routine no-change. Meaningful new Deals and operational/provider/coverage failures notify; a healthy run with no meaningful change may stay silent. The ChatGPT UI notification switch is a delivery setting, not a substitute for these product semantics.\n",
)
append_once(
    "docs/publication.md",
    "- **Signal** — useful evidence that has not satisfied the full Deal contract, including weak seeds, qualified anomalies pending exact completion, exact candidates without usable anomaly truth, stale anomalies, and fail-closed provider outcomes.",
    "\n- **Provider health** — independent of Deal count. Schema-v2 run-result/manifest evidence carries `provider_health`; Pages shows a visible warning for `degraded` or `provider_failed`. Partial degradation does not remove already exact-revalidated Deals, while a provider-failed zero-Deal run must never look like a healthy zero-Deal run.\n",
)
append_once(
    "docs/price-history.md",
    "Each run creates one new snapshot file and never rewrites an older run snapshot. Baselines, percentiles, and lows are derived from snapshots when needed; derived values are not a second authoritative state store.",
    "\n\nCanonical automatic runs and explicit operator reacquisitions are both real immutable observations, but they remain in separate run/claim namespaces: one `production-radar-*` canonical observation per routine local day, and request-id-scoped `operator-radar-{request_id}-*` observations for explicitly requested same-day refreshes. A duplicate operator request id is recovery/no-op only and never creates another observation.",
)

automation_doc = r'''# Daily Flight Radar — ChatGPT automation prompt

Use this as the canonical prompt contract for the ChatGPT automation named `Daily Flight Radar`.

```text
Run the Cheap Flight Radar routine canonical daily orchestration. First read the latest formal project sources in order: Chat Dev, Cheap Flight Radar｜Chat Dev, then the latest `main` in `ga815647/cheap-flight-radar`, `AGENTS.md`, `PRODUCT_INTENT.md`, complete `flight-radar.yaml`, and `docs/production-operationalization-2026-08-14.md`; latest formal SSOT overrides memory. Resolve the current Asia/Taipei local date.

This automation owns only the routine automatic canonical request. Do not directly run airfare acquisition and do not add GitHub cron, providers, daemons, queues, state services, proxy/UA rotation, reset_rate_limit, retry storms, or a 30-second provider timeout. Use the dedicated GitHub control branch `ops/radar-request`: get the current `main` SHA, refresh/reset that dedicated control branch to current `main` as needed, then create the day's `requests/daily.json` with exactly `schema_version: 1`, `mode: canonical_daily`, and `requested_date` as current Asia/Taipei `YYYY-MM-DD`.

Before writing a routine request, inspect the existing `history/price-observations` canonical daily claim/snapshot state when practical. The automatic canonical path is limited to one claimed acquisition attempt per local day: if today's canonical claim/snapshot already exists, do not cause another automatic canonical live acquisition and use only the repository's documented recovery/no-op path. This automatic duplicate guard is not a product-level ban on same-day reacquisition: an explicit user/operator request with a new unique request id may use the separate `operator_reacquisition` path, but this scheduled automation must never create such an operator request on its own.

Submitting the control request is not completion. Identify the canonical workflow run triggered by the request commit and only decide user-facing status after that workflow reaches a terminal state. Then read back the final immutable evidence on `history/price-observations`: the pre-acquisition canonical claim, immutable price-history snapshot, immutable run-evidence `run-result.json`, recovery `publication-manifest.json`, and the active publication manifest/Pages dispatch evidence required by the SSOT. If the workflow is terminal-failed, or final immutable completion evidence cannot be obtained during this automation execution, treat that as an operational completion-verification failure; do not report a normal no-change result based only on successful request submission.

Use final immutable `provider_health` when present, and otherwise derive health fail-safely from the final coverage/execution evidence; never use Deal count to distinguish healthy market results from degraded/provider-failed acquisition. Preserve any already exact-revalidated valid Deals in a degraded run. Compare the final Deal set with the previous relevant canonical publication/evidence to decide whether there are meaningful new Deals. Notify/report when there are meaningful new Deals or any operational/provider/coverage failure. A healthy routine run with no meaningful change may stay silent/concise. Do not treat the ChatGPT UI notification toggle as product policy.

Do not rerun production soak, Issue #26 search-recall repair, PR #27 publication correctness work, or 429/provider hardening.
```
'''
Path("docs/daily-flight-radar-automation-prompt.md").write_text(automation_doc, encoding="utf-8")

operational_tests = r'''from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from cheap_flight_radar.operational_status import (
    decide_notification,
    derive_provider_health,
    reconcile_provider_failures,
)

ROOT = Path(__file__).resolve().parents[1]


def execution_surface(**overrides):
    base = {"attempts": 0, "records": 0, "successes": 0, "empty": 0, "failures": 0, "unsupported": 0}
    base.update(overrides)
    return base


class OperationalCorrectnessTests(unittest.TestCase):
    def test_provider_counter_failure_forces_health_and_failure_evidence(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                "TPE": {"status": "attempted", "returned_flight_deals": 3, "explore_seeds": 2},
                "TSA": {"status": "attempted", "returned_flight_deals": 3, "explore_seeds": 2},
            },
            "execution": {
                "flight_deals": execution_surface(attempts=2, records=6, successes=1, failures=1),
                "explore": execution_surface(attempts=2, records=4, successes=2),
            },
        }
        failures = reconcile_provider_failures(coverage, ())
        health = derive_provider_health(coverage, failures)
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["technical_failure_count"], 1)
        self.assertTrue(failures)
        self.assertEqual(failures[0]["surface"], "execution_counters")

    def test_complete_empty_is_not_technical_failure_but_broad_discovery_collapse_is_provider_failed(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                origin: {"status": "failed", "returned_flight_deals": 0, "explore_seeds": 0}
                for origin in ("TPE", "TSA", "RMQ", "KHH")
            },
            "execution": {
                "flight_deals": execution_surface(attempts=12, empty=12),
                "explore": execution_surface(attempts=4, empty=4),
            },
        }
        failures = reconcile_provider_failures(coverage, ())
        health = derive_provider_health(coverage, failures)
        self.assertEqual(health["technical_failure_count"], 0)
        self.assertEqual(health["status"], "provider_failed")
        self.assertTrue(any(item.get("kind") == "coverage_collapse" for item in failures))

    def test_legacy_failure_counters_do_not_reclassify_healthy_coverage(self):
        coverage = {
            "all_origins_attempted": True,
            "origins": {
                origin: {"status": "attempted", "returned_flight_deals": 30, "explore_seeds": 20}
                for origin in ("TPE", "TSA", "RMQ", "KHH")
            },
            "execution": {
                "flight_deals": {"attempts": 12, "records": 330, "successes": 11, "failures": 1, "unsupported": 0},
                "explore": {"attempts": 4, "records": 283, "successes": 3, "failures": 1, "unsupported": 0},
            },
        }
        self.assertEqual(derive_provider_health(coverage, ())["status"], "healthy")

    def test_notification_decision_deal_failure_and_routine_no_change(self):
        self.assertEqual(
            decide_notification(meaningful_deal_count=1, provider_health_status="healthy"),
            {"notify": True, "reason": "meaningful_new_deal"},
        )
        self.assertEqual(
            decide_notification(meaningful_deal_count=0, provider_health_status="provider_failed"),
            {"notify": True, "reason": "provider_or_coverage_degradation"},
        )
        self.assertEqual(
            decide_notification(meaningful_deal_count=0, provider_health_status="healthy"),
            {"notify": False, "reason": "routine_no_meaningful_change"},
        )
        self.assertEqual(
            decide_notification(meaningful_deal_count=0, provider_health_status="healthy", operational_failure=True),
            {"notify": True, "reason": "operational_failure"},
        )

    def test_ssot_has_automatic_guard_operator_exception_and_final_evidence_notification_semantics(self):
        policy = yaml.safe_load((ROOT / "flight-radar.yaml").read_text(encoding="utf-8"))
        canonical = policy["price_history"]["persistence"]["canonical_daily_acquisition"]
        operator = policy["price_history"]["persistence"]["operator_requested_reacquisition"]
        completion = policy["publication"]["orchestration"]["completion_evidence"]
        notifications = policy["notifications"]
        self.assertEqual(canonical["max_automatic_attempts_per_local_day"], 1)
        self.assertTrue(operator["enabled"])
        self.assertEqual(operator["duplicate_same_request_id_action"], "recovery_or_noop_never_reacquire")
        self.assertTrue(completion["wait_for_workflow_terminal_state"])
        self.assertTrue(completion["read_final_immutable_run_evidence_before_notification_decision"])
        self.assertTrue(completion["control_request_submission_is_not_completion"])
        self.assertIn("provider_or_coverage_degradation", notifications["notify_on"])
        self.assertTrue(notifications["decision_requires_final_immutable_evidence"])

    def test_tracked_automation_prompt_scopes_same_day_guard_to_automatic_path_and_requires_final_evidence(self):
        text = (ROOT / "docs" / "daily-flight-radar-automation-prompt.md").read_text(encoding="utf-8")
        self.assertIn("automatic canonical path is limited to one claimed acquisition attempt per local day", text)
        self.assertIn("explicit user/operator request with a new unique request id", text)
        self.assertIn("Submitting the control request is not completion", text)
        self.assertIn("only decide user-facing status after that workflow reaches a terminal state", text)
        self.assertIn("final immutable `provider_health`", text)
        self.assertNotIn("same-day prior claim exists without a successful snapshot, fail closed and do not retry providers", text)


if __name__ == "__main__":
    unittest.main()
'''
Path("tests/test_operational_correctness.py").write_text(operational_tests, encoding="utf-8")

replace_once(
    "tests/test_production_radar.py",
    '''    async def test_exact_failure_is_signal_and_never_guessed_into_deal(self):\n        adapter = self.full_adapter()\n        adapter.fail_exact.add(("TPE", "NRT"))\n        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)\n        self.assertNotIn(("TPE", "NRT"), [(item.discovery.origin.iata, item.discovery.destination.iata) for item in result.deals])\n        failed = [item for item in result.signals if item.discovery.destination.iata == "NRT"]\n        self.assertTrue(failed)\n        self.assertTrue(any("failed" in item.reason for item in failed))\n''',
    '''    async def test_exact_failure_is_signal_and_never_guessed_into_deal(self):\n        adapter = self.full_adapter()\n        adapter.fail_exact.add(("TPE", "NRT"))\n        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)\n        self.assertNotIn(("TPE", "NRT"), [(item.discovery.origin.iata, item.discovery.destination.iata) for item in result.deals])\n        failed = [item for item in result.signals if item.discovery.destination.iata == "NRT"]\n        self.assertTrue(failed)\n        self.assertTrue(any("failed" in item.reason for item in failed))\n        self.assertEqual(result.coverage["provider_health"]["status"], "degraded")\n        self.assertTrue(result.provider_failures)\n\n    async def test_partial_discovery_degradation_keeps_exact_revalidated_deal(self):\n        adapter = FakeAdapter({\n            "TPE": [deal("TPE", "NRT", "Japan", 6500, 10000, 35)],\n            "TSA": [], "RMQ": [], "KHH": [],\n        })\n        adapter.explore_records["TSA"] = [weak_explore("TSA", "ICN", "South Korea")]\n        adapter.explore_records["RMQ"] = [weak_explore("RMQ", "KIX", "Japan")]\n        adapter.explore_records["KHH"] = [weak_explore("KHH", "MNL", "Philippines")]\n        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)\n        self.assertEqual(result.coverage["provider_health"]["status"], "degraded")\n        self.assertTrue(any(item.discovery.destination.iata == "NRT" for item in result.deals))\n\n    async def test_all_discovery_surfaces_empty_is_provider_failed_not_normal_zero_deal(self):\n        adapter = FakeAdapter({origin: [] for origin in ("TPE", "TSA", "RMQ", "KHH")})\n        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)\n        self.assertEqual(result.deals, ())\n        self.assertEqual(result.coverage["provider_health"]["status"], "provider_failed")\n        self.assertEqual(result.coverage["execution"]["flight_deals"]["failures"], 0)\n        self.assertEqual(result.coverage["execution"]["flight_deals"]["empty"], 12)\n        self.assertTrue(any(item.get("kind") == "coverage_collapse" for item in result.provider_failures))\n''',
)
replace_once(
    "tests/test_production_radar.py",
    '''        self.assertGreater(manifest["coverage"]["execution"]["flexible_dates"]["attempts"], 0)\n''',
    '''        self.assertGreater(manifest["coverage"]["execution"]["flexible_dates"]["attempts"], 0)\n        self.assertIn(manifest["provider_health"]["status"], {"healthy", "degraded", "provider_failed"})\n''',
)

replace_once(
    "tests/test_production_publication.py",
    '''    def test_wrapper_still_renders_legacy_schema_v1_fixture(self):\n''',
    '''    def test_provider_failed_zero_deal_is_not_rendered_as_normal_market_zero(self):\n        with tempfile.TemporaryDirectory() as tmp:\n            history, manifests, site, run_id = self._write_v2(Path(tmp))\n            manifest_path = manifests / f"{run_id}.json"\n            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n            manifest["deals"] = []\n            manifest["provider_health"] = {\n                "status": "provider_failed",\n                "reasons": ["synthetic full discovery collapse"],\n                "deal_count_is_health_signal": False,\n            }\n            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")\n            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifests, site_dir=site)\n            failed_text = (site / "runs" / run_id / "index.html").read_text(encoding="utf-8")\n            self.assertIn("Provider acquisition failed", failed_text)\n            self.assertIn("does not represent a normal zero-Deal market result", failed_text)\n            self.assertIn("Deal result unavailable as a normal market-zero interpretation", failed_text)\n\n            manifest["provider_health"] = {"status": "healthy", "reasons": [], "deal_count_is_health_signal": False}\n            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")\n            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifests, site_dir=site)\n            healthy_text = (site / "runs" / run_id / "index.html").read_text(encoding="utf-8")\n            self.assertNotIn("Provider acquisition failed", healthy_text)\n            self.assertIn("No qualified current Deal survived exact revalidation", healthy_text)\n\n    def test_legacy_coverage_can_surface_provider_failed_warning_without_rewriting_evidence(self):\n        with tempfile.TemporaryDirectory() as tmp:\n            history, manifests, site, run_id = self._write_v2(Path(tmp))\n            manifest_path = manifests / f"{run_id}.json"\n            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))\n            manifest.pop("provider_health", None)\n            manifest["deals"] = []\n            manifest["coverage"]["origins"] = {\n                origin: {"status": "attempted", "returned_flight_deals": 0, "explore_seeds": 0}\n                for origin in ("TPE", "TSA", "RMQ", "KHH")\n            }\n            manifest["coverage"]["all_origins_attempted"] = True\n            manifest["coverage"]["execution"] = {\n                "flight_deals": {"attempts": 12, "records": 0, "successes": 0, "failures": 12, "unsupported": 0},\n                "explore": {"attempts": 4, "records": 0, "successes": 0, "failures": 4, "unsupported": 0},\n            }\n            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")\n            build_site(policy_path=POLICY, history_dir=history, manifest_dir=manifests, site_dir=site)\n            text = (site / "runs" / run_id / "index.html").read_text(encoding="utf-8")\n            self.assertIn("Provider acquisition failed", text)\n\n    def test_wrapper_still_renders_legacy_schema_v1_fixture(self):\n''',
)

print("operational correctness patch applied")
