"""Public-intelligence registry, cadence, provenance, and dedupe primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import yaml


SUCCESS = "success"
ATTEMPT_STATUSES = {"success", "unavailable", "blocked", "fetch_failed", "parse_failed"}
ALLOWED_ACQUISITIONS = {"direct_http", "headless"}


class RegistryError(ValueError):
    """Raised when the public-intelligence SSOT registry is invalid."""


@dataclass(frozen=True)
class FixedWatch:
    id: str
    markets: tuple[str, ...]
    source_type: str
    acquisition: str
    entry_url: str
    cadence_hours: int
    coverage_claim: str
    content_filter: str | None = None


@dataclass(frozen=True)
class FixedWatchAttempt:
    attempt_id: str
    source_id: str
    status: str
    started_at: datetime
    completed_at: datetime
    requested_url: str
    final_url: str | None = None
    http_status: int | None = None
    error: str | None = None
    observation_count: int = 0

    def __post_init__(self) -> None:
        if self.status not in ATTEMPT_STATUSES:
            raise ValueError(f"unsupported fixed-watch attempt status: {self.status}")
        _require_aware(self.started_at)
        _require_aware(self.completed_at)


@dataclass(frozen=True)
class FixedWatchPlanEntry:
    source_id: str
    due: bool
    cadence_hours: int
    latest_success_attempt_id: str | None
    latest_success_completed_at: datetime | None
    reason: str


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


@dataclass(frozen=True)
class FixedWatchRunManifest:
    run_id: str
    requested_at: datetime
    completed_at: datetime
    requested_watch_ids: tuple[str, ...]
    attempts: tuple[FixedWatchAttempt, ...]
    observations: tuple[DiscoverySighting, ...]

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def load_policy(path: str | Path = "flight-radar.yaml") -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RegistryError("flight-radar.yaml must contain a mapping")
    return data


def validate_orchestration_policy(policy: Mapping[str, Any]) -> None:
    public = policy.get("public_intelligence") or {}
    orchestration = public.get("orchestration") or {}
    runtime = public.get("runtime") or {}
    coverage = public.get("coverage") or {}

    expected = {
        "primary_scheduler": "chatgpt_scheduled_radar_run",
        "github_actions_role": "on_demand_deterministic_execution_crawler_and_gate_backend",
        "cadence_semantics": "freshness_reuse_window_and_due_threshold_not_actions_schedule",
    }
    for key, value in expected.items():
        if orchestration.get(key) != value:
            raise RegistryError(f"public_intelligence.orchestration.{key} must be {value!r}")
    if orchestration.get("independent_github_cron") is not False:
        raise RegistryError("independent_github_cron must remain false")
    if runtime.get("selected") != "scrapy":
        raise RegistryError("selected fixed-watch runtime must be scrapy")
    if coverage.get("cadence_is_maximum_age_of_latest_successful_attempt_hours") is not True:
        raise RegistryError("cadence freshness semantics must be explicit")


def load_fixed_watch_registry(
    path: str | Path = "flight-radar.yaml",
) -> tuple[FixedWatch, ...]:
    policy = load_policy(path)
    validate_orchestration_policy(policy)
    rows = ((policy.get("public_intelligence") or {}).get("fixed_watch_registry") or [])
    if not isinstance(rows, list) or not rows:
        raise RegistryError("fixed_watch_registry must be a non-empty list")

    watches: list[FixedWatch] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise RegistryError("each fixed watch must be a mapping")
        source_id = str(row.get("id") or "").strip()
        if not source_id or source_id in seen:
            raise RegistryError(f"fixed watch id is missing or duplicated: {source_id!r}")
        seen.add(source_id)
        cadence = row.get("cadence_hours")
        if not isinstance(cadence, int) or isinstance(cadence, bool) or cadence <= 0:
            raise RegistryError(f"{source_id}: cadence_hours must be a positive integer")
        acquisition = str(row.get("acquisition") or "")
        if acquisition not in ALLOWED_ACQUISITIONS:
            raise RegistryError(f"{source_id}: unsupported acquisition {acquisition!r}")
        entry_url = str(row.get("entry_url") or "")
        parsed = urlparse(entry_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RegistryError(f"{source_id}: entry_url must be public HTTP(S)")
        markets = tuple(str(m) for m in (row.get("markets") or ()))
        if not markets:
            raise RegistryError(f"{source_id}: markets must not be empty")
        coverage_claim = str(row.get("coverage_claim") or "")
        if not coverage_claim:
            raise RegistryError(f"{source_id}: coverage_claim is required")
        watches.append(
            FixedWatch(
                id=source_id,
                markets=markets,
                source_type=str(row.get("source_type") or ""),
                acquisition=acquisition,
                entry_url=entry_url,
                cadence_hours=cadence,
                coverage_claim=coverage_claim,
                content_filter=(str(row["content_filter"]) if row.get("content_filter") else None),
            )
        )
    return tuple(watches)


def plan_fixed_watches(
    watches: Sequence[FixedWatch],
    attempt_history: Iterable[FixedWatchAttempt],
    now: datetime,
) -> tuple[FixedWatchPlanEntry, ...]:
    """Plan due watches from the latest *successful* attempt only.

    Failed attempts never refresh freshness. A watch becomes due when age is
    greater than or equal to ``cadence_hours``.
    """

    _require_aware(now)
    latest_success: dict[str, FixedWatchAttempt] = {}
    known_ids = {watch.id for watch in watches}
    for attempt in attempt_history:
        if attempt.source_id not in known_ids or attempt.status != SUCCESS:
            continue
        current = latest_success.get(attempt.source_id)
        if current is None or attempt.completed_at > current.completed_at:
            latest_success[attempt.source_id] = attempt

    result: list[FixedWatchPlanEntry] = []
    for watch in watches:
        success = latest_success.get(watch.id)
        if success is None:
            result.append(
                FixedWatchPlanEntry(
                    source_id=watch.id,
                    due=True,
                    cadence_hours=watch.cadence_hours,
                    latest_success_attempt_id=None,
                    latest_success_completed_at=None,
                    reason="no_successful_attempt",
                )
            )
            continue
        age = now - success.completed_at
        due = age >= timedelta(hours=watch.cadence_hours)
        result.append(
            FixedWatchPlanEntry(
                source_id=watch.id,
                due=due,
                cadence_hours=watch.cadence_hours,
                latest_success_attempt_id=success.attempt_id,
                latest_success_completed_at=success.completed_at,
                reason="cadence_expired" if due else "fresh_prior_success",
            )
        )
    return tuple(result)


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
    payload = {
        "carrier": required[0],
        "sale_period": required[1],
        "travel_period": required[2],
        "route_set": route_set,
        "promo_code": _clean_token(sighting.promo_code),
    }
    return "campaign:" + _stable_hash(payload)


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
    """Group resolved campaign sightings while preserving every provenance record."""

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
        source_ids = tuple(dict.fromkeys(item.source_id for item in ordered))
        candidates.append(
            DiscoveryCandidate(
                campaign_key=key,
                first_seen_at=ordered[0].observed_at,
                first_discovery_source_id=ordered[0].source_id,
                discovery_source_ids=source_ids,
                sightings=tuple(ordered),
            )
        )
    candidates.sort(key=lambda item: (item.first_seen_at, item.campaign_key))
    unresolved.sort(key=lambda item: (item.observed_at, item.observation_id))
    return tuple(candidates), tuple(unresolved)


def make_observation_id(source_id: str, item_url: str, title: str, observed_at: datetime) -> str:
    _require_aware(observed_at)
    return "obs:" + _stable_hash(
        {
            "source_id": source_id,
            "item_url": item_url,
            "title": title.strip(),
            "observed_at": observed_at.isoformat(),
        }
    )


def make_attempt_id(run_id: str, source_id: str, started_at: datetime) -> str:
    _require_aware(started_at)
    return "attempt:" + _stable_hash(
        {"run_id": run_id, "source_id": source_id, "started_at": started_at.isoformat()}
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
