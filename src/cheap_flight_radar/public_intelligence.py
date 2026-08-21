"""Generic opportunistic public-intelligence provenance and dedupe primitives.

SR-F deliberately retired CFR's fixed-watch crawler/cadence/state machinery.
This module retains only source-agnostic Signal provenance/identity helpers for
best-effort public Web/social observations supplied by the ChatGPT orchestrator.
These records are never Deal/anomaly/backend coverage authority by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class DiscoverySighting:
    observation_id: str
    source_id: str
    source_url: str
    item_url: str
    observed_at: datetime
    title: str
    carrier: str | None = None
    sale_period: str | None = None
    travel_period: str | None = None
    route_set: tuple[str, ...] = ()
    promo_code: str | None = None
    price_text: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.observed_at)


@dataclass(frozen=True)
class DiscoveryCandidate:
    campaign_key: str
    first_seen_at: datetime
    first_discovery_source_id: str
    discovery_source_ids: tuple[str, ...]
    sightings: tuple[DiscoverySighting, ...]


def campaign_identity(sighting: DiscoverySighting) -> str | None:
    """Return a source/price-independent campaign key, or None if unresolved."""
    route_set = tuple(sorted({_clean_token(route) for route in sighting.route_set if _clean_token(route)}))
    required = (
        _clean_token(sighting.carrier),
        _clean_token(sighting.sale_period),
        _clean_token(sighting.travel_period),
    )
    if any(value is None for value in required) or not route_set:
        return None
    return "campaign:" + _stable_hash({
        "carrier": required[0],
        "sale_period": required[1],
        "travel_period": required[2],
        "route_set": route_set,
        "promo_code": _clean_token(sighting.promo_code),
    })


def exact_itinerary_identity(
    *,
    trip_type: str,
    exact_origin_airport: str,
    exact_destination_airport_when_known: str | None,
    outbound_date_or_window: str,
    return_date_or_window: str | None,
    operating_or_marketing_flight_identity_when_known: Sequence[str] = (),
) -> str:
    payload = {
        "trip_type": _clean_token(trip_type),
        "exact_origin_airport": _clean_token(exact_origin_airport),
        "exact_destination_airport_when_known": _clean_token(exact_destination_airport_when_known),
        "outbound_date_or_window": _clean_token(outbound_date_or_window),
        "return_date_or_window": _clean_token(return_date_or_window),
        "flight_identity": tuple(
            token for token in (_clean_token(value) for value in operating_or_marketing_flight_identity_when_known) if token
        ),
    }
    if not payload["trip_type"] or not payload["exact_origin_airport"] or not payload["outbound_date_or_window"]:
        raise ValueError("trip type, exact origin, and outbound date/window are required")
    return "itinerary:" + _stable_hash(payload)


def dedupe_campaign_sightings(
    sightings: Iterable[DiscoverySighting],
) -> tuple[tuple[DiscoveryCandidate, ...], tuple[DiscoverySighting, ...]]:
    groups: dict[str, list[DiscoverySighting]] = {}
    unresolved: list[DiscoverySighting] = []
    for sighting in sightings:
        key = campaign_identity(sighting)
        if key is None:
            unresolved.append(sighting)
        else:
            groups.setdefault(key, []).append(sighting)
    candidates: list[DiscoveryCandidate] = []
    for key, group in groups.items():
        ordered = sorted(group, key=lambda item: (item.observed_at, item.observation_id))
        candidates.append(DiscoveryCandidate(
            campaign_key=key,
            first_seen_at=ordered[0].observed_at,
            first_discovery_source_id=ordered[0].source_id,
            discovery_source_ids=tuple(dict.fromkeys(item.source_id for item in ordered)),
            sightings=tuple(ordered),
        ))
    candidates.sort(key=lambda item: (item.first_seen_at, item.campaign_key))
    unresolved.sort(key=lambda item: (item.observed_at, item.observation_id))
    return tuple(candidates), tuple(unresolved)


def make_observation_id(source_id: str, item_url: str, title: str, observed_at: datetime) -> str:
    _require_aware(observed_at)
    return "obs:" + _stable_hash({
        "source_id": source_id,
        "item_url": item_url,
        "title": title.strip(),
        "observed_at": observed_at.isoformat(),
    })


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")


def _clean_token(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).strip().split()).casefold()
    return cleaned or None


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()[:24]
