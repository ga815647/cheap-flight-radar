from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URL = "https://www.searchapi.io/api/v1/search"
KEY = os.environ.get("SEARCHAPI_API_KEY", "")
OUT = Path("research-output/searchapi-china-decision.json")
REQUESTS = 0

CASES = {
    "C1": ("TSA", "SHA", "2026-10-13", "2026-10-17"),
    "C2": ("TPE", "XMN", "2026-10-13", "2026-10-17"),
}
# Exact flight-number sets from FlyAI formal-key artifact 9067758804.
FLYAI_FLIGHTS = {
    "C1": {"AE211", "CA197", "CA198", "CI201", "CI202", "FM3001", "FM3002", "MF8511", "MF8542", "MF8547", "MF882", "MF883", "MU5098", "MU8628"},
    "C2": {"9C8804", "9C8807", "9C8815", "9C8951", "CX461", "CX495", "CX978", "HX232", "HX234", "HX246", "HX253", "HX255", "HX261", "HX283", "MF887", "MF888", "NX132", "NX615", "NX621"},
}


def call(params: Mapping[str, Any]) -> dict[str, Any]:
    global REQUESTS
    if not KEY:
        raise RuntimeError("SEARCHAPI_API_KEY missing")
    if REQUESTS >= 8:
        raise RuntimeError("8-request China decision budget exceeded")
    clean = {k: v for k, v in params.items() if v is not None}
    req = Request(
        API_URL + "?" + urlencode(clean),
        headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
    )
    REQUESTS += 1
    with urlopen(req, timeout=120) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(str(payload.get("error")))
    return payload


def params(origin: str, dest: str, out: str, back: str) -> dict[str, Any]:
    return {
        "engine": "google_flights",
        "flight_type": "round_trip",
        "departure_id": origin,
        "arrival_id": dest,
        "outbound_date": out,
        "return_date": back,
        "travel_class": "economy",
        "adults": 1,
        "currency": "TWD",
        "gl": "tw",
        "hl": "en",
        "stops": "any",
        "sort_by": "price",
        "show_cheapest_flights": "true",
        "separate_tickets": 0,
    }


def items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for key in ("best_flights", "other_flights"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                out.append(item)
    return out


def exact(item: Mapping[str, Any], origin: str, dest: str, date: str) -> bool:
    flights = item.get("flights") or []
    if not flights:
        return False
    dep = flights[0].get("departure_airport") or {}
    arr = flights[-1].get("arrival_airport") or {}
    return dep.get("id") == origin and arr.get("id") == dest and dep.get("date") == date


def num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def sanitize_selected(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for journey in payload.get("selected_flights") or []:
        flights = []
        for f in journey.get("flights") or []:
            dep, arr = f.get("departure_airport") or {}, f.get("arrival_airport") or {}
            flights.append({
                "origin": dep.get("id"), "destination": arr.get("id"),
                "departure_date": dep.get("date"), "departure_time": dep.get("time"),
                "arrival_date": arr.get("date"), "arrival_time": arr.get("time"),
                "airline": f.get("airline"), "flight_number": f.get("flight_number"),
            })
        result.append({"price": journey.get("price"), "flights": flights})
    return result


def options(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{
        "book_with": x.get("book_with"),
        "flight_numbers": list(x.get("flight_numbers") or []),
        "fare_type": x.get("fare_type"),
        "option_title": x.get("option_title"),
        "price": x.get("price"),
        "baggage_prices": list(x.get("baggage_prices") or []),
        "local_prices": list(x.get("local_prices") or []),
        "is_split_booking": bool(x.get("is_split_booking")),
    } for x in payload.get("booking_options") or [] if isinstance(x, Mapping)]


def option_id(x: Mapping[str, Any]) -> tuple[Any, ...]:
    return (x.get("book_with"), tuple(x.get("flight_numbers") or []), x.get("fare_type"), x.get("option_title"), bool(x.get("is_split_booking")))


def run_case(case_id: str, expected: tuple[str, str, str, str]) -> dict[str, Any]:
    origin, dest, out_date, back_date = expected
    p = params(*expected)
    first = call(p)
    outbounds = [x for x in items(first) if exact(x, origin, dest, out_date) and x.get("departure_token")]
    outbounds.sort(key=lambda x: num(x.get("price")))
    if not outbounds:
        return {"exact_outbound": False, "booking_revalidation_success": False}

    returns_payload = call({**p, "departure_token": outbounds[0]["departure_token"]})
    returns = [x for x in items(returns_payload) if exact(x, dest, origin, back_date) and x.get("booking_token")]
    returns.sort(key=lambda x: num(x.get("price")))
    if not returns:
        return {"exact_outbound": True, "exact_return": False, "booking_revalidation_success": False}

    booking_params = {**p, "booking_token": returns[0]["booking_token"]}
    b1, b2 = call(booking_params), call(booking_params)
    o1, o2 = options(b1), options(b2)
    low1 = min(o1, key=lambda x: num(x.get("price"))) if o1 else None
    match = next((x for x in o2 if low1 and option_id(x) == option_id(low1)), None)
    selected = sanitize_selected(b1)
    selected_flight_numbers = [f.get("flight_number") for j in selected for f in j.get("flights") or [] if f.get("flight_number")]
    flyai_components = FLYAI_FLIGHTS.get(case_id, set())
    component_hits = [n for n in selected_flight_numbers if n.replace(" ", "") in flyai_components]
    return {
        "exact_outbound": True,
        "exact_return": True,
        "selected_search_price_twd": returns[0].get("price"),
        "selected_flights": selected,
        "booking_options": o1,
        "lowest_booking_option": low1,
        "booking_revalidation_success": bool(o2),
        "same_lowest_option": match is not None,
        "same_lowest_option_price": bool(match and low1 and match.get("price") == low1.get("price")),
        "selected_flight_numbers": selected_flight_numbers,
        "flyai_formal_component_hits": component_hits,
        "all_selected_flight_components_seen_in_flyai_formal_set": bool(selected_flight_numbers) and len(component_hits) == len(selected_flight_numbers),
        "note": "Flight-number component overlap is not proof that FlyAI returned the identical combined itinerary because the formal artifact retained per-case flight-number sets, not offer grouping.",
    }


def main() -> int:
    result = {
        "provider": "SearchAPI.io Google Flights API",
        "purpose": "focused China decision reference",
        "observed_at_asia_taipei": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
        "cases": {}, "requests_used": 0, "error": None,
    }
    try:
        for cid, expected in CASES.items():
            result["cases"][cid] = run_case(cid, expected)
    except Exception as exc:
        result["error"] = str(exc)
    result["requests_used"] = REQUESTS
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"requests_used": REQUESTS, "error": result["error"], "cases": result["cases"]}, ensure_ascii=False, indent=2))
    return 1 if result["error"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
