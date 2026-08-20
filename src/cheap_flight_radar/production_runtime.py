"""Canonical one-shot production execution wrapper.

The core :mod:`production_radar` runtime intentionally spends exact-search work
only on a bounded competitive shortlist. This wrapper records destination-free
Flight Deals acquisition so every qualified anomaly candidate remains durable
evidence even when it was not selected for exact completion in this run.

It also owns narrowly operational provider hardening for the canonical daily
execution path. Multi-city searches use a client created at process start that
is separate from the high-volume discovery/exact/flexible client. Both clients
retain the same explicit CheapFlightRadar User-Agent, direct connection
(``proxy=None``), locale, and currency through :class:`GFlightsAdapter`; this is
surface budget isolation, not UA/proxy/session rotation, retry, or rate-limit
resetting. Provider failures still fail closed through the underlying adapter.

RP-06 additionally retains already-acquired multi-city exact results as a
*dedicated* exact non-Deal candidate input. This never scans the Signal journal:
route variants are admitted only from the adapter result that the canonical
runtime actually acquired, and the existing RP-02 eligibility/ordering selector
is reused as the admission truth. The same capture records bounded return-gateway
attempt/not-attempted evidence without adding provider calls.

The wrapper does not alter Deal qualification, Deal ordering, or provider-call
latency semantics. ChatGPT remains the scheduler/orchestrator; this module is
only short-lived execution.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .airfare import AirfareRecord, ProviderResult, is_international_asia_oceania
from .production_radar import (
    ProductionRadar,
    RadarItem,
    RadarRunResult,
    _dedupe_discovery,
    _discovery_sort_key,
    _item_json,
    _load_prior_history,
    _minimum_away_satisfied,
    _to_observation,
    load_policy,
    write_run_artifacts as _write_run_artifacts,
)
from .providers.gflights import GFlightsAdapter
from .ftr_absolute_low import apply_absolute_low_selection, select_absolute_low_non_deals


STICKY_RATE_LIMIT_MARKERS = (
    "HTTP 429 Too Many Requests",
    "all further requests on this client are blocked",
)


def _is_sticky_rate_limit(result: ProviderResult) -> bool:
    error = result.error or ""
    return bool(
        result.provider == "gflights"
        and result.coverage_state == "failed"
        and all(marker in error for marker in STICKY_RATE_LIMIT_MARKERS)
    )


class ProductionExecutionAdapter:
    """Reserve fixed provider lanes and stop known-local sticky 429 follow-ons.

    gflights marks an ``ApiClient`` sticky after an HTTP 429 and locally refuses
    every later call on that same client. Once Radar observes that exact sticky
    error, later logical work on the same fixed lane is failed closed without
    invoking the client again. The first sticky failure remains a real technical
    provider call/failure; later work is circuit-suppressed evidence. No retry,
    reset, new identity, proxy, or client rotation is performed.
    """

    def __init__(self, *, primary: Any, multi_city: Any) -> None:
        self._primary = primary
        self._multi_city = multi_city
        self._circuit_reason: dict[str, str | None] = {"primary": None, "multi_city": None}

    def _suppressed(self, *, lane: str, surface: str) -> ProviderResult:
        trigger = self._circuit_reason[lane] or "sticky provider rate-limit state"
        return ProviderResult(
            "gflights",
            surface,
            "failed",
            error=(
                f"circuit_open: {lane} gflights client is already locally blocked after sticky HTTP 429; "
                f"no provider request sent; trigger={trigger}"
            ),
            request_sent=False,
        )

    async def _call(self, *, lane: str, surface: str, method: Any, kwargs: Mapping[str, Any]) -> ProviderResult:
        if self._circuit_reason[lane] is not None:
            return self._suppressed(lane=lane, surface=surface)
        result = await method(**kwargs)
        if _is_sticky_rate_limit(result):
            self._circuit_reason[lane] = result.error or "sticky HTTP 429"
        return result

    async def flight_deals(self, **kwargs: Any) -> ProviderResult:
        return await self._call(lane="primary", surface="flight_deals", method=self._primary.flight_deals, kwargs=kwargs)

    async def explore(self, **kwargs: Any) -> ProviderResult:
        return await self._call(lane="primary", surface="explore", method=self._primary.explore, kwargs=kwargs)

    async def exact(self, **kwargs: Any) -> ProviderResult:
        return await self._call(lane="primary", surface="exact", method=self._primary.exact, kwargs=kwargs)

    async def cheapest_dates(self, **kwargs: Any) -> ProviderResult:
        return await self._call(lane="primary", surface="cheapest_dates", method=self._primary.cheapest_dates, kwargs=kwargs)

    async def open_jaw(self, **kwargs: Any) -> ProviderResult:
        return await self._call(lane="multi_city", surface="open_jaw", method=self._multi_city.open_jaw, kwargs=kwargs)


class RecordingFlightDealsAdapter:
    """Transparent adapter decorator retaining already-fetched provider rows.

    Flight Deals rows support the pre-existing pending-qualified-candidate
    behavior. RP-06 also records the exact multi-city request/result pairs that
    :class:`ProductionRadar` already performs. Merely recording those results
    adds no provider request and does not change sticky-429 lane behavior.
    """

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.flight_deal_records: list[AirfareRecord] = []
        self.open_jaw_results: list[
            tuple[tuple[tuple[str, str, str], ...], ProviderResult]
        ] = []

    async def flight_deals(self, **kwargs: Any) -> ProviderResult:
        result = await self._delegate.flight_deals(**kwargs)
        if result.coverage_state != "failed":
            self.flight_deal_records.extend(result.records)
        return result

    async def open_jaw(self, **kwargs: Any) -> ProviderResult:
        legs = tuple(tuple(str(value) for value in leg) for leg in (kwargs.get("legs") or ()))
        result = await self._delegate.open_jaw(**kwargs)
        self.open_jaw_results.append((legs, result))
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def retain_pending_qualified_candidates(
    result: RadarRunResult,
    *,
    flight_deal_records: Sequence[AirfareRecord],
    policy: Mapping[str, Any],
) -> RadarRunResult:
    """Retain qualified-but-not-exact-completed Flight Deals as Signals.

    A record is pending only when it meets the same discovery qualification
    predicates as the core runtime and is not already represented by a Deal or
    another Signal. Pending records remain Signals because exact current fare
    completion has not been performed.
    """

    run_date = datetime.fromisoformat(result.run_at).date()
    horizon_end = run_date + timedelta(days=int(policy["search"]["horizon_days"]))
    retained_ids = {
        item.discovery.record_id
        for item in (*result.deals, *result.signals)
    }
    pending: list[RadarItem] = []
    for record in _dedupe_discovery(flight_deal_records):
        if record.record_id in retained_ids:
            continue
        if not is_international_asia_oceania(record.destination.country):
            continue
        if record.outbound_date:
            try:
                departure = date.fromisoformat(record.outbound_date)
            except ValueError:
                continue
            if departure < run_date or departure > horizon_end:
                continue
        qualified = (
            record.evidence_class == "qualified_round_trip_deal"
            and record.complete_airfare
            and bool(record.current_price_twd)
            and bool(record.typical_price_twd)
            and bool(record.discount_percent)
            and _minimum_away_satisfied(record)
        )
        if not qualified:
            continue
        pending.append(
            RadarItem(
                classification="Signal",
                state="qualified_anomaly_candidate_pending_exact",
                discovery=record,
                exact=None,
                anomaly_source=record.anomaly_authority,
                anomaly_strength_percent=record.discount_percent,
                reason=(
                    "qualified Flight Deals anomaly retained; exact completion "
                    "was not selected under the current run compute budget"
                ),
            )
        )
        retained_ids.add(record.record_id)

    pending.sort(key=lambda item: _discovery_sort_key(item.discovery))
    return RadarRunResult(
        radar_run_id=result.radar_run_id,
        run_at=result.run_at,
        deals=result.deals,
        signals=tuple([*result.signals, *pending]),
        coverage=result.coverage,
        provider_failures=result.provider_failures,
        exact_non_deal_candidates=result.exact_non_deal_candidates,
        ftr_absolute_low_non_deals=result.ftr_absolute_low_non_deals,
    )


def _route_variant_kind(legs: Sequence[Sequence[str]]) -> str | None:
    """Classify the two RP-06 route variants from the exact requested legs."""

    if len(legs) < 2 or len(legs[0]) != 3 or len(legs[-1]) != 3:
        return None
    first = legs[0]
    last = legs[-1]
    if last[0] == first[1] and last[1] != first[0]:
        return "mixed_taiwan_return"
    if last[0] != first[1]:
        return "destination_open_jaw"
    return None


def _variant_discovery(
    result: RadarRunResult,
    *,
    origin: str,
    destination: str,
    outbound_date: str,
) -> AirfareRecord | None:
    """Resolve provenance from retained CFR truth, never from a city guess."""

    candidates = [
        item.discovery
        for item in (*result.deals, *result.signals, *result.exact_non_deal_candidates)
        if item.discovery.origin.iata == origin
        and item.discovery.destination.iata == destination
    ]
    exact_date = [record for record in candidates if record.outbound_date == outbound_date]
    if exact_date:
        return min(exact_date, key=lambda record: record.record_id)
    if candidates:
        return min(candidates, key=lambda record: record.record_id)
    return None


def _rp02_admits_candidate(
    result: RadarRunResult,
    *,
    candidate: RadarItem,
    policy: Mapping[str, Any],
) -> bool:
    """Reuse RP-02 eligibility without copying a second truth engine.

    The one-candidate probe is *not* the final bounded selection. It only asks
    RP-02 whether this exact candidate satisfies its existing current,
    reproducible, complete-fare, >24h, provenance, main-island and Deal-duplicate
    gates. Final price-first/max-count selection still runs once over the merged
    dedicated pool after RP-06 convergence.
    """

    probe = RadarRunResult(
        radar_run_id=result.radar_run_id,
        run_at=result.run_at,
        deals=result.deals,
        signals=(),
        coverage=result.coverage,
        provider_failures=result.provider_failures,
        exact_non_deal_candidates=(candidate,),
        ftr_absolute_low_non_deals=(),
    )
    return bool(select_absolute_low_non_deals(probe, policy=policy))


def converge_rp06_route_variants(
    result: RadarRunResult,
    *,
    open_jaw_results: Sequence[
        tuple[tuple[tuple[str, str, str], ...], ProviderResult]
    ],
    policy: Mapping[str, Any],
) -> RadarRunResult:
    """Admit already-acquired exact route variants and persist gateway truth.

    Authority is the captured provider request/result pair, not generic Signal
    membership or naming. RP-02 remains the only non-Deal FTR admission engine.
    This function performs zero provider calls.
    """

    return_policy = (policy.get("search") or {}).get("return_to_taiwan") or {}
    primary_gateways = tuple(str(value) for value in return_policy.get("primary_return_search_airports") or ())
    completion_scope = str(return_policy.get("completion_scope") or "")
    route_candidates: list[RadarItem] = []
    gateway_rows: list[dict[str, Any]] = []
    mixed_seed_keys: set[str] = set()

    for requested_legs, provider_result in open_jaw_results:
        kind = _route_variant_kind(requested_legs)
        if kind is None or len(requested_legs) < 2:
            continue
        first = requested_legs[0]
        last = requested_legs[-1]

        if kind == "mixed_taiwan_return":
            seed_key = f"{first[0]}:{first[1]}:{first[2]}:{last[2]}"
            if seed_key in mixed_seed_keys:
                raise RuntimeError(
                    "RP-06 mixed-return provider-call budget drifted above one attempt per expansion seed"
                )
            mixed_seed_keys.add(seed_key)
            selected_gateway = last[1]
            request_sent = bool(provider_result.request_sent)
            attempted = [selected_gateway] if request_sent else []
            gateway_rows.append(
                {
                    "seed_key": seed_key,
                    "taiwan_origin_gateway": first[0],
                    "destination_arrival_airport": first[1],
                    "selected_mixed_return_gateway": selected_gateway,
                    "selected_gateway_source": (
                        "configured_primary"
                        if selected_gateway in primary_gateways
                        else "opportunistic_non_primary_request"
                    ),
                    "attempted_mixed_return_gateways": attempted,
                    "configured_primary_gateways_not_attempted": [
                        gateway for gateway in primary_gateways if gateway not in attempted
                    ],
                    "provider_request_sent": request_sent,
                    "result_coverage_state": provider_result.coverage_state,
                    "live_route_evidence_observed": bool(
                        provider_result.records
                        and any(
                            record.surface == "open_jaw"
                            and record.verification_state == "revalidated"
                            and record.complete_airfare
                            and record.legs
                            and record.legs[-1].destination == selected_gateway
                            for record in provider_result.records
                        )
                    ),
                }
            )

        if provider_result.coverage_state == "failed":
            continue
        for exact in provider_result.records:
            discovery = _variant_discovery(
                result,
                origin=first[0],
                destination=first[1],
                outbound_date=first[2],
            )
            if discovery is None:
                continue
            observation_id = _to_observation(result.radar_run_id, exact).observation_id
            candidate = RadarItem(
                classification="Signal",
                state="exact_revalidated_candidate",
                discovery=discovery,
                exact=exact,
                anomaly_source=None,
                anomaly_strength_percent=None,
                reason=(
                    "RP-06 already-acquired exact route variant retained in the dedicated exact non-Deal pool; "
                    "no anomaly authority invented and final admission remains RP-02"
                ),
                observation_id=observation_id,
            )
            if _rp02_admits_candidate(result, candidate=candidate, policy=policy):
                route_candidates.append(candidate)

    existing_keys = {
        (
            item.exact.record_id,
            tuple((leg.origin, leg.destination, leg.date) for leg in item.exact.legs),
        )
        for item in result.exact_non_deal_candidates
        if item.exact is not None
    }
    merged_pool = list(result.exact_non_deal_candidates)
    for candidate in route_candidates:
        assert candidate.exact is not None
        key = (
            candidate.exact.record_id,
            tuple((leg.origin, leg.destination, leg.date) for leg in candidate.exact.legs),
        )
        if key not in existing_keys:
            merged_pool.append(candidate)
            existing_keys.add(key)

    coverage = dict(result.coverage)
    coverage["return_gateway_expansion"] = {
        "completion_scope": completion_scope,
        "configured_primary_return_gateways": list(primary_gateways),
        "primary_pool_semantics": "bounded_search_pool_not_exhaustive_claim",
        "search_exhaustive": False,
        "mixed_return_provider_attempts_per_expansion_seed_max": 1,
        "provider_call_budget_changed_by_rp06": False,
        "opportunistic_non_primary": {
            "allowed": bool(return_policy.get("allow_opportunistic_main_island_airports", False)),
            "requires_live_route_evidence": bool(return_policy.get("opportunistic_airport_requires_live_route_evidence", True)),
            "proactively_exhaustive": False,
            "no_live_evidence_semantics": "not_searched_not_eligible_as_opportunistic_extra",
        },
        "seed_attempts": gateway_rows,
    }

    return RadarRunResult(
        radar_run_id=result.radar_run_id,
        run_at=result.run_at,
        deals=result.deals,
        signals=result.signals,
        coverage=coverage,
        provider_failures=result.provider_failures,
        exact_non_deal_candidates=tuple(merged_pool),
        ftr_absolute_low_non_deals=result.ftr_absolute_low_non_deals,
    )


async def run_once(
    *,
    policy: Mapping[str, Any],
    adapter: Any,
    prior_history: Sequence[Any] = (),
    run_at: datetime | None = None,
) -> RadarRunResult:
    recorder = RecordingFlightDealsAdapter(adapter)
    base_result = await ProductionRadar(
        policy=policy,
        adapter=recorder,
        prior_history=prior_history,
    ).run(run_at=run_at)
    retained = retain_pending_qualified_candidates(
        base_result,
        flight_deal_records=recorder.flight_deal_records,
        policy=policy,
    )
    converged = converge_rp06_route_variants(
        retained,
        open_jaw_results=recorder.open_jaw_results,
        policy=policy,
    )
    return apply_absolute_low_selection(converged, policy=policy)


def write_run_artifacts(
    result: RadarRunResult,
    *,
    policy: Mapping[str, Any],
    output_dir: Path,
) -> Mapping[str, str]:
    """Write canonical artifacts, including full Signal rows in run-result."""

    paths = _write_run_artifacts(result, policy=policy, output_dir=output_dir)
    result_path = Path(paths["run_result"])
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["signals"] = [_item_json(item) for item in result.signals]
    payload["signal_states"] = {
        state: sum(1 for item in result.signals if item.state == state)
        for state in sorted({item.state for item in result.signals})
    }
    payload["ftr_absolute_low_non_deal_count"] = len(result.ftr_absolute_low_non_deals)
    payload["ftr_absolute_low_non_deals"] = [
        _item_json(item) for item in result.ftr_absolute_low_non_deals
    ]
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths


def _replace_run_identity(value: Any, old_id: str, new_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(old_id, new_id).replace(old_id.lower(), new_id.lower())
    if isinstance(value, list):
        return [_replace_run_identity(item, old_id, new_id) for item in value]
    if isinstance(value, dict):
        return {key: _replace_run_identity(item, old_id, new_id) for key, item in value.items()}
    return value


def retag_run_artifacts(
    *,
    output_dir: Path,
    paths: Mapping[str, str],
    run_id_prefix: str,
    execution_mode: str,
) -> Mapping[str, str]:
    """Retag one completed acquisition without re-querying providers.

    Canonical automatic runs retain the ``production-radar-*`` identity. Explicit
    operator reacquisitions are retagged after acquisition so their immutable
    snapshot can coexist on the same local day without entering the canonical
    daily snapshot namespace.
    """

    prefix = run_id_prefix.strip("-.")
    if not prefix or re.search(r"[^A-Za-z0-9._-]", prefix):
        raise ValueError("run_id_prefix must contain only path-safe characters")
    if prefix == "production-radar":
        return paths

    result_path = Path(paths["run_result"])
    manifest_path = Path(paths["publication_manifest"])
    snapshot_path = Path(paths["history_snapshot"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    old_id = str(result.get("radar_run_id") or "")
    if not old_id.startswith("production-radar-"):
        raise ValueError("retag source must be a production-radar run")
    suffix = old_id.removeprefix("production-radar-")
    new_id = f"{prefix}-{suffix}"
    old_safe = re.sub(r"[^A-Za-z0-9._-]+", "-", old_id).strip("-.")
    new_safe = re.sub(r"[^A-Za-z0-9._-]+", "-", new_id).strip("-.")

    transformed_result = _replace_run_identity(result, old_id, new_id)
    transformed_manifest = _replace_run_identity(manifest, old_id, new_id)
    transformed_snapshot = _replace_run_identity(snapshot, old_id, new_id)
    history_rel = Path(str(manifest["history_snapshot_path"]))
    if history_rel.name != f"{old_safe}.json":
        raise ValueError("history snapshot path does not match source run identity")
    new_history_rel = history_rel.with_name(f"{new_safe}.json").as_posix()
    transformed_manifest["history_snapshot_path"] = new_history_rel
    transformed_manifest["execution_mode"] = execution_mode
    transformed_result["execution_mode"] = execution_mode

    new_snapshot_path = snapshot_path.with_name(f"{new_safe}.json")
    new_manifest_path = manifest_path.with_name(f"{new_id}.json")
    new_snapshot_path.write_text(
        json.dumps(transformed_snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    new_manifest_path.write_text(
        json.dumps(transformed_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    result_path.write_text(
        json.dumps(transformed_result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if new_snapshot_path != snapshot_path:
        snapshot_path.unlink()
    if new_manifest_path != manifest_path:
        manifest_path.unlink()
    return {
        "history_snapshot": new_snapshot_path.as_posix(),
        "publication_manifest": new_manifest_path.as_posix(),
        "run_result": result_path.as_posix(),
    }


async def _async_main(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy))
    prior_history = _load_prior_history(Path(args.history_dir) if args.history_dir else None)
    adapter = ProductionExecutionAdapter(
        primary=GFlightsAdapter(),
        multi_city=GFlightsAdapter(),
    )
    result = await run_once(
        policy=policy,
        adapter=adapter,
        prior_history=prior_history,
    )
    paths = write_run_artifacts(result, policy=policy, output_dir=Path(args.output_dir))
    if args.run_id_prefix != "production-radar":
        paths = retag_run_artifacts(
            output_dir=Path(args.output_dir),
            paths=paths,
            run_id_prefix=args.run_id_prefix,
            execution_mode=args.execution_mode,
        )
    summary = json.loads(Path(paths["run_result"]).read_text(encoding="utf-8"))
    print(json.dumps({
        "radar_run_id": summary["radar_run_id"],
        "run_at": summary["run_at"],
        "deal_count": summary["deal_count"],
        "signal_count": summary["signal_count"],
        "signal_states": summary["signal_states"],
        "coverage": summary["coverage"],
        "provider_health": summary["provider_health"],
        "provider_failures": summary["provider_failures"],
        "paths": paths,
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one canonical short-lived Cheap Flight Radar acquisition"
    )
    parser.add_argument("--policy", default="flight-radar.yaml")
    parser.add_argument(
        "--history-dir",
        default=None,
        help="Optional checked-out history/price-observations ref",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--run-id-prefix",
        default="production-radar",
        help="Path-safe run identity prefix; operator workflows use a request-specific prefix",
    )
    parser.add_argument(
        "--execution-mode",
        default="canonical_daily",
        help="Provenance label embedded in non-canonical retagged run artifacts",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
