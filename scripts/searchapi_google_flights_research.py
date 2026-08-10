from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from cheap_flight_radar.provider_validation import OPEN_JAW_LEGS, ROUND_TRIP_BASKET

API_URL = "https://www.searchapi.io/api/v1/search"
MAX_REQUESTS = 60
OUTBOUND_TOKENS_PER_CASE = 2
OUTPUT = Path("research-output/searchapi-google-flights-summary.json")

# Sanitized carrier-code evidence derived from FlyAI formal-key artifact 9067758804.
# This is used only for carrier-set overlap; FlyAI raw prices are intentionally not compared.
FLYAI_FORMAL_CARRIER_CODES = {
    "J1": {"GK", "LJ", "MM", "SL", "TR"},
    "J2": {"FM", "JL", "MU", "NH"},
    "J3": {"NX"},
    "J4": {"7C", "BR", "CI", "IT", "JL", "OZ", "VN"},
    "K1": {"7C", "HX", "IT", "KE", "LJ", "OZ", "TR", "ZE"},
    "K2": {"7C", "9C", "CI", "CX", "H1", "KE", "OZ", "TW", "VN"},
    "C1": {"AE", "CA", "CI", "FM", "MF", "MU"},
    "C2": {"9C", "CX", "HX", "MF", "NX"},
    "S1": {"BR", "CI", "CX", "JX", "VJ", "VN"},
    "L1": {"BR", "KE", "OZ"},
}

REQUESTS_USED = 0
API_KEY = os.environ.get("SEARCHAPI_API_KEY", "")


def write_output(payload: Mapping[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_search(params: Mapping[str, Any]) -> dict[str, Any]:
    global REQUESTS_USED
    if not API_KEY:
        raise RuntimeError("SEARCHAPI_API_KEY is not available")
    if REQUESTS_USED >= MAX_REQUESTS:
        raise RuntimeError(f"request budget exceeded ({MAX_REQUESTS})")

    clean_params = {k: v for k, v in params.items() if v is not None}
    url = f"{API_URL}?{urlencode(clean_params)}"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
            "User-Agent": "cheap-flight-radar-issue-2-research/0.1",
        },
    )
    REQUESTS_USED += 1
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"SearchAPI HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"SearchAPI network error: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SearchAPI returned non-JSON response") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("SearchAPI JSON root is not an object")
    if payload.get("error"):
        raise RuntimeError(f"SearchAPI error: {payload.get('error')}")
    return payload


def base_params(case: Any) -> dict[str, Any]:
    return {
        "engine": "google_flights",
        "flight_type": "round_trip",
        "departure_id": case.origin,
        "arrival_id": case.destination,
        "outbound_date": case.outbound_date,
        "return_date": case.return_date,
        "travel_class": "economy",
        "adults": 1,
        "currency": "TWD",
        "gl": "tw",
        "hl": "en",
        "stops": "any",
        "sort_by": "price",
        "show_cheapest_flights": "true",
        "show_hidden_flights": "true",
        "expanded_search": "true",
        "separate_tickets": 0,
    }


def flight_items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("best_flights", "other_flights"):
        values = payload.get(key) or []
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            fingerprint = json.dumps(
                [
                    item.get("price"),
                    [f.get("flight_number") for f in item.get("flights") or [] if isinstance(f, dict)],
                    bool(item.get("departure_token")),
                    bool(item.get("booking_token")),
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
            if fingerprint not in seen:
                seen.add(fingerprint)
                result.append(item)
    return result


def numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def endpoint_date(item: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    flights = [f for f in item.get("flights") or [] if isinstance(f, Mapping)]
    if not flights:
        return None, None, None
    dep = flights[0].get("departure_airport") or {}
    arr = flights[-1].get("arrival_airport") or {}
    return dep.get("id"), arr.get("id"), dep.get("date")


def exact_leg(item: Mapping[str, Any], origin: str, destination: str, date: str) -> bool:
    dep, arr, dep_date = endpoint_date(item)
    return dep == origin and arr == destination and dep_date == date


def flight_number_code(value: Any) -> str | None:
    if not value:
        return None
    match = re.match(r"^\s*([A-Z0-9]{2})\s*\d", str(value).upper())
    return match.group(1) if match else None


def carrier_codes(items: Iterable[Mapping[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for item in items:
        for flight in item.get("flights") or []:
            if not isinstance(flight, Mapping):
                continue
            code = flight_number_code(flight.get("flight_number"))
            if code:
                codes.add(code)
    return codes


def sanitize_leg(item: Mapping[str, Any]) -> dict[str, Any]:
    flights_out = []
    for flight in item.get("flights") or []:
        if not isinstance(flight, Mapping):
            continue
        dep = flight.get("departure_airport") or {}
        arr = flight.get("arrival_airport") or {}
        flights_out.append(
            {
                "origin": dep.get("id"),
                "destination": arr.get("id"),
                "departure_date": dep.get("date"),
                "departure_time": dep.get("time"),
                "arrival_date": arr.get("date"),
                "arrival_time": arr.get("time"),
                "airline": flight.get("airline"),
                "flight_number": flight.get("flight_number"),
                "travel_class": flight.get("travel_class"),
            }
        )
    return {
        "price": item.get("price"),
        "type": item.get("type"),
        "flights": flights_out,
        "layovers": [
            {"id": x.get("id"), "name": x.get("name"), "duration": x.get("duration")}
            for x in (item.get("layovers") or [])
            if isinstance(x, Mapping)
        ],
        "extensions": list(item.get("extensions") or []),
        "has_departure_token": bool(item.get("departure_token")),
        "has_booking_token": bool(item.get("booking_token")),
    }


def selected_journeys(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    journeys = []
    for item in payload.get("selected_flights") or []:
        if isinstance(item, Mapping):
            journeys.append(sanitize_leg(item))
    return journeys


def selected_exact_round_trip(payload: Mapping[str, Any], case: Any) -> bool:
    journeys = selected_journeys(payload)
    if len(journeys) < 2:
        return False
    out = {"flights": journeys[0].get("flights") or []}
    back = {"flights": journeys[1].get("flights") or []}

    def exact_sanitized(item: Mapping[str, Any], origin: str, destination: str, date: str) -> bool:
        flights = item.get("flights") or []
        if not flights:
            return False
        return (
            flights[0].get("origin") == origin
            and flights[-1].get("destination") == destination
            and flights[0].get("departure_date") == date
        )

    return exact_sanitized(out, case.origin, case.destination, case.outbound_date) and exact_sanitized(
        back, case.destination, case.origin, case.return_date
    )


def selected_exact_open_jaw(payload: Mapping[str, Any]) -> bool:
    journeys = selected_journeys(payload)
    if len(journeys) < 2:
        return False
    expected = OPEN_JAW_LEGS
    for journey, case in zip(journeys[:2], expected):
        flights = journey.get("flights") or []
        if not flights:
            return False
        if not (
            flights[0].get("origin") == case.origin
            and flights[-1].get("destination") == case.destination
            and flights[0].get("departure_date") == case.outbound_date
        ):
            return False
    return True


def sanitize_booking_options(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    sanitized = []
    for option in payload.get("booking_options") or []:
        if not isinstance(option, Mapping):
            continue
        entry = {
            "book_with": option.get("book_with"),
            "flight_numbers": list(option.get("flight_numbers") or []),
            "fare_type": option.get("fare_type"),
            "option_title": option.get("option_title"),
            "price": option.get("price"),
            "is_split_booking": bool(option.get("is_split_booking")),
            "baggage_prices": list(option.get("baggage_prices") or []),
            "local_prices": list(option.get("local_prices") or []),
        }
        for direction in ("departure", "arrival"):
            part = option.get(direction)
            if isinstance(part, Mapping):
                entry[direction] = {
                    "book_with": part.get("book_with"),
                    "flight_numbers": list(part.get("flight_numbers") or []),
                    "price": part.get("price"),
                    "local_prices": list(part.get("local_prices") or []),
                    "baggage_prices": list(part.get("baggage_prices") or []),
                }
        sanitized.append(entry)
    return sanitized


def booking_identity(option: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        option.get("book_with"),
        tuple(option.get("flight_numbers") or []),
        option.get("fare_type"),
        option.get("option_title"),
        bool(option.get("is_split_booking")),
    )


def lowest_booking(options: list[dict[str, Any]]) -> dict[str, Any] | None:
    numeric_options = [(numeric(o.get("price")), o) for o in options]
    numeric_options = [(p, o) for p, o in numeric_options if p is not None]
    return min(numeric_options, key=lambda pair: pair[0])[1] if numeric_options else (options[0] if options else None)


def compare_booking_revalidation(first: Mapping[str, Any], second: Mapping[str, Any], exact_selected: bool) -> dict[str, Any]:
    first_options = sanitize_booking_options(first)
    second_options = sanitize_booking_options(second)
    selected = lowest_booking(first_options)
    if selected is None:
        return {
            "method": "same_booking_token_booking_options",
            "attempted": True,
            "revalidation_success": False,
            "same_lowest_option": None,
            "same_price": None,
            "stale": True,
        }
    selected_id = booking_identity(selected)
    matched = next((o for o in second_options if booking_identity(o) == selected_id), None)
    success = bool(exact_selected and second_options)
    same_option = matched is not None
    same_price = bool(matched and matched.get("price") == selected.get("price"))
    return {
        "method": "same_booking_token_booking_options",
        "attempted": True,
        "revalidation_success": success,
        "same_lowest_option": same_option,
        "same_price": same_price,
        "first_lowest_price": selected.get("price"),
        "second_matching_price": matched.get("price") if matched else None,
        "stale": (not success) or (not same_option) or (not same_price),
        "scope_note": "Booking-option layer revalidation via the same SearchAPI booking_token; not airline/OTA checkout completion.",
    }


def choose_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return min(candidates, key=lambda x: (numeric(x.get("price")) is None, numeric(x.get("price")) or float("inf")))


def run_round_trip(case: Any, initial_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    params = base_params(case)
    initial = dict(initial_payload) if initial_payload is not None else api_search(params)
    initial_items = flight_items(initial)
    exact_outbound = [i for i in initial_items if exact_leg(i, case.origin, case.destination, case.outbound_date)]
    exact_outbound.sort(key=lambda i: (numeric(i.get("price")) is None, numeric(i.get("price")) or float("inf")))
    tokenized = [i for i in exact_outbound if i.get("departure_token")][:OUTBOUND_TOKENS_PER_CASE]

    full_candidates: list[dict[str, Any]] = []
    return_probe_summaries = []
    reference_return_codes: set[str] = set()
    for outbound in tokenized:
        ret_payload = api_search({**params, "departure_token": outbound.get("departure_token")})
        ret_items = flight_items(ret_payload)
        exact_returns = [i for i in ret_items if exact_leg(i, case.destination, case.origin, case.return_date)]
        reference_return_codes.update(carrier_codes(exact_returns))
        return_probe_summaries.append(
            {
                "outbound": sanitize_leg(outbound),
                "returned_items": len(ret_items),
                "exact_return_items": len(exact_returns),
                "exact_return_carrier_codes": sorted(carrier_codes(exact_returns)),
            }
        )
        for ret in exact_returns:
            if ret.get("booking_token"):
                full_candidates.append(
                    {
                        "price": ret.get("price") if ret.get("price") is not None else outbound.get("price"),
                        "outbound": outbound,
                        "return": ret,
                        "booking_token": ret.get("booking_token"),
                    }
                )

    chosen = choose_candidate(full_candidates)
    booking_first: dict[str, Any] = {}
    booking_second: dict[str, Any] = {}
    first_exact = False
    second_exact = False
    booking_options: list[dict[str, Any]] = []
    revalidation: dict[str, Any] | None = None
    if chosen:
        booking_params = {**params, "booking_token": chosen["booking_token"]}
        booking_first = api_search(booking_params)
        booking_second = api_search(booking_params)
        first_exact = selected_exact_round_trip(booking_first, case)
        second_exact = selected_exact_round_trip(booking_second, case)
        booking_options = sanitize_booking_options(booking_first)
        revalidation = compare_booking_revalidation(booking_first, booking_second, second_exact)

    flyai_codes = FLYAI_FORMAL_CARRIER_CODES.get(case.case_id, set())
    reference_outbound_codes = carrier_codes(exact_outbound)
    reference_codes = reference_outbound_codes | reference_return_codes
    carrier_misses = reference_codes - flyai_codes
    carrier_overlap = reference_codes & flyai_codes
    lowest = lowest_booking(booking_options)
    search_price = numeric(chosen.get("price")) if chosen else None
    booking_price = numeric(lowest.get("price")) if lowest else None

    return {
        "case": asdict(case),
        "initial_result_keys": sorted(k for k in initial.keys() if k not in {"best_flights", "other_flights"}),
        "initial_returned_items": len(initial_items),
        "exact_outbound_items": len(exact_outbound),
        "exact_outbound_carrier_codes": sorted(reference_outbound_codes),
        "tested_outbound_tokens": len(tokenized),
        "return_probes": return_probe_summaries,
        "full_exact_candidates_with_booking_token": len(full_candidates),
        "selected_search_price_twd": chosen.get("price") if chosen else None,
        "selected_search_outbound": sanitize_leg(chosen["outbound"]) if chosen else None,
        "selected_search_return": sanitize_leg(chosen["return"]) if chosen else None,
        "booking_selected_exact_first": first_exact,
        "booking_selected_exact_second": second_exact,
        "booking_option_count": len(booking_options),
        "lowest_booking_option": lowest,
        "search_to_booking_price_gap_twd": (booking_price - search_price) if booking_price is not None and search_price is not None else None,
        "search_to_booking_price_gap_fraction": ((booking_price - search_price) / booking_price) if booking_price not in (None, 0) and search_price is not None else None,
        "booking_revalidation": revalidation,
        "reference_carrier_codes_sampled": sorted(reference_codes),
        "flyai_formal_carrier_codes": sorted(flyai_codes),
        "carrier_code_overlap": sorted(carrier_overlap),
        "carrier_code_reference_misses_in_flyai": sorted(carrier_misses),
        "price_comparison_to_flyai": None,
        "price_comparison_limitation": "FlyAI ticketPrice has no verified currency/tax/baggage semantics, so SearchAPI TWD prices are not numerically compared with it.",
    }


def open_jaw_params() -> dict[str, Any]:
    legs = [
        {"departure_id": case.origin, "arrival_id": case.destination, "outbound_date": case.outbound_date}
        for case in OPEN_JAW_LEGS
    ]
    return {
        "engine": "google_flights",
        "flight_type": "multi_city",
        "multi_city_json": json.dumps(legs, separators=(",", ":")),
        "travel_class": "economy",
        "adults": 1,
        "currency": "TWD",
        "gl": "tw",
        "hl": "en",
        "stops": "any",
        "sort_by": "price",
        "show_cheapest_flights": "true",
        "show_hidden_flights": "true",
        "expanded_search": "true",
        "separate_tickets": 0,
    }


def run_open_jaw() -> dict[str, Any]:
    params = open_jaw_params()
    initial = api_search(params)
    first_case, second_case = OPEN_JAW_LEGS
    initial_items = flight_items(initial)
    exact_first = [i for i in initial_items if exact_leg(i, first_case.origin, first_case.destination, first_case.outbound_date)]
    exact_first.sort(key=lambda i: (numeric(i.get("price")) is None, numeric(i.get("price")) or float("inf")))
    tokenized = [i for i in exact_first if i.get("departure_token")][:OUTBOUND_TOKENS_PER_CASE]

    candidates = []
    second_probes = []
    for first_leg in tokenized:
        second_payload = api_search({**params, "departure_token": first_leg.get("departure_token")})
        second_items = flight_items(second_payload)
        exact_second = [i for i in second_items if exact_leg(i, second_case.origin, second_case.destination, second_case.outbound_date)]
        second_probes.append(
            {
                "first_leg": sanitize_leg(first_leg),
                "returned_items": len(second_items),
                "exact_second_leg_items": len(exact_second),
            }
        )
        for second_leg in exact_second:
            if second_leg.get("booking_token"):
                candidates.append(
                    {
                        "price": second_leg.get("price") if second_leg.get("price") is not None else first_leg.get("price"),
                        "first": first_leg,
                        "second": second_leg,
                        "booking_token": second_leg.get("booking_token"),
                    }
                )

    chosen = choose_candidate(candidates)
    first_payload = {}
    second_payload = {}
    first_exact_selected = False
    second_exact_selected = False
    options = []
    revalidation = None
    if chosen:
        booking_params = {**params, "booking_token": chosen["booking_token"]}
        first_payload = api_search(booking_params)
        second_payload = api_search(booking_params)
        first_exact_selected = selected_exact_open_jaw(first_payload)
        second_exact_selected = selected_exact_open_jaw(second_payload)
        options = sanitize_booking_options(first_payload)
        revalidation = compare_booking_revalidation(first_payload, second_payload, second_exact_selected)

    lowest = lowest_booking(options)
    return {
        "case_id": "J5",
        "flight_type": "multi_city",
        "legs": [asdict(c) for c in OPEN_JAW_LEGS],
        "initial_returned_items": len(initial_items),
        "exact_first_leg_items": len(exact_first),
        "tested_first_leg_tokens": len(tokenized),
        "second_leg_probes": second_probes,
        "full_exact_candidates_with_booking_token": len(candidates),
        "selected_search_price_twd": chosen.get("price") if chosen else None,
        "booking_selected_exact_first": first_exact_selected,
        "booking_selected_exact_second": second_exact_selected,
        "booking_option_count": len(options),
        "lowest_booking_option": lowest,
        "booking_revalidation": revalidation,
        "structured_open_jaw_supported": bool(chosen and first_exact_selected),
    }


def main() -> int:
    started_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    result: dict[str, Any] = {
        "provider": "SearchAPI.io Google Flights API",
        "purpose": "Issue #2 independent benchmark / booking-option revalidation reference",
        "credential_mode": "SEARCHAPI_API_KEY via Authorization Bearer",
        "currency_requested": "TWD",
        "observed_at_asia_taipei": started_at,
        "request_budget_max": MAX_REQUESTS,
        "outbound_tokens_per_case": OUTBOUND_TOKENS_PER_CASE,
        "round_trip_cases": {},
        "open_jaw": None,
        "aggregate": {},
        "error": None,
    }
    try:
        # Schema guard: use the first basket request once, then reuse it.
        first_case = ROUND_TRIP_BASKET[0]
        first_payload = api_search(base_params(first_case))
        if not any(key in first_payload for key in ("best_flights", "other_flights")):
            result["schema_guard"] = {
                "ok": False,
                "top_level_keys": sorted(first_payload.keys()),
                "note": "Stopped after one request because expected flight-result arrays were absent.",
            }
            raise RuntimeError("SearchAPI schema guard failed")
        result["schema_guard"] = {"ok": True, "top_level_keys": sorted(first_payload.keys())}

        for index, case in enumerate(ROUND_TRIP_BASKET):
            payload = first_payload if index == 0 else None
            result["round_trip_cases"][case.case_id] = run_round_trip(case, payload)

        result["open_jaw"] = run_open_jaw()

        cases = list(result["round_trip_cases"].values())
        booking_attempts = [c for c in cases if c.get("full_exact_candidates_with_booking_token")]
        booking_success = [c for c in booking_attempts if c.get("booking_selected_exact_first") and c.get("booking_option_count", 0) > 0]
        revals = [c.get("booking_revalidation") for c in booking_attempts if c.get("booking_revalidation")]
        reval_success = sum(bool(x.get("revalidation_success")) for x in revals)
        stale = sum(bool(x.get("stale")) for x in revals)
        reference_codes = set().union(*(set(c.get("reference_carrier_codes_sampled") or []) for c in cases)) if cases else set()
        misses = set().union(*(set(c.get("carrier_code_reference_misses_in_flyai") or []) for c in cases)) if cases else set()

        result["aggregate"] = {
            "round_trip_cases_attempted": len(cases),
            "round_trip_cases_with_exact_outbound": sum(bool(c.get("exact_outbound_items")) for c in cases),
            "round_trip_cases_with_full_exact_candidate": sum(bool(c.get("full_exact_candidates_with_booking_token")) for c in cases),
            "round_trip_cases_with_booking_options": len(booking_success),
            "lowest_search_candidate_booking_option_hit_rate": len(booking_success) / len(booking_attempts) if booking_attempts else None,
            "booking_option_revalidation_attempts": len(revals),
            "booking_option_revalidation_successes": reval_success,
            "booking_option_revalidation_success_rate": reval_success / len(revals) if revals else None,
            "booking_option_stale_count": stale,
            "booking_option_stale_rate": stale / len(revals) if revals else None,
            "reference_carrier_codes_sampled": sorted(reference_codes),
            "reference_carrier_code_misses_in_flyai": sorted(misses),
            "lcc_miss_rate": None,
            "lcc_miss_rate_note": "Carrier-code differences are recorded. LCC classification is applied after observing the reference set so unknown carrier business models are not guessed.",
            "cross_source_price_gap": None,
            "cross_source_price_gap_note": "FlyAI ticketPrice semantics remain unknown, so numeric cross-source price gaps are not computed.",
            "j5_structured_open_jaw_supported": bool((result.get("open_jaw") or {}).get("structured_open_jaw_supported")),
        }
    except Exception as exc:
        result["error"] = str(exc)
        result["requests_used"] = REQUESTS_USED
        write_output(result)
        print(json.dumps({"error": result["error"], "requests_used": REQUESTS_USED}, ensure_ascii=False))
        return 1

    result["requests_used"] = REQUESTS_USED
    write_output(result)
    print(json.dumps({"aggregate": result["aggregate"], "requests_used": REQUESTS_USED}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
