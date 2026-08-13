"""Lead-time-aware fare history and live-floor primitives.

Policy thresholds come from ``flight-radar.yaml``.  This module keeps historical
observations separate from current live fare state and never synthesizes missing
history.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
import re
from statistics import median
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from .scoring import departure_lead_time_bucket


PROJECT_TIMEZONE = ZoneInfo("Asia/Taipei")
_AVAILABLE = "available"
_COMPLETE_TRIP = "usable_complete_trip"


@dataclass(frozen=True)
class FareObservation:
    observation_id: str
    radar_run_id: str
    observed_at: str
    origin: str
    destination: str
    departure_date: str
    trip_type: str
    normalized_twd_price: float | None
    fare_scope: str
    availability_state: str
    source_id: str
    source_url: str | None
    verification_state: str
    original_price: str | int | float | None = None
    original_currency: str | None = None
    related_observation_id: str | None = None


@dataclass(frozen=True)
class WindowStatistic:
    value: float | None
    sample_count: int


@dataclass(frozen=True)
class LiveFareFloors:
    near_term: FareObservation | None
    horizon_absolute: FareObservation | None


@dataclass(frozen=True)
class FareHistoryComparison:
    lead_time_bucket: str
    sample_count: int
    confidence: str
    moving_medians_twd: Mapping[int, WindowStatistic]
    selected_baseline_window_days: int | None
    selected_baseline_twd: float | None
    rolling_lows_twd: Mapping[int, WindowStatistic]
    all_time_low_twd: float | None
    historical_percentile: float | None
    percent_below_baseline: float | None
    distance_from_all_time_low_twd: float | None
    distance_from_all_time_low_percent: float | None
    anomaly_label: str | None


@dataclass(frozen=True)
class FareHistorySnapshot:
    schema_version: int
    radar_run_id: str
    run_at: str
    observations: tuple[FareObservation, ...]


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return parsed


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _local_date(value: datetime) -> date:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(PROJECT_TIMEZONE).date()


def _days_until_departure(observation: FareObservation) -> int:
    observed = _parse_datetime(observation.observed_at)
    return (_parse_date(observation.departure_date) - _local_date(observed)).days


def _price(observation: FareObservation) -> float | None:
    if observation.normalized_twd_price is None:
        return None
    value = float(observation.normalized_twd_price)
    if value <= 0:
        return None
    return value


def _price_sample_eligible(observation: FareObservation) -> bool:
    return (
        observation.availability_state == _AVAILABLE
        and observation.fare_scope == _COMPLETE_TRIP
        and bool(observation.origin)
        and bool(observation.destination)
        and _price(observation) is not None
    )


def current_live_floors(
    observations: Sequence[FareObservation],
    *,
    radar_run_id: str,
    run_at: datetime,
    horizon_days: int,
    near_term_days: int = 30,
) -> LiveFareFloors:
    """Return independent current-run near-term and full-horizon floors."""

    if horizon_days < 0 or near_term_days < 0:
        raise ValueError("floor horizons must be non-negative")
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("run_at must be timezone-aware")

    run_date = _local_date(run_at)
    eligible: list[tuple[FareObservation, int]] = []
    for observation in observations:
        if observation.radar_run_id != radar_run_id or not _price_sample_eligible(observation):
            continue
        days = (_parse_date(observation.departure_date) - run_date).days
        if 0 <= days <= horizon_days:
            eligible.append((observation, days))

    def choose(candidates: Sequence[tuple[FareObservation, int]]) -> FareObservation | None:
        if not candidates:
            return None
        return min(
            (item[0] for item in candidates),
            key=lambda item: (
                float(item.normalized_twd_price),
                item.departure_date,
                item.observation_id,
            ),
        )

    return LiveFareFloors(
        near_term=choose([item for item in eligible if item[1] <= near_term_days]),
        horizon_absolute=choose(eligible),
    )


def _confidence(sample_count: int, policy: Mapping[str, object]) -> str:
    levels_obj = policy["confidence"]["levels"]
    if not isinstance(levels_obj, Mapping):
        raise TypeError("price_history.confidence.levels must be a mapping")
    for name, bounds_obj in levels_obj.items():
        if not isinstance(bounds_obj, Mapping):
            raise TypeError("confidence level bounds must be a mapping")
        minimum = int(bounds_obj["min_samples"])
        maximum_obj = bounds_obj.get("max_samples")
        maximum = None if maximum_obj is None else int(maximum_obj)
        if sample_count >= minimum and (maximum is None or sample_count <= maximum):
            return str(name)
    raise ValueError("sample_count is outside configured confidence levels")


def _collapse_duplicate_run_samples(
    observations: Sequence[FareObservation],
) -> list[FareObservation]:
    """Keep one comparable destination-floor sample per radar run.

    Multiple Taiwan origins/source/query sightings in one run are provenance,
    not independent historical market samples.  The cheapest usable complete-trip
    observation is retained for that destination/trip-type/lead-time run.
    """

    by_run: dict[str, FareObservation] = {}
    for observation in observations:
        existing = by_run.get(observation.radar_run_id)
        if existing is None or float(observation.normalized_twd_price) < float(existing.normalized_twd_price):
            by_run[observation.radar_run_id] = observation
    return list(by_run.values())


def _comparable_history(
    current: FareObservation,
    history: Sequence[FareObservation],
    policy: Mapping[str, object],
) -> tuple[str, list[FareObservation]]:
    if not _price_sample_eligible(current):
        raise ValueError("current observation is not a usable available complete-trip price")

    current_time = _parse_datetime(current.observed_at)
    bucket = departure_lead_time_bucket(_days_until_departure(current), policy)
    configured_origins_obj = policy.get("comparison_origin_airports", ())
    if not isinstance(configured_origins_obj, Sequence) or isinstance(configured_origins_obj, (str, bytes)):
        raise TypeError("price_history.comparison_origin_airports must be a sequence")
    configured_origins = {str(item) for item in configured_origins_obj}
    if configured_origins and current.origin not in configured_origins:
        raise ValueError("current observation origin is outside configured comparison origins")

    comparable: list[FareObservation] = []
    for prior in history:
        if prior.observation_id == current.observation_id or not _price_sample_eligible(prior):
            continue
        prior_time = _parse_datetime(prior.observed_at)
        if prior_time >= current_time:
            continue
        if configured_origins and prior.origin not in configured_origins:
            continue
        if prior.destination != current.destination or prior.trip_type != current.trip_type:
            continue
        try:
            prior_bucket = departure_lead_time_bucket(_days_until_departure(prior), policy)
        except ValueError:
            continue
        if prior_bucket == bucket:
            comparable.append(prior)

    return bucket, _collapse_duplicate_run_samples(comparable)


def _window_values(
    history: Sequence[FareObservation],
    current_time: datetime,
    window_days: int,
) -> list[float]:
    threshold = current_time - timedelta(days=window_days)
    return [
        float(item.normalized_twd_price)
        for item in history
        if threshold <= _parse_datetime(item.observed_at) < current_time
    ]


def compare_with_history(
    current: FareObservation,
    history: Sequence[FareObservation],
    policy: Mapping[str, object],
) -> FareHistoryComparison:
    """Compare a current fare with prior destination-airport, lead-time-matched history."""

    bucket, comparable = _comparable_history(current, history, policy)
    current_time = _parse_datetime(current.observed_at)
    current_price = float(current.normalized_twd_price)
    sample_count = len(comparable)

    baseline_obj = policy["baseline"]
    if not isinstance(baseline_obj, Mapping):
        raise TypeError("price_history.baseline must be a mapping")
    minimum_baseline_samples = int(baseline_obj["minimum_samples_per_window"])
    moving_medians: dict[int, WindowStatistic] = {}
    for days_obj in baseline_obj["moving_windows_days"]:
        days = int(days_obj)
        values = _window_values(comparable, current_time, days)
        value = float(median(values)) if len(values) >= minimum_baseline_samples else None
        moving_medians[days] = WindowStatistic(value=value, sample_count=len(values))

    primary = int(baseline_obj["primary_recent_window_days"])
    selection_order = [primary] + [int(item) for item in baseline_obj["fallback_window_order_days"]]
    selected_window: int | None = None
    selected_baseline: float | None = None
    for days in selection_order:
        metric = moving_medians[days]
        if metric.value is not None:
            selected_window = days
            selected_baseline = metric.value
            break

    lows_obj = policy["rolling_lows"]
    if not isinstance(lows_obj, Mapping):
        raise TypeError("price_history.rolling_lows must be a mapping")
    rolling_lows: dict[int, WindowStatistic] = {}
    for days_obj in lows_obj["windows_days"]:
        days = int(days_obj)
        values = _window_values(comparable, current_time, days)
        rolling_lows[days] = WindowStatistic(
            value=min(values) if values else None,
            sample_count=len(values),
        )

    all_values = [float(item.normalized_twd_price) for item in comparable]
    all_time_low = min(all_values) if all_values else None

    percentile_obj = policy["percentile"]
    if not isinstance(percentile_obj, Mapping):
        raise TypeError("price_history.percentile must be a mapping")
    minimum_percentile_samples = int(percentile_obj["minimum_samples"])
    historical_percentile: float | None = None
    if sample_count >= minimum_percentile_samples:
        below = sum(1 for value in all_values if value < current_price)
        equal = sum(1 for value in all_values if value == current_price)
        historical_percentile = 100.0 * (below + 0.5 * equal) / sample_count

    percent_below = None
    if selected_baseline is not None:
        percent_below = 100.0 * (selected_baseline - current_price) / selected_baseline

    distance_amount = None
    distance_percent = None
    if all_time_low is not None:
        distance_amount = current_price - all_time_low
        distance_percent = 100.0 * distance_amount / all_time_low

    anomaly_label = None
    historical_floor_obj = policy["anomaly_labeling"]["historical_floor"]
    minimum_floor_samples = int(historical_floor_obj["minimum_samples"])
    if (
        all_time_low is not None
        and sample_count >= minimum_floor_samples
        and current_price <= all_time_low
    ):
        anomaly_label = "historical_floor"

    return FareHistoryComparison(
        lead_time_bucket=bucket,
        sample_count=sample_count,
        confidence=_confidence(sample_count, policy),
        moving_medians_twd=moving_medians,
        selected_baseline_window_days=selected_window,
        selected_baseline_twd=selected_baseline,
        rolling_lows_twd=rolling_lows,
        all_time_low_twd=all_time_low,
        historical_percentile=historical_percentile,
        percent_below_baseline=percent_below,
        distance_from_all_time_low_twd=distance_amount,
        distance_from_all_time_low_percent=distance_percent,
        anomaly_label=anomaly_label,
    )


def build_snapshot(
    radar_run_id: str,
    run_at: datetime,
    observations: Sequence[FareObservation],
) -> FareHistorySnapshot:
    if not radar_run_id:
        raise ValueError("radar_run_id must not be empty")
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("run_at must be timezone-aware")
    for observation in observations:
        if observation.radar_run_id != radar_run_id:
            raise ValueError("all snapshot observations must use the snapshot radar_run_id")
    return FareHistorySnapshot(
        schema_version=1,
        radar_run_id=radar_run_id,
        run_at=run_at.isoformat(),
        observations=tuple(observations),
    )


def snapshot_repository_path(snapshot: FareHistorySnapshot) -> str:
    run_at = _parse_datetime(snapshot.run_at).astimezone(PROJECT_TIMEZONE)
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", snapshot.radar_run_id).strip("-.")
    if not safe_id:
        raise ValueError("radar_run_id does not contain any path-safe characters")
    return (
        f"data/price-history/{run_at:%Y/%m/%d}/{safe_id}.json"
    )


def snapshot_to_json(snapshot: FareHistorySnapshot) -> str:
    payload = {
        "schema_version": snapshot.schema_version,
        "radar_run_id": snapshot.radar_run_id,
        "run_at": snapshot.run_at,
        "observations": [asdict(item) for item in snapshot.observations],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def snapshot_from_json(payload: str) -> FareHistorySnapshot:
    raw = json.loads(payload)
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported fare history snapshot schema_version")
    radar_run_id = str(raw["radar_run_id"])
    run_at = _parse_datetime(str(raw["run_at"]))
    observations = tuple(FareObservation(**item) for item in raw.get("observations", []))
    return build_snapshot(radar_run_id, run_at, observations)
