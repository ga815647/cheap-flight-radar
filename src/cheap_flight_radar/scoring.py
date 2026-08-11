"""Explainable scoring primitives for Cheap Flight Radar.

The policy is supplied by the caller (normally loaded from ``flight-radar.yaml``).
This module intentionally does not fetch fares or redefine search policy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _return_band(one_way_hours: float, bands: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    if one_way_hours <= 0:
        raise ValueError("one_way_hours must be positive")
    if not bands:
        raise ValueError("return_windows must not be empty")

    for band in bands:
        maximum = band.get("max_one_way_hours")
        if maximum is None or one_way_hours <= float(maximum):
            return band
    raise ValueError("return_windows must end with an open-ended band")


def departure_lead_time_bucket(
    days_until_departure: int,
    price_history_policy: Mapping[str, object],
) -> str:
    """Return the configured departure lead-time bucket id.

    Historical fare comparisons should compare like with like. A fare departing
    next week should not be judged against a 90-day-ahead observation without
    retaining that lead-time distinction.
    """

    if days_until_departure < 0:
        raise ValueError("days_until_departure must be non-negative")

    buckets_obj = price_history_policy["departure_lead_time_buckets_days"]
    if not isinstance(buckets_obj, Sequence) or not buckets_obj:
        raise TypeError("departure_lead_time_buckets_days must be a non-empty sequence")

    for bucket in buckets_obj:
        if not isinstance(bucket, Mapping):
            raise TypeError("departure lead-time bucket must be a mapping")
        minimum = int(bucket["min_days"])
        maximum = int(bucket["max_days"])
        if minimum <= days_until_departure <= maximum:
            return str(bucket["id"])

    raise ValueError("days_until_departure is outside configured lead-time buckets")


def trip_length_fit(one_way_hours: float, nights: float, policy: Mapping[str, object]) -> float:
    """Return a 0..1 fit score for trip length versus route size.

    Below the minimum useful stay, the score drops sharply. From the minimum to
    the ideal lower bound it rises from 0.5 to 1.0. Stays in or above the ideal
    range receive full credit; extra days are not rewarded further.
    """

    if nights < 0:
        raise ValueError("nights must be non-negative")

    bands = policy["return_windows"]
    if not isinstance(bands, Sequence):
        raise TypeError("return_windows must be a sequence")
    band = _return_band(one_way_hours, bands)

    minimum = float(band["min_nights"])
    ideal = band["ideal_nights"]
    if not isinstance(ideal, Sequence) or len(ideal) != 2:
        raise ValueError("ideal_nights must contain [low, high]")
    ideal_low = float(ideal[0])

    if nights < minimum:
        return _clamp(0.5 * (nights / minimum)) if minimum else 1.0
    if nights < ideal_low:
        span = ideal_low - minimum
        if span <= 0:
            return 1.0
        return _clamp(0.5 + 0.5 * ((nights - minimum) / span))
    return 1.0


def transport_efficiency(
    efficient_transport_hours: float,
    actual_transport_hours: float,
    *,
    self_transfer_count: int = 0,
    self_transfer_multiplier: float = 0.85,
) -> float:
    """Return a 0..1 transport-efficiency score.

    ``efficient_transport_hours`` is the practical baseline for the itinerary;
    ``actual_transport_hours`` includes connections and positioning time.
    Self-transfers apply an additional multiplicative risk/friction penalty.
    """

    if efficient_transport_hours <= 0 or actual_transport_hours <= 0:
        raise ValueError("transport hours must be positive")
    if self_transfer_count < 0:
        raise ValueError("self_transfer_count must be non-negative")
    if not 0 < self_transfer_multiplier <= 1:
        raise ValueError("self_transfer_multiplier must be in (0, 1]")

    time_ratio = _clamp(efficient_transport_hours / actual_transport_hours)
    return time_ratio * (self_transfer_multiplier**self_transfer_count)


def composite_score(
    components: Mapping[str, float],
    ranking_policy: Mapping[str, object],
) -> float:
    """Return a 0..100 weighted score from normalized 0..1 components.

    Expected component names and weights come from
    ``ranking.primary_recommendation_components`` in the SSOT.
    """

    weights_obj = ranking_policy["primary_recommendation_components"]
    if not isinstance(weights_obj, Mapping):
        raise TypeError("primary_recommendation_components must be a mapping")

    weights = {str(name): float(weight) for name, weight in weights_obj.items()}
    missing = set(weights) - set(components)
    if missing:
        raise ValueError(f"missing score components: {sorted(missing)}")

    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("score weights must sum to a positive value")

    weighted = 0.0
    for name, weight in weights.items():
        value = float(components[name])
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"component {name!r} must be within 0..1")
        weighted += value * weight

    return 100.0 * weighted / total_weight
