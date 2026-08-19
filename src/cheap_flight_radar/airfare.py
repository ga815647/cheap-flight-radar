"""Anomaly-first airfare domain records used by production Radar runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ASIA_OCEANIA_COUNTRIES = frozenset({
    "afghanistan","armenia","australia","azerbaijan","bahrain","bangladesh","bhutan","brunei","cambodia",
    "china","cyprus","east timor","timor-leste","fiji","georgia","hong kong","india","indonesia","iran","iraq",
    "israel","japan","jordan","kazakhstan","kiribati","kuwait","kyrgyzstan","laos","lebanon","macao","macau",
    "malaysia","maldives","marshall islands","micronesia","mongolia","myanmar","nauru","nepal","new caledonia",
    "new zealand","north korea","northern mariana islands","oman","pakistan","palau","palestine","papua new guinea",
    "philippines","qatar","samoa","saudi arabia","singapore","solomon islands","south korea","korea","sri lanka",
    "syria","taiwan","tajikistan","thailand","tonga","turkey","türkiye","turkmenistan","tuvalu",
    "united arab emirates","uae","uzbekistan","vanuatu","vietnam","viet nam","yemen","guam","french polynesia",
})

_COUNTRY_ALIASES = {
    "republic of korea": "south korea",
    "korea, republic of": "south korea",
    "korea, south": "south korea",
    "people's republic of china": "china",
    "hong kong sar china": "hong kong",
    "macao sar china": "macao",
    "brunei darussalam": "brunei",
    "lao people's democratic republic": "laos",
    "viet nam": "vietnam",
}


@dataclass(frozen=True)
class AirportIdentity:
    iata: str
    city: str | None = None
    country: str | None = None

    def __post_init__(self) -> None:
        if len(self.iata) != 3 or self.iata != self.iata.upper() or not self.iata.isalpha():
            raise ValueError("airport identity requires an exact uppercase three-letter IATA code")


@dataclass(frozen=True)
class AirfareLeg:
    """One normalized itinerary leg or segment.

    ``date`` is always present because every exact Radar request is date-scoped.
    Provider-returned departure/arrival values are optional so discovery records
    can still exist without pretending a time was observed.
    """

    origin: str
    destination: str
    date: str
    departure_time: str | None = None
    arrival_time: str | None = None

    def __post_init__(self) -> None:
        for value, label in ((self.origin, "origin"), (self.destination, "destination")):
            if len(value) != 3 or value != value.upper() or not value.isalpha():
                raise ValueError(f"{label} must be an exact uppercase IATA code")


@dataclass(frozen=True)
class AirfareRecord:
    """Provider-independent airfare evidence.

    No gflights (or other provider) object is retained here. The record keeps
    normalized domain facts plus reproduction/evidence identifiers.

    For gflights round-trip exact search, the public result exposes the chosen
    outbound segments while ``offer()`` locks and prices both directions. The
    requested return date therefore remains part of the exact search context;
    it must not be inferred from the last outbound connection segment.
    """

    record_id: str
    provider: str
    surface: str
    origin: AirportIdentity
    destination: AirportIdentity
    legs: tuple[AirfareLeg, ...]
    current_price_twd: int | None
    observed_at: str
    verification_state: str
    evidence_class: str
    complete_airfare: bool
    typical_price_twd: int | None = None
    discount_percent: float | None = None
    anomaly_authority: str | None = None
    airlines: tuple[str, ...] = ()
    booking_url: str | None = None
    booking_token: str | None = None
    evidence_url: str | None = None
    reproducible_search: Mapping[str, Any] = field(default_factory=dict)

    @property
    def outbound_date(self) -> str | None:
        return self.legs[0].date if self.legs else None

    @property
    def return_date(self) -> str | None:
        # gflights round-trip ``search`` returns outbound-choice segments only.
        # The requested return date is nevertheless part of the exact priced
        # search/offer context, so use it instead of mistaking an outbound
        # connection date for the trip return date.
        if self.surface == "exact":
            requested = self.reproducible_search.get("return_date")
            if isinstance(requested, str) and requested:
                return requested
            return None
        return self.legs[-1].date if len(self.legs) > 1 else None

    @property
    def is_round_trip(self) -> bool:
        if self.surface == "exact":
            return self.return_date is not None
        return len(self.legs) >= 2 and self.legs[-1].destination == self.origin.iata

    @property
    def has_provider_leg_identity(self) -> bool:
        return bool(self.legs) and all(
            leg.departure_time is not None and leg.arrival_time is not None
            for leg in self.legs
        )

    @property
    def provider_segments_cover_complete_trip(self) -> bool:
        """Whether normalized provider segments themselves cover the full trip.

        A round-trip exact record may still be a complete priced/revalidated
        airfare when this is false: gflights 0.3.0 ``offer()`` internally locks
        the return choice but does not expose those return segments publicly.
        """
        if not self.has_provider_leg_identity:
            return False
        if self.is_round_trip:
            return self.legs[-1].destination == self.origin.iata
        return True


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    surface: str
    coverage_state: str
    records: tuple[AirfareRecord, ...] = ()
    error: str | None = None
    request_sent: bool = True


def normalize_country_name(country: str | None) -> str | None:
    if not country:
        return None
    normalized = " ".join(country.strip().casefold().replace("’", "'").split())
    return _COUNTRY_ALIASES.get(normalized, normalized)


def is_asia_oceania(country: str | None) -> bool:
    normalized = normalize_country_name(country)
    return normalized in ASIA_OCEANIA_COUNTRIES if normalized else False


def is_international_asia_oceania(country: str | None) -> bool:
    normalized = normalize_country_name(country)
    return bool(normalized and normalized != "taiwan" and normalized in ASIA_OCEANIA_COUNTRIES)


def market_slice(country: str | None) -> str:
    normalized = normalize_country_name(country)
    if normalized == "japan":
        return "japan"
    if normalized in {"south korea", "korea"}:
        return "korea"
    if normalized in {"china", "hong kong", "macao", "macau"}:
        return "china"
    return "other_asia_oceania"
