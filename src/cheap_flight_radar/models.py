"""Normalized collector and source-router data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchRequest:
    profile: str
    search_stage: str
    origin: str
    destination: str
    outbound_date: str
    return_date: str | None = None
    destination_country: str | None = None
    open_jaw_required: bool = False
    required_freshness: str = "live"


@dataclass(frozen=True)
class OriginSweepRequest:
    """Destination-free Stage A request.

    Deliberately has no destination or outbound-date field. A destination must be
    emitted by the origin sweep itself before a known-route probe can be built.
    """

    origin: str
    horizon_start: str
    horizon_days: int = 120
    near_term_days: int = 30
    destination_scope: str = "global"
    currency: str = "TWD"
    profiles: tuple[str, ...] = ("world", "japan", "korea", "china")

    def __post_init__(self) -> None:
        if len(self.origin) != 3 or self.origin != self.origin.upper():
            raise ValueError("origin must be an exact uppercase IATA airport")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if self.near_term_days < 0 or self.near_term_days > self.horizon_days:
            raise ValueError("near_term_days must be within the search horizon")


@dataclass(frozen=True)
class OutboundSeed:
    seed_id: str
    profile: str
    origin: str
    destination: str
    market: str
    source_id: str
    source_url: str
    observed_at: str
    evidence_kind: str
    destination_country: str | None = None
    outbound_date_hint: str | None = None
    return_date_hint: str | None = None
    displayed_price_twd: int | None = None
    discovery_mode: str = "origin_sweep"


@dataclass(frozen=True)
class OutboundProbe:
    seed_id: str
    profile: str
    origin: str
    destination: str
    market: str
    outbound_date: str
    price_twd: int
    one_way_hours: float
    source_id: str
    source_url: str
    observed_at: str
    destination_country: str | None = None
    fare_scope: str = "one_way"
    exact_airports: bool = True
    verification_state: str = "discovery"


@dataclass(frozen=True)
class SeriousOutbound:
    probe: OutboundProbe
    selection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class LiveReturnAirport:
    airport: str
    live_route_evidence: bool
    source_id: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ReturnExpansionRequest:
    seed_id: str
    profile: str
    foreign_origin: str
    taiwan_return_airport: str
    outbound_date: str
    return_date: str
    destination_country: str | None = None
    live_route_evidence_source_id: str | None = None


@dataclass(frozen=True)
class ReturnFare:
    seed_id: str
    foreign_origin: str
    taiwan_return_airport: str
    return_date: str
    price_twd: int
    source_id: str
    source_url: str
    observed_at: str
    exact_airports: bool = True
    exact_date: bool = True
    usable: bool = True


@dataclass(frozen=True)
class RoundTripBenchmark:
    origin: str
    destination: str
    outbound_date: str
    return_date: str
    price_twd: int
    source_id: str
    source_url: str
    observed_at: str
    usable: bool = True
    practicality: str = "comparable"


@dataclass(frozen=True)
class CompleteCandidate:
    seed_id: str
    origin: str
    destination: str
    outbound_date: str
    return_date: str
    taiwan_return_airport: str
    selected_kind: str
    selected_total_twd: int
    constructed_total_twd: int
    round_trip_benchmark_twd: int
    benchmark_source_id: str


@dataclass(frozen=True)
class ProviderState:
    provider: str
    credential_available: bool
    healthy: bool = True


@dataclass(frozen=True)
class ProviderPlanEntry:
    provider: str
    reason: str


@dataclass(frozen=True)
class RoutePlan:
    entries: tuple[ProviderPlanEntry, ...]
    coverage_state: str
    fallback_reason: str | None = None


@dataclass(frozen=True)
class FlightSegment:
    origin: str | None
    destination: str | None
    departure: str | None
    arrival: str | None
    marketing_carrier: str | None
    marketing_flight_number: str | None
    cabin: str | None = None


@dataclass(frozen=True)
class Journey:
    segments: tuple[FlightSegment, ...]


@dataclass(frozen=True)
class NormalizedOffer:
    provider: str
    search_stage: str
    profile: str
    requested_origin: str
    requested_destination: str
    journeys: tuple[Journey, ...]
    source_id: str | None
    source_url: str | None
    raw_price: str | int | float | None
    original_currency: str | None
    tax_semantics: str
    fare_family: str | None
    baggage_state: str
    freshness: str
    verification_state: str
    observed_at: str
    exact_airport_date: bool


@dataclass(frozen=True)
class CollectorResult:
    provider: str
    health: str
    coverage_state: str
    offers: tuple[NormalizedOffer, ...] = ()
    returned_items: int = 0
    rejected_items: int = 0
    error: str | None = None
