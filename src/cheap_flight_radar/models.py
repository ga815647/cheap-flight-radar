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
