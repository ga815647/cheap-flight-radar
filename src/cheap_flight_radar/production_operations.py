"""Deterministic daily operational guardrails for canonical production Radar runs.

This module does not schedule work or acquire fares. It coordinates the
existing append-only repository refs so a caller can enforce one canonical live
acquisition attempt per Asia/Taipei day and recover publication without
re-querying providers.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence


CANONICAL_RUN_PREFIX = "production-radar-"


@dataclass(frozen=True)
class DailyOperationState:
    requested_date: str
    status: str
    claim_path: str
    radar_run_id: str | None = None
    history_snapshot_path: str | None = None
    recovery_manifest_path: str | None = None
    publication_manifest_path: str | None = None
    reason: str | None = None


def _day_parts(requested_date: str) -> tuple[str, str, str]:
    parsed = date.fromisoformat(requested_date)
    return f"{parsed.year:04d}", f"{parsed.month:02d}", f"{parsed.day:02d}"


def claim_repository_path(requested_date: str) -> str:
    year, month, day = _day_parts(requested_date)
    return f"data/production-attempts/{year}/{month}/{day}/canonical.json"


def run_evidence_repository_dir(requested_date: str, radar_run_id: str) -> str:
    year, month, day = _day_parts(requested_date)
    return f"data/run-evidence/{year}/{month}/{day}/{radar_run_id}"


def _history_snapshot_files(history_dir: Path, requested_date: str) -> list[Path]:
    year, month, day = _day_parts(requested_date)
    root = history_dir / "data" / "price-history" / year / month / day
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.glob(f"{CANONICAL_RUN_PREFIX}*.json")
        if path.is_file()
    )


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON object required: {path}")
    return payload


def inspect_daily_state(
    *,
    history_dir: Path,
    publication_dir: Path,
    requested_date: str,
) -> DailyOperationState:
    """Classify one local-day operation without causing side effects."""

    claim_rel = claim_repository_path(requested_date)
    claim_path = history_dir / claim_rel
    snapshots = _history_snapshot_files(history_dir, requested_date)

    if len(snapshots) > 1:
        return DailyOperationState(
            requested_date=requested_date,
            status="blocked_multiple_canonical_snapshots",
            claim_path=claim_rel,
            reason=(
                "more than one canonical production snapshot already exists for "
                "this local day; do not acquire or guess which run is canonical"
            ),
        )

    if not snapshots:
        if claim_path.exists():
            return DailyOperationState(
                requested_date=requested_date,
                status="blocked_prior_acquisition_attempt",
                claim_path=claim_rel,
                reason=(
                    "the daily acquisition claim exists but no canonical snapshot "
                    "was persisted; fail closed and do not query providers again"
                ),
            )
        return DailyOperationState(
            requested_date=requested_date,
            status="acquire",
            claim_path=claim_rel,
            reason="no daily claim or canonical snapshot exists",
        )

    snapshot_path = snapshots[0]
    snapshot = _read_json(snapshot_path)
    radar_run_id = str(snapshot.get("radar_run_id") or "")
    if not radar_run_id.startswith(CANONICAL_RUN_PREFIX):
        return DailyOperationState(
            requested_date=requested_date,
            status="blocked_invalid_snapshot_identity",
            claim_path=claim_rel,
            history_snapshot_path=snapshot_path.relative_to(history_dir).as_posix(),
            reason="canonical snapshot path does not contain a canonical radar_run_id",
        )

    evidence_dir = history_dir / run_evidence_repository_dir(requested_date, radar_run_id)
    recovery_manifest = evidence_dir / "publication-manifest.json"
    publication_manifest = publication_dir / "publication" / "runs" / f"{radar_run_id}.json"
    common = dict(
        requested_date=requested_date,
        claim_path=claim_rel,
        radar_run_id=radar_run_id,
        history_snapshot_path=snapshot_path.relative_to(history_dir).as_posix(),
        recovery_manifest_path=recovery_manifest.relative_to(history_dir).as_posix(),
        publication_manifest_path=publication_manifest.relative_to(publication_dir).as_posix(),
    )

    if publication_manifest.exists():
        if not recovery_manifest.exists():
            return DailyOperationState(
                status="blocked_missing_recovery_evidence",
                reason=(
                    "active publication manifest exists without immutable recovery evidence; "
                    "do not accept presentation state as durable recovery"
                ),
                **common,
            )
        if publication_manifest.read_bytes() != recovery_manifest.read_bytes():
            return DailyOperationState(
                status="blocked_manifest_divergence",
                reason="active publication manifest differs from immutable recovery evidence",
                **common,
            )
        return DailyOperationState(
            status="published",
            reason="canonical acquisition and active publication manifest already exist",
            **common,
        )
    if recovery_manifest.exists():
        return DailyOperationState(
            status="recover_publication",
            reason="canonical acquisition exists; republish immutable manifest without reacquisition",
            **common,
        )

    return DailyOperationState(
        status="blocked_missing_recovery_evidence",
        reason=(
            "canonical snapshot exists without immutable recovery manifest; "
            "do not reacquire or synthesize publication state"
        ),
        **common,
    )


def write_daily_claim(
    *,
    history_dir: Path,
    requested_date: str,
    claimed_at: str,
    workflow_run_id: str,
    workflow_run_url: str,
    trigger_sha: str,
) -> Path:
    """Create the immutable claim written immediately before live acquisition."""

    parsed_claimed_at = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
    if parsed_claimed_at.tzinfo is None or parsed_claimed_at.utcoffset() is None:
        raise ValueError("claimed_at must be timezone-aware")
    target = history_dir / claim_repository_path(requested_date)
    if target.exists():
        raise FileExistsError(f"daily acquisition claim already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "requested_date": requested_date,
        "claimed_at": claimed_at,
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_url": workflow_run_url,
        "trigger_sha": trigger_sha,
        "semantics": "one_canonical_live_acquisition_attempt_per_asia_taipei_day",
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def stage_success_evidence(
    *,
    output_dir: Path,
    history_dir: Path,
    requested_date: str,
) -> Mapping[str, str]:
    """Validate and stage successful runtime output into the durable evidence ref."""

    claim_path = history_dir / claim_repository_path(requested_date)
    if not claim_path.exists():
        raise FileNotFoundError("daily acquisition claim must exist before staging success")

    result_path = output_dir / "run-result.json"
    result = _read_json(result_path)
    radar_run_id = str(result.get("radar_run_id") or "")
    run_at_raw = str(result.get("run_at") or "")
    if not radar_run_id.startswith(CANONICAL_RUN_PREFIX):
        raise ValueError("runtime result is not a canonical production radar run")
    run_at = datetime.fromisoformat(run_at_raw.replace("Z", "+00:00"))
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("runtime run_at must be timezone-aware")
    if run_at.date().isoformat() != requested_date:
        raise ValueError(
            f"runtime local date {run_at.date().isoformat()} does not match request {requested_date}"
        )

    manifest_source = output_dir / "publication" / "runs" / f"{radar_run_id}.json"
    manifest = _read_json(manifest_source)
    if manifest.get("radar_run_id") != radar_run_id:
        raise ValueError("publication manifest radar_run_id mismatch")
    history_rel = str(manifest.get("history_snapshot_path") or "")
    if not history_rel:
        raise ValueError("publication manifest missing history_snapshot_path")
    snapshot_source = output_dir / "history" / history_rel
    snapshot = _read_json(snapshot_source)
    if snapshot.get("radar_run_id") != radar_run_id:
        raise ValueError("history snapshot radar_run_id mismatch")

    snapshot_target = history_dir / history_rel
    if snapshot_target.exists():
        raise FileExistsError(f"canonical history snapshot already exists: {snapshot_target}")
    snapshot_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(snapshot_source, snapshot_target)

    evidence_dir = history_dir / run_evidence_repository_dir(requested_date, radar_run_id)
    if evidence_dir.exists():
        raise FileExistsError(f"run recovery evidence already exists: {evidence_dir}")
    evidence_dir.mkdir(parents=True, exist_ok=False)
    recovery_result = evidence_dir / "run-result.json"
    recovery_manifest = evidence_dir / "publication-manifest.json"
    shutil.copyfile(result_path, recovery_result)
    shutil.copyfile(manifest_source, recovery_manifest)

    return {
        "radar_run_id": radar_run_id,
        "history_snapshot_path": snapshot_target.relative_to(history_dir).as_posix(),
        "run_result_path": recovery_result.relative_to(history_dir).as_posix(),
        "recovery_manifest_path": recovery_manifest.relative_to(history_dir).as_posix(),
    }


def restore_publication_manifest(
    *,
    history_dir: Path,
    publication_dir: Path,
    requested_date: str,
) -> Mapping[str, str]:
    """Stage the immutable recovery manifest onto the active publication ref."""

    state = inspect_daily_state(
        history_dir=history_dir,
        publication_dir=publication_dir,
        requested_date=requested_date,
    )
    if state.status == "published":
        return {
            "status": "already_published",
            "radar_run_id": state.radar_run_id or "",
            "publication_manifest_path": state.publication_manifest_path or "",
        }
    if state.status != "recover_publication":
        raise RuntimeError(f"publication cannot be recovered from state {state.status}: {state.reason}")

    assert state.recovery_manifest_path
    assert state.publication_manifest_path
    source = history_dir / state.recovery_manifest_path
    target = publication_dir / state.publication_manifest_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != source.read_bytes():
            raise ValueError("existing publication manifest diverges from recovery evidence")
        status = "already_published"
    else:
        shutil.copyfile(source, target)
        status = "staged"
    return {
        "status": status,
        "radar_run_id": state.radar_run_id or "",
        "publication_manifest_path": state.publication_manifest_path,
    }


def _write_json_output(payload: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical daily production Radar operational guardrails")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--history-dir", required=True)
    inspect_parser.add_argument("--publication-dir", required=True)
    inspect_parser.add_argument("--date", required=True)
    inspect_parser.add_argument("--output")

    claim_parser = sub.add_parser("claim")
    claim_parser.add_argument("--history-dir", required=True)
    claim_parser.add_argument("--date", required=True)
    claim_parser.add_argument("--claimed-at", required=True)
    claim_parser.add_argument("--workflow-run-id", required=True)
    claim_parser.add_argument("--workflow-run-url", required=True)
    claim_parser.add_argument("--trigger-sha", required=True)

    stage_parser = sub.add_parser("stage-success")
    stage_parser.add_argument("--output-dir", required=True)
    stage_parser.add_argument("--history-dir", required=True)
    stage_parser.add_argument("--date", required=True)
    stage_parser.add_argument("--output")

    restore_parser = sub.add_parser("restore-publication")
    restore_parser.add_argument("--history-dir", required=True)
    restore_parser.add_argument("--publication-dir", required=True)
    restore_parser.add_argument("--date", required=True)
    restore_parser.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        state = inspect_daily_state(
            history_dir=Path(args.history_dir),
            publication_dir=Path(args.publication_dir),
            requested_date=args.date,
        )
        _write_json_output(asdict(state), args.output)
        return 0
    if args.command == "claim":
        path = write_daily_claim(
            history_dir=Path(args.history_dir),
            requested_date=args.date,
            claimed_at=args.claimed_at,
            workflow_run_id=args.workflow_run_id,
            workflow_run_url=args.workflow_run_url,
            trigger_sha=args.trigger_sha,
        )
        _write_json_output({"claim_path": path.as_posix()}, None)
        return 0
    if args.command == "stage-success":
        payload = stage_success_evidence(
            output_dir=Path(args.output_dir),
            history_dir=Path(args.history_dir),
            requested_date=args.date,
        )
        _write_json_output(payload, args.output)
        return 0
    if args.command == "restore-publication":
        payload = restore_publication_manifest(
            history_dir=Path(args.history_dir),
            publication_dir=Path(args.publication_dir),
            requested_date=args.date,
        )
        _write_json_output(payload, args.output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
