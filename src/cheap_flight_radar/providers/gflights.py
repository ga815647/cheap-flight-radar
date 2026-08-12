"""Production adapter for the pinned ``gflights==0.3.0`` substrate.

The adapter is the only layer allowed to see gflights result objects. Core Radar
code receives immutable normalized airfare records instead.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

from ..airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult

PRODUCTION_USER_AGENT = "CheapFlightRadar/0.1 (+public-research; no-proxy)"
PROVIDER_ID = "gflights"


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        raw = to_dict()
        if isinstance(raw, Mapping):
            return raw
    names = (
        "origin_iata", "destination_iata", "destination_city", "destination_country",
        "outbound_date", "return_date", "price", "typical_price", "discount_pct",
        "duration_minutes", "stops", "airline_code", "airline_name", "booking_url",
        "booking_token", "name", "country", "flight_airport", "nearest_airport",
        "date_from", "date_to", "airline", "departure_date", "legs", "airline_names",
        "from_airport", "to_airport", "departure_time", "arrival_time", "arrival_date",
    )
    return {name: getattr(value, name) for name in names if hasattr(value, name)}


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit() or ch == ".")
        if not digits:
            return None
        value = digits
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _positive_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _iata(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip().upper()
    return result if len(result) == 3 and result.isalpha() else None


def _required_iata(value: str, label: str) -> str:
    normalized = _iata(value)
    if normalized is None:
        raise ValueError(f"{label} must be an exact uppercase IATA airport")
    return normalized


def _record_id(surface: str, params: Mapping[str, Any], discriminator: str) -> str:
    payload = json.dumps([surface, params, discriminator], sort_keys=True, ensure_ascii=False, default=str)
    return "gf-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_legs(raw_item: Mapping[str, Any], fallback_date: str) -> tuple[AirfareLeg, ...]:
    raw_legs = raw_item.get("legs")
    if not isinstance(raw_legs, Sequence) or isinstance(raw_legs, (str, bytes)):
        return ()
    result: list[AirfareLeg] = []
    for raw_leg in raw_legs:
        leg = _mapping(raw_leg)
        origin = _iata(leg.get("from_airport"))
        destination = _iata(leg.get("to_airport"))
        if not origin or not destination:
            return ()
        departure_date = leg.get("departure_date")
        result.append(
            AirfareLeg(
                origin=origin,
                destination=destination,
                date=str(departure_date) if departure_date else fallback_date,
                departure_time=str(leg["departure_time"]) if leg.get("departure_time") else None,
                arrival_time=str(leg["arrival_time"]) if leg.get("arrival_time") else None,
            )
        )
    return tuple(result)


def _airlines(*values: Any) -> tuple[str, ...]:
    flat: list[str] = []
    for value in values:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            flat.extend(str(item) for item in value if item)
        elif value:
            flat.append(str(value))
    return tuple(dict.fromkeys(flat))


class GFlightsAdapter:
    """Typed normalization boundary around gflights 0.3.0.

    Production construction always supplies the project identity explicitly and
    always disables proxying. Tests may inject a fake client without importing
    the optional native dependency.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        observed_at: Callable[[], str] = _now,
    ) -> None:
        self._observed_at = observed_at
        if client is not None:
            self._client = client
            return
        if client_factory is None:
            from gflights import Client
            client_factory = Client
        self._client = client_factory(
            user_agent=PRODUCTION_USER_AGENT,
            proxy=None,
            currency="TWD",
            lang="en",
            country="TW",
        )

    async def flight_deals(self, *, origin: str, anchor_departure: str, anchor_return: str) -> ProviderResult:
        source_origin = _required_iata(origin, "origin")
        params = {
            "origin": source_origin,
            "date": anchor_departure,
            "return_date": anchor_return,
            "currency": "TWD",
            "country": "TW",
        }
        try:
            raw_items = await self._client.deals(origin=source_origin, date=anchor_departure, return_date=anchor_return)
        except Exception as exc:
            return ProviderResult(PROVIDER_ID, "flight_deals", "failed", error=f"{type(exc).__name__}: {exc}")
        records: list[AirfareRecord] = []
        for raw in raw_items:
            item = _mapping(raw)
            destination = _iata(item.get("destination_iata"))
            returned_origin = _iata(item.get("origin_iata")) or source_origin
            outbound = item.get("outbound_date")
            ret = item.get("return_date")
            price = _positive_int(item.get("price"))
            typical = _positive_int(item.get("typical_price"))
            discount_value = _positive_float(item.get("discount_pct"))
            if not destination:
                continue
            legs: tuple[AirfareLeg, ...] = ()
            if isinstance(outbound, str) and isinstance(ret, str):
                legs = (
                    AirfareLeg(returned_origin, destination, outbound),
                    AirfareLeg(destination, returned_origin, ret),
                )
            complete = bool(price and legs)
            qualified = bool(complete and typical and discount_value)
            booking = item.get("booking_url") if isinstance(item.get("booking_url"), str) else None
            token = item.get("booking_token") if isinstance(item.get("booking_token"), str) else None
            records.append(
                AirfareRecord(
                    record_id=_record_id("flight_deals", params, f"{returned_origin}:{destination}:{outbound}:{ret}"),
                    provider=PROVIDER_ID,
                    surface="flight_deals",
                    origin=AirportIdentity(returned_origin),
                    destination=AirportIdentity(
                        destination,
                        city=str(item["destination_city"]) if item.get("destination_city") else None,
                        country=str(item["destination_country"]) if item.get("destination_country") else None,
                    ),
                    legs=legs,
                    current_price_twd=price,
                    typical_price_twd=typical,
                    discount_percent=discount_value,
                    anomaly_authority="google_flight_deals" if qualified else None,
                    airlines=_airlines(item.get("airline_name"), item.get("airline_code")),
                    booking_url=booking,
                    booking_token=token,
                    evidence_url=booking,
                    reproducible_search=params,
                    observed_at=self._observed_at(),
                    verification_state="discovery",
                    evidence_class="qualified_round_trip_deal" if qualified else "weak_seed",
                    complete_airfare=complete,
                )
            )
        return ProviderResult(PROVIDER_ID, "flight_deals", "complete", tuple(records))

    async def explore(self, *, origin: str, month: int | None = None, duration: str = "week", max_price: int | None = None) -> ProviderResult:
        source_origin = _required_iata(origin, "origin")
        params = {"origin": source_origin, "month": month, "duration": duration, "max_price": max_price, "currency": "TWD", "country": "TW"}
        try:
            raw_items = await self._client.explore(origin=source_origin, month=month, duration=duration, max_price=max_price)
        except Exception as exc:
            return ProviderResult(PROVIDER_ID, "explore", "failed", error=f"{type(exc).__name__}: {exc}")
        records: list[AirfareRecord] = []
        for raw in raw_items:
            item = _mapping(raw)
            destination = _iata(item.get("flight_airport")) or _iata(item.get("nearest_airport"))
            if not destination:
                continue
            outbound, ret = item.get("date_from"), item.get("date_to")
            legs: tuple[AirfareLeg, ...] = ()
            if isinstance(outbound, str) and isinstance(ret, str):
                legs = (AirfareLeg(source_origin, destination, outbound), AirfareLeg(destination, source_origin, ret))
            price = _positive_int(item.get("price"))
            records.append(
                AirfareRecord(
                    record_id=_record_id("explore", params, f"{destination}:{outbound}:{ret}"),
                    provider=PROVIDER_ID,
                    surface="explore",
                    origin=AirportIdentity(source_origin),
                    destination=AirportIdentity(
                        destination,
                        city=str(item["name"]) if item.get("name") else None,
                        country=str(item["country"]) if item.get("country") else None,
                    ),
                    legs=legs,
                    current_price_twd=price,
                    observed_at=self._observed_at(),
                    verification_state="seed_only",
                    evidence_class="weak_seed",
                    complete_airfare=bool(price and legs),
                    airlines=_airlines(item.get("airline")),
                    booking_token=str(item["booking_token"]) if item.get("booking_token") else None,
                    reproducible_search=params,
                )
            )
        return ProviderResult(PROVIDER_ID, "explore", "complete", tuple(records))

    async def exact(self, *, origin: str, destination: str, departure_date: str, return_date: str | None = None, resolve_booking_offer: bool = True) -> ProviderResult:
        source_origin = _required_iata(origin, "origin")
        source_destination = _required_iata(destination, "destination")
        params = {"origin": source_origin, "destination": source_destination, "date": departure_date, "return_date": return_date, "currency": "TWD", "country": "TW"}
        try:
            raw_items = await self._client.search(origin=source_origin, destination=source_destination, date=departure_date, return_date=return_date)
        except Exception as exc:
            return ProviderResult(PROVIDER_ID, "exact", "failed", error=f"{type(exc).__name__}: {exc}")
        candidates = [(_positive_int(_mapping(item).get("price")), _mapping(item)) for item in raw_items]
        candidates = [(price, item) for price, item in candidates if price]
        if not candidates:
            return ProviderResult(PROVIDER_ID, "exact", "empty")
        search_price, item = min(candidates, key=lambda pair: pair[0])
        provider_legs = _provider_legs(item, departure_date)
        legs = provider_legs or (AirfareLeg(source_origin, source_destination, departure_date),)
        booking_token = str(item["booking_token"]) if item.get("booking_token") else None
        current_price = search_price
        booking_url: str | None = None
        offer_airlines: tuple[str, ...] = ()
        offer_error: str | None = None
        if resolve_booking_offer and hasattr(self._client, "offer"):
            try:
                raw_offers = await self._client.offer(origin=source_origin, destination=source_destination, date=departure_date, return_date=return_date)
                offers = [(_positive_int(_mapping(raw).get("price")), _mapping(raw)) for raw in raw_offers]
                offers = [(price, raw) for price, raw in offers if price]
                if offers:
                    offer_price, offer = min(offers, key=lambda pair: pair[0])
                    current_price = offer_price
                    if isinstance(offer.get("booking_url"), str):
                        booking_url = offer["booking_url"]
                    offer_airlines = _airlines(offer.get("airline_names"))
            except Exception as exc:
                offer_error = f"{type(exc).__name__}: {exc}"
        record = AirfareRecord(
            record_id=_record_id("exact", params, f"{source_origin}:{source_destination}:{departure_date}:{return_date}:{current_price}"),
            provider=PROVIDER_ID,
            surface="exact",
            origin=AirportIdentity(source_origin),
            destination=AirportIdentity(source_destination),
            legs=legs,
            current_price_twd=current_price,
            observed_at=self._observed_at(),
            verification_state="revalidated" if booking_url or booking_token or provider_legs else "exact_search",
            evidence_class="exact_revalidated_candidate",
            complete_airfare=bool(return_date and current_price) or bool(current_price and not return_date),
            airlines=_airlines(item.get("airline"), offer_airlines),
            booking_url=booking_url,
            booking_token=booking_token,
            evidence_url=booking_url,
            reproducible_search={**params, "search_price_twd": search_price, "booking_offer_error": offer_error},
        )
        return ProviderResult(PROVIDER_ID, "exact", "complete", (record,))

    async def cheapest_dates(self, *, origin: str, destination: str, start_date: str, months: int = 3, trip_duration_days: int | None = None) -> ProviderResult:
        source_origin = _required_iata(origin, "origin")
        source_destination = _required_iata(destination, "destination")
        params = {"origin": source_origin, "destination": source_destination, "date": start_date, "months": months, "trip_duration_days": trip_duration_days, "currency": "TWD", "country": "TW"}
        try:
            raw_items = await self._client.cheapest_dates(origin=source_origin, destination=source_destination, date=start_date, months=months, trip_duration_days=trip_duration_days)
        except Exception as exc:
            return ProviderResult(PROVIDER_ID, "cheapest_dates", "failed", error=f"{type(exc).__name__}: {exc}")
        records: list[AirfareRecord] = []
        for raw in raw_items:
            item = _mapping(raw)
            dep, ret = item.get("departure_date"), item.get("return_date")
            price = _positive_int(item.get("price"))
            if not isinstance(dep, str) or not price:
                continue
            legs = [AirfareLeg(source_origin, source_destination, dep)]
            if isinstance(ret, str):
                legs.append(AirfareLeg(source_destination, source_origin, ret))
            records.append(
                AirfareRecord(
                    record_id=_record_id("cheapest_dates", params, f"{dep}:{ret}:{price}"),
                    provider=PROVIDER_ID,
                    surface="cheapest_dates",
                    origin=AirportIdentity(source_origin),
                    destination=AirportIdentity(source_destination),
                    legs=tuple(legs),
                    current_price_twd=price,
                    observed_at=self._observed_at(),
                    verification_state="seed_only",
                    evidence_class="weak_seed",
                    complete_airfare=bool(ret),
                    reproducible_search=params,
                )
            )
        return ProviderResult(PROVIDER_ID, "cheapest_dates", "complete", tuple(records))

    async def open_jaw(self, *, legs: Sequence[tuple[str, str, str]]) -> ProviderResult:
        if len(legs) < 2:
            raise ValueError("open-jaw/multi-city exact search requires at least two legs")
        normalized = [
            (_required_iata(str(origin).upper(), "origin"), _required_iata(str(destination).upper(), "destination"), str(date))
            for origin, destination, date in legs
        ]
        params = {"legs": normalized, "currency": "TWD", "country": "TW"}
        try:
            raw_items = await self._client.multi_city_search(normalized)
        except Exception as exc:
            return ProviderResult(PROVIDER_ID, "open_jaw", "failed", error=f"{type(exc).__name__}: {exc}")
        candidates = [(_positive_int(_mapping(item).get("price")), _mapping(item)) for item in raw_items]
        candidates = [(price, item) for price, item in candidates if price]
        if not candidates:
            return ProviderResult(PROVIDER_ID, "open_jaw", "empty")
        price, item = min(candidates, key=lambda pair: pair[0])
        provider_legs = _provider_legs(item, normalized[0][2])
        airfare_legs = provider_legs or tuple(AirfareLeg(origin, destination, date) for origin, destination, date in normalized)
        record = AirfareRecord(
            record_id=_record_id("open_jaw", params, str(price)),
            provider=PROVIDER_ID,
            surface="open_jaw",
            origin=AirportIdentity(normalized[0][0]),
            destination=AirportIdentity(normalized[0][1]),
            legs=airfare_legs,
            current_price_twd=price,
            observed_at=self._observed_at(),
            verification_state="revalidated" if item.get("booking_token") or provider_legs else "exact_search",
            evidence_class="exact_revalidated_candidate",
            complete_airfare=True,
            airlines=_airlines(item.get("airline")),
            booking_token=str(item["booking_token"]) if item.get("booking_token") else None,
            reproducible_search=params,
        )
        return ProviderResult(PROVIDER_ID, "open_jaw", "complete", (record,))
