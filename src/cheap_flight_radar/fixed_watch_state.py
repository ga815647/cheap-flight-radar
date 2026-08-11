"""Read persisted fixed-watch manifests for the ChatGPT radar orchestrator."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .public_intelligence import (
    DiscoverySighting,
    FixedWatch,
    FixedWatchAttempt,
    FixedWatchPlanEntry,
    FixedWatchRunManifest,
    load_fixed_watch_registry,
    plan_fixed_watches,
    utc_now,
)


MANIFEST_SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """Raised when a persisted fixed-watch manifest is malformed or inconsistent."""


@dataclass(frozen=True)
class ReusedFixedWatchSuccess:
    source_id: str
    attempt_id: str
    completed_at: datetime
    run_id: str
    observation_count: int


@dataclass(frozen=True)
class FixedWatchArtifactState:
    planned_at: datetime
    plan: tuple[FixedWatchPlanEntry, ...]
    due_watch_ids: tuple[str, ...]
    reused_successes: tuple[ReusedFixedWatchSuccess, ...]
    normalized_observations: tuple[DiscoverySighting, ...]

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def load_fixed_watch_manifest(path: str | Path) -> FixedWatchRunManifest:
    """Load and validate one extracted ``fixed-watch-run.json`` artifact file.

    Manifests written before the reader existed did not carry an explicit schema
    version. They are treated as schema v1 because the v1 field contract is the
    format already emitted by the runner at the durable Issue #10 checkpoint.
    """

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read fixed-watch manifest {manifest_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ManifestError("fixed-watch manifest must contain a JSON object")
    return parse_fixed_watch_manifest(payload)


def parse_fixed_watch_manifest(payload: Mapping[str, Any]) -> FixedWatchRunManifest:
    version = payload.get("schema_version", MANIFEST_SCHEMA_VERSION)
    if version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(f"unsupported fixed-watch manifest schema_version: {version!r}")

    run_id = _required_text(payload, "run_id")
    requested_watch_ids = _text_tuple(payload.get("requested_watch_ids"), "requested_watch_ids")
    attempts_raw = payload.get("attempts")
    observations_raw = payload.get("observations")
    if not isinstance(attempts_raw, list):
        raise ManifestError("attempts must be a list")
    if not isinstance(observations_raw, list):
        raise ManifestError("observations must be a list")

    attempts = tuple(_parse_attempt(item) for item in attempts_raw)
    observations = tuple(_parse_observation(item) for item in observations_raw)
    manifest = FixedWatchRunManifest(
        run_id=run_id,
        requested_at=_parse_timestamp(payload.get("requested_at"), "requested_at"),
        completed_at=_parse_timestamp(payload.get("completed_at"), "completed_at"),
        requested_watch_ids=requested_watch_ids,
        attempts=attempts,
        observations=observations,
    )
    _validate_manifest_integrity(manifest)
    return manifest


def build_fixed_watch_artifact_state(
    watches: Sequence[FixedWatch],
    manifests: Sequence[FixedWatchRunManifest],
    now: datetime,
) -> FixedWatchArtifactState:
    """Resolve due watches and reusable observations from persisted manifests.

    Only the latest successful attempt selected by the cadence planner contributes
    observations to the current ChatGPT radar run. A newer failed attempt never
    refreshes the due clock and never resurrects an expired success.
    """

    attempts = tuple(attempt for manifest in manifests for attempt in manifest.attempts)
    plan = plan_fixed_watches(watches, attempts, now)

    attempt_locations: dict[str, tuple[FixedWatchRunManifest, FixedWatchAttempt]] = {}
    for manifest in manifests:
        for attempt in manifest.attempts:
            attempt_locations.setdefault(attempt.attempt_id, (manifest, attempt))

    reused: list[ReusedFixedWatchSuccess] = []
    observations: list[DiscoverySighting] = []
    due_watch_ids: list[str] = []
    for entry in plan:
        if entry.due:
            due_watch_ids.append(entry.source_id)
            continue
        attempt_id = entry.latest_success_attempt_id
        if attempt_id is None or attempt_id not in attempt_locations:
            raise ManifestError(
                f"fresh plan entry for {entry.source_id} does not resolve to a persisted attempt"
            )
        manifest, attempt = attempt_locations[attempt_id]
        source_observations = tuple(
            observation
            for observation in manifest.observations
            if observation.source_id == entry.source_id
        )
        if len(source_observations) != attempt.observation_count:
            raise ManifestError(
                f"{attempt.attempt_id}: observation_count={attempt.observation_count} "
                f"but manifest contains {len(source_observations)} source observations"
            )
        reused.append(
            ReusedFixedWatchSuccess(
                source_id=entry.source_id,
                attempt_id=attempt.attempt_id,
                completed_at=attempt.completed_at,
                run_id=manifest.run_id,
                observation_count=attempt.observation_count,
            )
        )
        observations.extend(source_observations)

    observations.sort(key=lambda item: (item.observed_at, item.observation_id))
    return FixedWatchArtifactState(
        planned_at=now,
        plan=plan,
        due_watch_ids=tuple(due_watch_ids),
        reused_successes=tuple(reused),
        normalized_observations=tuple(observations),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="extracted fixed-watch-run.json path; repeat for multiple prior artifacts",
    )
    parser.add_argument("--policy", default="flight-radar.yaml")
    parser.add_argument(
        "--now",
        help="timezone-aware ISO-8601 planning timestamp; defaults to current UTC",
    )
    parser.add_argument("--output", help="write state JSON here instead of stdout")
    args = parser.parse_args(argv)

    now = _parse_timestamp(args.now, "--now") if args.now else utc_now()
    watches = load_fixed_watch_registry(args.policy)
    manifests = tuple(load_fixed_watch_manifest(path) for path in args.manifest)
    state = build_fixed_watch_artifact_state(watches, manifests, now)
    text = json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def _parse_attempt(value: Any) -> FixedWatchAttempt:
    if not isinstance(value, Mapping):
        raise ManifestError("each attempt must be a JSON object")
    observation_count = value.get("observation_count", 0)
    if not isinstance(observation_count, int) or isinstance(observation_count, bool) or observation_count < 0:
        raise ManifestError("attempt observation_count must be a non-negative integer")
    http_status = value.get("http_status")
    if http_status is not None and (not isinstance(http_status, int) or isinstance(http_status, bool)):
        raise ManifestError("attempt http_status must be an integer or null")
    return FixedWatchAttempt(
        attempt_id=_required_text(value, "attempt_id"),
        source_id=_required_text(value, "source_id"),
        status=_required_text(value, "status"),
        started_at=_parse_timestamp(value.get("started_at"), "started_at"),
        completed_at=_parse_timestamp(value.get("completed_at"), "completed_at"),
        requested_url=_required_text(value, "requested_url"),
        final_url=_optional_text(value.get("final_url")),
        http_status=http_status,
        error=_optional_text(value.get("error")),
        observation_count=observation_count,
    )


def _parse_observation(value: Any) -> DiscoverySighting:
    if not isinstance(value, Mapping):
        raise ManifestError("each observation must be a JSON object")
    route_set_raw = value.get("route_set", [])
    if not isinstance(route_set_raw, list) or any(not isinstance(item, str) for item in route_set_raw):
        raise ManifestError("observation route_set must be a list of strings")
    return DiscoverySighting(
        observation_id=_required_text(value, "observation_id"),
        source_id=_required_text(value, "source_id"),
        source_url=_required_text(value, "source_url"),
        item_url=_required_text(value, "item_url"),
        observed_at=_parse_timestamp(value.get("observed_at"), "observed_at"),
        title=_required_text(value, "title"),
        carrier=_optional_text(value.get("carrier")),
        sale_period=_optional_text(value.get("sale_period")),
        travel_period=_optional_text(value.get("travel_period")),
        route_set=tuple(route_set_raw),
        promo_code=_optional_text(value.get("promo_code")),
        price_text=_optional_text(value.get("price_text")),
    )


def _validate_manifest_integrity(manifest: FixedWatchRunManifest) -> None:
    attempt_source_ids = tuple(attempt.source_id for attempt in manifest.attempts)
    if len(set(attempt_source_ids)) != len(attempt_source_ids):
        raise ManifestError("manifest contains more than one attempt for the same source")
    if set(attempt_source_ids) != set(manifest.requested_watch_ids):
        raise ManifestError("requested_watch_ids must match the manifest attempt source ids")
    if len(set(manifest.requested_watch_ids)) != len(manifest.requested_watch_ids):
        raise ManifestError("requested_watch_ids must not contain duplicates")

    observation_counts: dict[str, int] = {source_id: 0 for source_id in attempt_source_ids}
    for observation in manifest.observations:
        if observation.source_id not in observation_counts:
            raise ManifestError(
                f"observation {observation.observation_id} has no source attempt in the same manifest"
            )
        observation_counts[observation.source_id] += 1
    for attempt in manifest.attempts:
        actual = observation_counts[attempt.source_id]
        if actual != attempt.observation_count:
            raise ManifestError(
                f"{attempt.attempt_id}: observation_count={attempt.observation_count} "
                f"but manifest contains {actual} source observations"
            )
        if attempt.status != "success" and actual:
            raise ManifestError(f"{attempt.attempt_id}: failed attempt cannot contain observations")


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a timezone-aware ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ManifestError(f"{field} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManifestError(f"{field} must be timezone-aware")
    return parsed


def _required_text(mapping: Mapping[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError("optional text fields must be strings or null")
    return value


def _text_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ManifestError(f"{field} must be a non-empty list of strings")
    return tuple(item.strip() for item in value)


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


if __name__ == "__main__":
    raise SystemExit(main())
