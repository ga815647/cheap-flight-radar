"""Qualified TWD-0 Kiwi.com MCP adapter for known-route fallback execution.

This adapter is intentionally narrow.  It does not provide destination-free
Deal/anomaly discovery and it does not replace Google Flight Deals truth.  It
borrows Kiwi.com's official public remote MCP ``search-flight`` surface only
for known-route exact/flexible completion when the primary gflights access
lane fails.

Production calls use one MCP tool invocation, no credential, no proxy, no
browser/TLS impersonation and no CFR retry loop.  The normalized records below
are provider-independent CFR evidence.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ..airfare import AirfareLeg, AirfareRecord, AirportIdentity, ProviderResult

ENDPOINT = "https://mcp.kiwi.com"
PROVIDER_ID = "kiwi_mcp"
TOOL_NAME = "search-flight"


def _ddmmyyyy(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _iata(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip().upper()
    return result if len(result) == 3 and result.isalpha() else None


def _record_id(surface: str, query: Mapping[str, Any], itinerary_id: str) -> str:
    raw = json.dumps([surface, query, itinerary_id], ensure_ascii=False, sort_keys=True)
    return "kiwi-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_jsonable(item) for item in value]
    return value


def _result_payload(result: Any) -> Mapping[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, Mapping):
        return structured
    if structured is not None:
        converted = _jsonable(structured)
        if isinstance(converted, Mapping):
            return converted
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            return parsed
    return {}


def _segments(raw_direction: Mapping[str, Any]) -> tuple[AirfareLeg, ...]:
    legs: list[AirfareLeg] = []
    for raw in raw_direction.get("segments") or ():
        if not isinstance(raw, Mapping):
            return ()
        origin = _iata(raw.get("from"))
        destination = _iata(raw.get("to"))
        departure = str(raw.get("departureTime") or "")
        arrival = str(raw.get("arrivalTime") or "")
        if not origin or not destination or not departure:
            return ()
        legs.append(
            AirfareLeg(
                origin=origin,
                destination=destination,
                date=departure[:10],
                departure_time=departure or None,
                arrival_time=arrival or None,
            )
        )
    return tuple(legs)


def _airport_identity(
    itinerary: Mapping[str, Any],
    *,
    direction: str,
    endpoint: str,
    fallback: str,
) -> AirportIdentity:
    raw_direction = itinerary.get(direction) or {}
    segments = raw_direction.get("segments") if isinstance(raw_direction, Mapping) else None
    segment = None
    if isinstance(segments, Sequence) and segments:
        candidate = segments[0] if endpoint == "from" else segments[-1]
        if isinstance(candidate, Mapping):
            segment = candidate
    iata = _iata((segment or {}).get(endpoint)) or fallback
    city_key = "fromCity" if endpoint == "from" else "toCity"
    country_key = "fromCountry" if endpoint == "from" else "toCountry"
    return AirportIdentity(
        iata=iata,
        city=str((segment or {}).get(city_key)) if (segment or {}).get(city_key) else None,
        country=str((segment or {}).get(country_key)) if (segment or {}).get(country_key) else None,
    )


def _normalize(
    payload: Mapping[str, Any],
    *,
    surface: str,
    origin: str,
    destination: str,
    query: Mapping[str, Any],
    verification_state: str,
) -> tuple[AirfareRecord, ...]:
    if str(payload.get("currency") or "").upper() != "TWD":
        return ()
    records: list[AirfareRecord] = []
    for raw in payload.get("itineraries") or ():
        if not isinstance(raw, Mapping):
            continue
        price = _positive_int(raw.get("price"))
        outbound = raw.get("outbound") or {}
        inbound = raw.get("inbound") or {}
        if not price or not isinstance(outbound, Mapping) or not isinstance(inbound, Mapping):
            continue
        outbound_legs = _segments(outbound)
        inbound_legs = _segments(inbound)
        legs = (*outbound_legs, *inbound_legs)
        if not outbound_legs or not inbound_legs:
            continue
        if outbound_legs[0].origin != origin or outbound_legs[-1].destination != destination:
            continue
        if inbound_legs[0].origin != destination or inbound_legs[-1].destination != origin:
            continue
        itinerary_id = str(raw.get("id") or f"{outbound_legs[0].date}-{inbound_legs[0].date}-{price}")
        airlines: list[str] = []
        for direction in (outbound, inbound):
            for segment in direction.get("segments") or ():
                if isinstance(segment, Mapping):
                    name = segment.get("carrierName") or segment.get("carrier")
                    if name and str(name) not in airlines:
                        airlines.append(str(name))
        records.append(
            AirfareRecord(
                record_id=_record_id(surface, query, itinerary_id),
                provider=PROVIDER_ID,
                surface=surface,
                origin=_airport_identity(raw, direction="outbound", endpoint="from", fallback=origin),
                destination=_airport_identity(raw, direction="outbound", endpoint="to", fallback=destination),
                legs=tuple(legs),
                current_price_twd=price,
                observed_at=datetime.now(timezone.utc).isoformat(),
                verification_state=verification_state,
                evidence_class="round_trip_fare",
                complete_airfare=True,
                airlines=tuple(airlines),
                booking_url=str(raw.get("bookingUrl")) if raw.get("bookingUrl") else None,
                evidence_url=ENDPOINT,
                reproducible_search={
                    "provider": PROVIDER_ID,
                    "tool": TOOL_NAME,
                    "endpoint": ENDPOINT,
                    **dict(query),
                },
            )
        )
    return tuple(sorted(records, key=lambda item: (item.current_price_twd or 10**12, item.record_id)))


class KiwiMCPAdapter:
    """One-shot official Kiwi.com MCP known-route access adapter."""

    provider = PROVIDER_ID

    def __init__(
        self,
        *,
        caller: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]] | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self._caller = caller
        self._timeout_seconds = timeout_seconds

    async def _live_call(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async def invoke() -> Mapping[str, Any]:
            async with streamable_http_client(ENDPOINT) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(TOOL_NAME, arguments=dict(arguments))
                    if getattr(result, "isError", False):
                        raise RuntimeError("Kiwi MCP search-flight returned an error result")
                    return _result_payload(result)

        return await asyncio.wait_for(invoke(), timeout=self._timeout_seconds)

    async def _search(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        caller = self._caller or self._live_call
        return await caller(arguments)

    async def exact(
        self,
        *,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
    ) -> ProviderResult:
        query = {
            "flyFrom": origin,
            "flyTo": destination,
            "departureDate": _ddmmyyyy(departure_date),
            "returnDate": _ddmmyyyy(return_date),
            "adults": 1,
            "children": 0,
            "infants": 0,
            "cabinClass": "M",
            "currency": "TWD",
            "allow_self_transfer": True,
            "sort": "price",
        }
        try:
            payload = await self._search(query)
        except Exception as exc:  # fail closed at provider boundary
            return ProviderResult(PROVIDER_ID, "exact", "failed", error=f"{type(exc).__name__}: {exc}")
        if str(payload.get("currency") or "").upper() != "TWD":
            return ProviderResult(PROVIDER_ID, "exact", "failed", error="Kiwi MCP did not return TWD currency")
        records = _normalize(
            payload,
            surface="exact",
            origin=origin,
            destination=destination,
            query={"departure_date": departure_date, "return_date": return_date},
            verification_state="revalidated",
        )
        return ProviderResult(PROVIDER_ID, "exact", "complete", records)

    async def cheapest_dates(
        self,
        *,
        origin: str,
        destination: str,
        start_date: str,
        months: int,
        trip_duration_days: int | None = None,
    ) -> ProviderResult:
        try:
            start = date.fromisoformat(start_date)
        except ValueError as exc:
            return ProviderResult(PROVIDER_ID, "cheapest_dates", "failed", error=str(exc), request_sent=False)
        end = start + timedelta(days=max(1, int(months)) * 30 - 1)
        query: dict[str, Any] = {
            "flyFrom": origin,
            "flyTo": destination,
            "departureDate": start.strftime("%d/%m/%Y"),
            "departureDateTo": end.strftime("%d/%m/%Y"),
            "adults": 1,
            "children": 0,
            "infants": 0,
            "cabinClass": "M",
            "currency": "TWD",
            "allow_self_transfer": True,
            "sort": "price",
        }
        if trip_duration_days is not None and trip_duration_days > 1:
            query["nights_in_dst_from"] = int(trip_duration_days)
            query["nights_in_dst_to"] = int(trip_duration_days)
        try:
            payload = await self._search(query)
        except Exception as exc:  # fail closed at provider boundary
            return ProviderResult(PROVIDER_ID, "cheapest_dates", "failed", error=f"{type(exc).__name__}: {exc}")
        if str(payload.get("currency") or "").upper() != "TWD":
            return ProviderResult(PROVIDER_ID, "cheapest_dates", "failed", error="Kiwi MCP did not return TWD currency")
        records = _normalize(
            payload,
            surface="cheapest_dates",
            origin=origin,
            destination=destination,
            query={
                "start_date": start_date,
                "end_date": end.isoformat(),
                "trip_duration_days": trip_duration_days,
            },
            verification_state="current_search_evidence",
        )
        return ProviderResult(PROVIDER_ID, "cheapest_dates", "complete", records)
