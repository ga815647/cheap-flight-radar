from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


SEMANTIC_TOKENS = ("currency", "tax", "baggage", "fare")


@dataclass(frozen=True)
class BasketCase:
    case_id: str
    origin: str
    destination: str
    outbound_date: str
    return_date: str | None = None
    market: str | None = None

    @property
    def is_round_trip(self) -> bool:
        return self.return_date is not None


ROUND_TRIP_BASKET: tuple[BasketCase, ...] = (
    BasketCase("J1", "TPE", "NRT", "2026-10-13", "2026-10-17", "japan"),
    BasketCase("J2", "TSA", "HND", "2026-10-13", "2026-10-18", "japan"),
    BasketCase("J3", "RMQ", "KIX", "2026-10-13", "2026-10-17", "japan"),
    BasketCase("J4", "KHH", "FUK", "2026-10-13", "2026-10-17", "japan"),
    BasketCase("K1", "TPE", "ICN", "2026-10-13", "2026-10-17", "korea"),
    BasketCase("K2", "KHH", "PUS", "2026-10-13", "2026-10-17", "korea"),
    BasketCase("C1", "TSA", "SHA", "2026-10-13", "2026-10-17", "china"),
    BasketCase("C2", "TPE", "XMN", "2026-10-13", "2026-10-17", "china"),
    BasketCase("S1", "TPE", "SGN", "2026-10-13", "2026-10-17", "world"),
    BasketCase("L1", "TPE", "LAX", "2026-10-13", "2026-10-23", "world"),
)

OPEN_JAW_LEGS: tuple[BasketCase, ...] = (
    BasketCase("J5A", "TPE", "NRT", "2026-10-13", None, "japan"),
    BasketCase("J5B", "KIX", "TPE", "2026-10-18", None, "japan"),
)


def _segments(itinerary: Mapping[str, Any]) -> list[list[Mapping[str, Any]]]:
    journeys = itinerary.get("journeys") or []
    return [list(journey.get("segments") or []) for journey in journeys]


def exact_airport_date(itinerary: Mapping[str, Any], case: BasketCase) -> bool:
    journeys = _segments(itinerary)
    if not journeys or not journeys[0]:
        return False

    outbound = journeys[0]
    outbound_exact = (
        outbound[0].get("origin") == case.origin
        and outbound[-1].get("destination") == case.destination
        and str(outbound[0].get("departure") or "")[:10] == case.outbound_date
    )
    if not outbound_exact:
        return False

    if not case.is_round_trip:
        return True

    if len(journeys) < 2 or not journeys[1]:
        return False
    inbound = journeys[1]
    return (
        inbound[0].get("origin") == case.destination
        and inbound[-1].get("destination") == case.origin
        and str(inbound[0].get("departure") or "")[:10] == case.return_date
    )


def itinerary_signature(itinerary: Mapping[str, Any]) -> tuple[tuple[tuple[Any, ...], ...], ...]:
    return tuple(
        tuple(
            (
                segment.get("origin"),
                segment.get("destination"),
                segment.get("departure"),
                segment.get("marketing_flight_number"),
            )
            for segment in journey
        )
        for journey in _segments(itinerary)
    )


def raw_numeric_price(itinerary: Mapping[str, Any]) -> float | None:
    value = itinerary.get("raw_price")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def select_lowest_raw_numeric(
    itineraries: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    candidates = [(raw_numeric_price(item), item) for item in itineraries]
    numeric = [(price, item) for price, item in candidates if price is not None]
    if numeric:
        return min(numeric, key=lambda pair: pair[0])[1]

    candidates = list(candidates)
    return candidates[0][1] if candidates else None


def semantic_key_paths(
    value: Any,
    tokens: Sequence[str] = SEMANTIC_TOKENS,
    path: str = "",
) -> dict[str, set[str]]:
    found = {token: set() for token in tokens}

    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            for token in tokens:
                if token.lower() in lowered:
                    found[token].add(child_path)
            nested = semantic_key_paths(child, tokens=tokens, path=child_path)
            for token in tokens:
                found[token].update(nested[token])
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            nested = semantic_key_paths(child, tokens=tokens, path=child_path)
            for token in tokens:
                found[token].update(nested[token])

    return found


def summarize_snapshot(
    case: BasketCase,
    itineraries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    exact = [item for item in itineraries if exact_airport_date(item, case)]
    selected = select_lowest_raw_numeric(exact)
    total = len(itineraries)
    exact_count = len(exact)

    return {
        "case_id": case.case_id,
        "returned_items": total,
        "exact_items": exact_count,
        "has_exact_result": bool(exact),
        "airport_integrity_reject_items": total - exact_count,
        "airport_integrity_reject_rate": (
            (total - exact_count) / total if total else None
        ),
        "selected_raw_price": selected.get("raw_price") if selected else None,
        "selected_signature": itinerary_signature(selected) if selected else None,
    }


def compare_repeat_query(
    case: BasketCase,
    first_itineraries: Sequence[Mapping[str, Any]],
    repeat_itineraries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    first_exact = [item for item in first_itineraries if exact_airport_date(item, case)]
    repeat_exact = [item for item in repeat_itineraries if exact_airport_date(item, case)]
    selected = select_lowest_raw_numeric(first_exact)

    if selected is None:
        return {
            "method": "repeat_query_proxy",
            "selected_itinerary_attempted": False,
            "same_selected_itinerary": None,
            "same_raw_price": None,
            "true_revalidation_success": None,
            "staleness_rate": None,
        }

    selected_signature = itinerary_signature(selected)
    matched = next(
        (
            item
            for item in repeat_exact
            if itinerary_signature(item) == selected_signature
        ),
        None,
    )
    same_itinerary = matched is not None
    same_raw_price = (
        bool(matched)
        and matched.get("raw_price") == selected.get("raw_price")
    )

    return {
        "method": "repeat_query_proxy",
        "selected_itinerary_attempted": True,
        "same_selected_itinerary": same_itinerary,
        "same_raw_price": bool(same_raw_price),
        "first_raw_price": selected.get("raw_price"),
        "repeat_raw_price": matched.get("raw_price") if matched else None,
        "true_revalidation_success": None,
        "staleness_rate": None,
    }


def aggregate_snapshots(
    snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    attempted = len(snapshots)
    exact_cases = sum(bool(item.get("has_exact_result")) for item in snapshots)
    returned = sum(int(item.get("returned_items") or 0) for item in snapshots)
    exact_items = sum(int(item.get("exact_items") or 0) for item in snapshots)
    rejected = returned - exact_items

    return {
        "cases_attempted": attempted,
        "cases_with_exact_result": exact_cases,
        "exact_case_coverage": exact_cases / attempted if attempted else None,
        "returned_items": returned,
        "exact_items": exact_items,
        "exact_item_rate": exact_items / returned if returned else None,
        "airport_integrity_reject_items": rejected,
        "airport_integrity_reject_rate": rejected / returned if returned else None,
    }


def aggregate_repeat_proxies(
    repeats: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    attempted = [
        item for item in repeats if item.get("selected_itinerary_attempted")
    ]
    same_itinerary = sum(bool(item.get("same_selected_itinerary")) for item in attempted)
    same_price = sum(bool(item.get("same_raw_price")) for item in attempted)

    return {
        "method": "repeat_query_proxy",
        "selected_itinerary_attempts": len(attempted),
        "same_selected_itinerary": same_itinerary,
        "same_selected_itinerary_rate": (
            same_itinerary / len(attempted) if attempted else None
        ),
        "same_itinerary_and_raw_price": same_price,
        "same_itinerary_and_raw_price_rate": (
            same_price / len(attempted) if attempted else None
        ),
        "true_revalidation_success": None,
        "staleness_rate": None,
    }
