"""Executable outbound-one-way-first contract.

The module is intentionally source-agnostic. ChatGPT Web may discover seeds from
Expedia or another public surface, but only a destination-free OriginSweepRequest
can establish outbound-first coverage. Round-trip cards remain round-trip evidence;
they are never divided into invented one-way fares.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from .models import (
    CompleteCandidate,
    LiveReturnAirport,
    OriginSweepRequest,
    OutboundProbe,
    OutboundSeed,
    ReturnExpansionRequest,
    ReturnFare,
    RoundTripBenchmark,
    SearchRequest,
    SeriousOutbound,
)


EVIDENCE_KINDS = {"one_way_fare", "round_trip_deal", "destination_only"}
MARKET_ORDER = ("japan", "korea", "china", "world")


@dataclass(frozen=True)
class OutboundFloor:
    origin: str
    market: str
    window: str
    probe: OutboundProbe


@dataclass(frozen=True)
class StageASelection:
    near_term_floors: tuple[OutboundFloor, ...]
    horizon_floors: tuple[OutboundFloor, ...]
    serious_outbounds: tuple[SeriousOutbound, ...]


@dataclass(frozen=True)
class OutboundFirstCoverage:
    covered_origins: tuple[str, ...]
    missing_origins: tuple[str, ...]
    invalid_request_count: int
    can_claim_outbound_first: bool


@dataclass(frozen=True)
class OpportunisticSeedSignal:
    source_id: str
    source_url: str
    observed_at: str
    route_signal: str
    date_signal: str | None
    promo_signal: str | None
    price_text: str | None
    role: str = "opportunistic"
    verification_state: str = "seed_only"
    can_establish_verified_fare: bool = False


def make_outbound_seed(
    request: OriginSweepRequest,
    *,
    seed_id: str,
    destination: str,
    market: str,
    source_id: str,
    source_url: str,
    observed_at: str,
    evidence_kind: str,
    destination_country: str | None = None,
    outbound_date_hint: str | None = None,
    return_date_hint: str | None = None,
    displayed_price_twd: int | None = None,
) -> OutboundSeed:
    """Normalize one destination emitted by a destination-free origin sweep."""

    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError(f"unsupported Stage A evidence kind: {evidence_kind}")
    if market not in MARKET_ORDER:
        raise ValueError(f"unsupported market bucket: {market}")
    if len(destination) != 3 or destination != destination.upper():
        raise ValueError("destination must be an exact uppercase IATA airport")
    if displayed_price_twd is not None and displayed_price_twd <= 0:
        raise ValueError("displayed price must be positive")
    if evidence_kind == "destination_only" and displayed_price_twd is not None:
        raise ValueError("destination-only seeds cannot carry a fare")
    return OutboundSeed(
        seed_id=seed_id,
        profile=(market if market in {"japan", "korea", "china"} else "world"),
        origin=request.origin,
        destination=destination,
        market=market,
        source_id=source_id,
        source_url=source_url,
        observed_at=observed_at,
        evidence_kind=evidence_kind,
        destination_country=destination_country,
        outbound_date_hint=outbound_date_hint,
        return_date_hint=return_date_hint,
        displayed_price_twd=displayed_price_twd,
    )


def seed_one_way_price_twd(seed: OutboundSeed) -> int | None:
    """Return a price only when the source explicitly says it is one-way."""

    if seed.evidence_kind != "one_way_fare":
        return None
    return seed.displayed_price_twd


def outbound_probe_request(seed: OutboundSeed, outbound_date: str) -> SearchRequest:
    """Turn an origin-sweep seed into the first known-destination query."""

    return SearchRequest(
        profile=seed.profile,
        search_stage="outbound_probe",
        origin=seed.origin,
        destination=seed.destination,
        outbound_date=outbound_date,
        return_date=None,
        destination_country=seed.destination_country,
    )


def validate_outbound_probe(seed: OutboundSeed, probe: OutboundProbe) -> None:
    if probe.seed_id != seed.seed_id:
        raise ValueError("outbound probe does not belong to seed")
    if (probe.origin, probe.destination) != (seed.origin, seed.destination):
        raise ValueError("outbound probe route does not match origin-sweep seed")
    if probe.fare_scope != "one_way":
        raise ValueError("outbound probe must be explicit one-way evidence")
    if not probe.exact_airports:
        raise ValueError("outbound probe must resolve exact airports")
    if probe.price_twd <= 0:
        raise ValueError("outbound probe price must be positive")
    _parse_iso_date(probe.outbound_date)


def outbound_first_coverage(
    requests: Iterable[OriginSweepRequest | SearchRequest],
    configured_origins: Sequence[str],
) -> OutboundFirstCoverage:
    """Only destination-free sweep requests can establish outbound-first coverage."""

    covered_list: list[str] = []
    invalid_request_count = 0
    for request in requests:
        if not isinstance(request, OriginSweepRequest):
            invalid_request_count += 1
            continue
        if request.origin not in covered_list:
            covered_list.append(request.origin)
    covered = tuple(covered_list)
    missing = tuple(origin for origin in configured_origins if origin not in covered)
    return OutboundFirstCoverage(
        covered_origins=covered,
        missing_origins=missing,
        invalid_request_count=invalid_request_count,
        can_claim_outbound_first=not missing and invalid_request_count == 0,
    )


def select_stage_a_candidates(
    probes: Iterable[OutboundProbe],
    *,
    run_date: str,
    near_term_days: int = 30,
    horizon_days: int = 120,
    candidate_limit: int = 20,
    market_order: Sequence[str] = MARKET_ORDER,
) -> StageASelection:
    """Keep both live floors while reserving serious-candidate breadth by market."""

    if candidate_limit <= 0:
        raise ValueError("candidate_limit must be positive")
    today = _parse_iso_date(run_date)
    eligible: list[OutboundProbe] = []
    for probe in probes:
        if probe.market not in market_order:
            continue
        if probe.fare_scope != "one_way" or not probe.exact_airports or probe.price_twd <= 0:
            continue
        departure = _parse_iso_date(probe.outbound_date)
        lead = (departure - today).days
        if 0 <= lead <= horizon_days:
            eligible.append(probe)

    near = _floors_by_origin_market(
        [
            p
            for p in eligible
            if (_parse_iso_date(p.outbound_date) - today).days <= near_term_days
        ],
        "near_term_0_30",
    )
    horizon = _floors_by_origin_market(eligible, "horizon_0_120")

    reserved: list[OutboundProbe] = []
    for market in market_order:
        near_market = [
            p
            for p in eligible
            if p.market == market
            and (_parse_iso_date(p.outbound_date) - today).days <= near_term_days
        ]
        horizon_market = [p for p in eligible if p.market == market]
        if near_market:
            _append_unique_probe(reserved, min(near_market, key=_probe_sort_key))
        if horizon_market:
            _append_unique_probe(reserved, min(horizon_market, key=_probe_sort_key))

    floor_pool = [floor.probe for floor in (*near, *horizon)]
    for probe in sorted(floor_pool, key=_probe_sort_key):
        _append_unique_probe(reserved, probe)
        if len(reserved) >= candidate_limit:
            break
    if len(reserved) < candidate_limit:
        for probe in sorted(eligible, key=_probe_sort_key):
            _append_unique_probe(reserved, probe)
            if len(reserved) >= candidate_limit:
                break

    return StageASelection(
        near_term_floors=near,
        horizon_floors=horizon,
        serious_outbounds=tuple(
            SeriousOutbound(
                probe=probe,
                selection_reasons=_selection_reasons(probe, near, horizon),
            )
            for probe in reserved[:candidate_limit]
        ),
    )


def build_return_expansion_requests(
    serious: SeriousOutbound,
    policy: Mapping[str, Any],
    *,
    additional_return_airports: Sequence[LiveReturnAirport] = (),
) -> tuple[ReturnExpansionRequest, ...]:
    """Generate multiple return dates; raw unselected probes cannot enter this stage."""

    outbound = serious.probe
    search = policy.get("search") or {}
    windows = policy.get("return_windows") or []
    bracket = _return_window_for_hours(outbound.one_way_hours, windows)
    if bracket is None:
        raise ValueError("no return-window policy matches outbound travel time")

    offsets = _return_offsets(bracket)
    if len(offsets) < 2:
        raise ValueError("return expansion must search multiple reasonable dates")

    return_policy = search.get("return_to_taiwan") or {}
    primary = tuple(return_policy.get("primary_return_search_airports") or ())
    if not primary:
        raise ValueError("primary Taiwan return airports are not configured")

    airports: list[tuple[str, str | None]] = [(airport, None) for airport in primary]
    for extra in additional_return_airports:
        if not extra.live_route_evidence:
            continue
        if extra.airport not in {airport for airport, _ in airports}:
            airports.append((extra.airport, extra.source_id))

    departure = _parse_iso_date(outbound.outbound_date)
    requests: list[ReturnExpansionRequest] = []
    for nights in offsets:
        return_date = (departure + timedelta(days=nights)).isoformat()
        for airport, source_id in airports:
            requests.append(
                ReturnExpansionRequest(
                    seed_id=outbound.seed_id,
                    profile=outbound.profile,
                    foreign_origin=outbound.destination,
                    taiwan_return_airport=airport,
                    outbound_date=outbound.outbound_date,
                    return_date=return_date,
                    destination_country=outbound.destination_country,
                    live_route_evidence_source_id=source_id,
                )
            )
    return tuple(requests)


def complete_candidate(
    serious: SeriousOutbound,
    return_fare: ReturnFare | None,
    benchmark: RoundTripBenchmark,
) -> CompleteCandidate:
    """Require a conventional RT benchmark and let it complete/win when appropriate."""

    outbound = serious.probe
    if benchmark.origin != outbound.origin or benchmark.destination != outbound.destination:
        raise ValueError("round-trip benchmark must cover the conventional outbound route")
    if benchmark.outbound_date != outbound.outbound_date:
        raise ValueError("round-trip benchmark must use the outbound probe date")
    if benchmark.practicality not in {"better", "comparable", "worse"}:
        raise ValueError("unsupported benchmark practicality state")
    if benchmark.price_twd <= 0:
        raise ValueError("round-trip benchmark price must be positive")

    if return_fare is None:
        if not benchmark.usable:
            raise ValueError("candidate has neither a usable return fare nor usable round trip")
        return CompleteCandidate(
            seed_id=outbound.seed_id,
            origin=outbound.origin,
            destination=outbound.destination,
            outbound_date=outbound.outbound_date,
            return_date=benchmark.return_date,
            taiwan_return_airport=outbound.origin,
            selected_kind="conventional_round_trip",
            selected_total_twd=benchmark.price_twd,
            constructed_total_twd=None,
            round_trip_benchmark_twd=benchmark.price_twd,
            benchmark_source_id=benchmark.source_id,
        )

    if return_fare.seed_id != outbound.seed_id:
        raise ValueError("return fare does not belong to outbound seed")
    if return_fare.foreign_origin != outbound.destination:
        raise ValueError("return fare must leave from the outbound destination")
    if not return_fare.exact_airports or not return_fare.exact_date:
        raise ValueError("return fare must resolve exact airport/date")
    if not return_fare.usable:
        raise ValueError("return fare must be usable")
    if benchmark.return_date != return_fare.return_date:
        raise ValueError("round-trip benchmark must use the candidate return date")

    constructed = outbound.price_twd + return_fare.price_twd
    rt_wins = benchmark.usable and (
        benchmark.practicality == "better"
        or (benchmark.practicality != "worse" and benchmark.price_twd <= constructed)
    )
    selected_kind = "conventional_round_trip" if rt_wins else "constructed_one_way_pair"
    selected_total = benchmark.price_twd if rt_wins else constructed
    return CompleteCandidate(
        seed_id=outbound.seed_id,
        origin=outbound.origin,
        destination=outbound.destination,
        outbound_date=outbound.outbound_date,
        return_date=return_fare.return_date,
        taiwan_return_airport=(outbound.origin if rt_wins else return_fare.taiwan_return_airport),
        selected_kind=selected_kind,
        selected_total_twd=selected_total,
        constructed_total_twd=constructed,
        round_trip_benchmark_twd=benchmark.price_twd,
        benchmark_source_id=benchmark.source_id,
    )


def downstream_expansion_modes(
    candidate: CompleteCandidate,
    *,
    profile: str,
) -> tuple[str, ...]:
    """Open-jaw/mixed return is post-benchmark; China specialist modes stay China-only."""

    modes = ["open_jaw", "mixed_taiwan_return"]
    if profile == "china":
        modes.extend(
            [
                "mainland_high_speed_rail",
                "mainland_domestic_air",
                "kinmen_gateway",
                "matsu_gateway",
            ]
        )
    return tuple(modes)


def public_indexed_social_seed(
    *,
    source_id: str,
    source_url: str,
    observed_at: str,
    route_signal: str,
    publicly_indexed_without_login: bool,
    date_signal: str | None = None,
    promo_signal: str | None = None,
    price_text: str | None = None,
) -> OpportunisticSeedSignal:
    """Public social/editor evidence may seed investigation but never verify a fare."""

    if not publicly_indexed_without_login:
        raise ValueError("non-public/login-gated social content is outside the contract")
    if not route_signal.strip():
        raise ValueError("public social seed requires a route signal")
    return OpportunisticSeedSignal(
        source_id=source_id,
        source_url=source_url,
        observed_at=observed_at,
        route_signal=route_signal.strip(),
        date_signal=date_signal,
        promo_signal=promo_signal,
        price_text=price_text,
    )


def _selection_reasons(
    probe: OutboundProbe,
    near: Sequence[OutboundFloor],
    horizon: Sequence[OutboundFloor],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if any(floor.probe == probe for floor in near):
        reasons.append("near_term_floor")
    if any(floor.probe == probe for floor in horizon):
        reasons.append("horizon_floor")
    if not reasons:
        reasons.append("candidate_limit_fill")
    return tuple(reasons)


def _floors_by_origin_market(
    probes: Sequence[OutboundProbe],
    window: str,
) -> tuple[OutboundFloor, ...]:
    groups: dict[tuple[str, str], list[OutboundProbe]] = {}
    for probe in probes:
        groups.setdefault((probe.origin, probe.market), []).append(probe)
    floors = [
        OutboundFloor(
            origin=origin,
            market=market,
            window=window,
            probe=min(group, key=_probe_sort_key),
        )
        for (origin, market), group in groups.items()
    ]
    floors.sort(key=lambda item: (item.market, item.origin, _probe_sort_key(item.probe)))
    return tuple(floors)


def _return_window_for_hours(
    one_way_hours: float,
    windows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for window in windows:
        maximum = window.get("max_one_way_hours")
        if maximum is None or one_way_hours <= float(maximum):
            return window
    return None


def _return_offsets(window: Mapping[str, Any]) -> tuple[int, ...]:
    values: list[int] = []
    for value in window.get("ideal_nights") or ():
        if isinstance(value, int) and value > 0 and value not in values:
            values.append(value)
    for key in ("min_nights", "max_nights"):
        value = window.get(key)
        if isinstance(value, int) and value > 0 and value not in values:
            values.append(value)
    return tuple(values)


def _probe_sort_key(probe: OutboundProbe) -> tuple[int, str, str, str]:
    return (probe.price_twd, probe.outbound_date, probe.origin, probe.destination)


def _append_unique_probe(items: list[OutboundProbe], probe: OutboundProbe) -> None:
    key = (probe.seed_id, probe.outbound_date, probe.price_twd)
    if all((item.seed_id, item.outbound_date, item.price_twd) != key for item in items):
        items.append(probe)


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"expected ISO date, got {value!r}") from exc
