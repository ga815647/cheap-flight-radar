"""Explicit operator-requested same-day Radar acquisition guardrails.

Routine automation remains canonical once per Asia/Taipei day. This module
provides a separate request-id namespace for an explicitly requested additional
live acquisition. A duplicate invocation of the same request id is recovery or
no-op only; a new live attempt requires a new explicit request id.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

PROJECT_TIMEZONE = ZoneInfo("Asia/Taipei")
OPERATOR_RUN_PREFIX = "operator-radar-"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class OperatorOperationState:
    requested_date: str
    request_id: str
    status: str
    claim_path: str
    radar_run_id: str | None = None
    history_snapshot_path: str | None = None
    recovery_manifest_path: str | None = None
    publication_manifest_path: str | None = None
    reason: str | None = None


def _validate_request_id(request_id: str) -> str:
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must be 1-64 path-safe characters")
    return request_id


def _day_parts(requested_date: str) -> tuple[str, str, str]:
    parsed = date.fromisoformat(requested_date)
    return f"{parsed.year:04d}", f"{parsed.month:02d}", f"{parsed.day:02d}"


def operator_claim_repository_path(requested_date: str, request_id: str) -> str:
    request_id = _validate_request_id(request_id)
    year, month, day = _day_parts(requested_date)
    return f"data/operator-attempts/{year}/{month}/{day}/{request_id}.json"


def operator_run_prefix(request_id: str) -> str:
    return f"{OPERATOR_RUN_PREFIX}{_validate_request_id(request_id)}-"


def run_evidence_repository_dir(requested_date: str, radar_run_id: str) -> str:
    year, month, day = _day_parts(requested_date)
    return f"data/run-evidence/{year}/{month}/{day}/{radar_run_id}"


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _snapshot_files(history_dir: Path, requested_date: str, request_id: str) -> list[Path]:
    year, month, day = _day_parts(requested_date)
    root = history_dir / "data" / "price-history" / year / month / day
    if not root.exists():
        return []
    prefix = operator_run_prefix(request_id)
    return sorted(path for path in root.glob(f"{prefix}*.json") if path.is_file())


def inspect_operator_state(*, history_dir: Path, publication_dir: Path, requested_date: str, request_id: str) -> OperatorOperationState:
    claim_rel = operator_claim_repository_path(requested_date, request_id)
    claim_path = history_dir / claim_rel
    snapshots = _snapshot_files(history_dir, requested_date, request_id)
    if len(snapshots) > 1:
        return OperatorOperationState(requested_date, request_id, "blocked_multiple_operator_snapshots", claim_rel, reason="more than one snapshot exists for one operator request id")
    if not snapshots:
        if claim_path.exists():
            return OperatorOperationState(requested_date, request_id, "blocked_prior_operator_attempt", claim_rel, reason="operator request claim exists without persisted success; same request id cannot reacquire")
        return OperatorOperationState(requested_date, request_id, "acquire", claim_rel, reason="new explicit operator request id")
    if not claim_path.exists():
        return OperatorOperationState(
            requested_date,
            request_id,
            "blocked_missing_operator_claim",
            claim_rel,
            history_snapshot_path=snapshots[0].relative_to(history_dir).as_posix(),
            reason="operator snapshot exists without its immutable pre-acquisition claim",
        )

    snapshot_path = snapshots[0]
    snapshot = _read_json(snapshot_path)
    radar_run_id = str(snapshot.get("radar_run_id") or "")
    if not radar_run_id.startswith(operator_run_prefix(request_id)):
        return OperatorOperationState(requested_date, request_id, "blocked_invalid_snapshot_identity", claim_rel, history_snapshot_path=snapshot_path.relative_to(history_dir).as_posix(), reason="operator snapshot run id does not match request id")

    evidence_dir = history_dir / run_evidence_repository_dir(requested_date, radar_run_id)
    recovery_manifest = evidence_dir / "publication-manifest.json"
    publication_manifest = publication_dir / "publication" / "runs" / f"{radar_run_id}.json"
    common = dict(
        requested_date=requested_date,
        request_id=request_id,
        claim_path=claim_rel,
        radar_run_id=radar_run_id,
        history_snapshot_path=snapshot_path.relative_to(history_dir).as_posix(),
        recovery_manifest_path=recovery_manifest.relative_to(history_dir).as_posix(),
        publication_manifest_path=publication_manifest.relative_to(publication_dir).as_posix(),
    )
    if publication_manifest.exists():
        if not recovery_manifest.exists():
            return OperatorOperationState(status="blocked_missing_recovery_evidence", reason="active operator publication exists without immutable recovery evidence", **common)
        if publication_manifest.read_bytes() != recovery_manifest.read_bytes():
            return OperatorOperationState(status="blocked_manifest_divergence", reason="active operator publication differs from immutable recovery evidence", **common)
        return OperatorOperationState(status="published", reason="operator acquisition and publication already exist", **common)
    if recovery_manifest.exists():
        return OperatorOperationState(status="recover_publication", reason="operator acquisition exists; republish without reacquisition", **common)
    return OperatorOperationState(status="blocked_missing_recovery_evidence", reason="operator snapshot exists without immutable recovery manifest", **common)


def write_operator_claim(*, history_dir: Path, requested_date: str, request_id: str, claimed_at: str, workflow_run_id: str, workflow_run_url: str, trigger_sha: str) -> Path:
    parsed_claimed_at = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
    if parsed_claimed_at.tzinfo is None or parsed_claimed_at.utcoffset() is None:
        raise ValueError("claimed_at must be timezone-aware")
    target = history_dir / operator_claim_repository_path(requested_date, request_id)
    if target.exists():
        raise FileExistsError(f"operator acquisition claim already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "mode": "operator_reacquisition",
        "requested_date": requested_date,
        "request_id": request_id,
        "claimed_at": claimed_at,
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_url": workflow_run_url,
        "trigger_sha": trigger_sha,
        "semantics": "explicit_operator_requested_live_reacquisition",
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def stage_operator_success_evidence(*, output_dir: Path, history_dir: Path, requested_date: str, request_id: str) -> Mapping[str, str]:
    claim_path = history_dir / operator_claim_repository_path(requested_date, request_id)
    if not claim_path.exists():
        raise FileNotFoundError("operator acquisition claim must exist before staging success")
    result_path = output_dir / "run-result.json"
    result = _read_json(result_path)
    radar_run_id = str(result.get("radar_run_id") or "")
    if not radar_run_id.startswith(operator_run_prefix(request_id)):
        raise ValueError("runtime result does not match operator request identity")
    if result.get("execution_mode") != "operator_requested_reacquisition":
        raise ValueError("operator runtime result missing explicit execution_mode")
    run_at = datetime.fromisoformat(str(result.get("run_at") or "").replace("Z", "+00:00"))
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("runtime run_at must be timezone-aware")
    if run_at.astimezone(PROJECT_TIMEZONE).date().isoformat() != requested_date:
        raise ValueError("operator runtime local date does not match request")

    manifest_source = output_dir / "publication" / "runs" / f"{radar_run_id}.json"
    manifest = _read_json(manifest_source)
    if manifest.get("radar_run_id") != radar_run_id:
        raise ValueError("publication manifest radar_run_id mismatch")
    if manifest.get("execution_mode") != "operator_requested_reacquisition":
        raise ValueError("operator publication manifest missing execution_mode")
    history_rel = str(manifest.get("history_snapshot_path") or "")
    if not history_rel:
        raise ValueError("publication manifest missing history_snapshot_path")
    snapshot_source = output_dir / "history" / history_rel
    snapshot = _read_json(snapshot_source)
    if snapshot.get("radar_run_id") != radar_run_id:
        raise ValueError("history snapshot radar_run_id mismatch")

    snapshot_target = history_dir / history_rel
    if snapshot_target.exists():
        raise FileExistsError(f"operator history snapshot already exists: {snapshot_target}")
    snapshot_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(snapshot_source, snapshot_target)
    evidence_dir = history_dir / run_evidence_repository_dir(requested_date, radar_run_id)
    if evidence_dir.exists():
        raise FileExistsError(f"operator run recovery evidence already exists: {evidence_dir}")
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


def restore_operator_publication_manifest(*, history_dir: Path, publication_dir: Path, requested_date: str, request_id: str) -> Mapping[str, str]:
    state = inspect_operator_state(history_dir=history_dir, publication_dir=publication_dir, requested_date=requested_date, request_id=request_id)
    if state.status == "published":
        return {"status": "already_published", "radar_run_id": state.radar_run_id or "", "publication_manifest_path": state.publication_manifest_path or ""}
    if state.status != "recover_publication":
        raise RuntimeError(f"operator publication cannot recover from state {state.status}: {state.reason}")
    assert state.recovery_manifest_path
    assert state.publication_manifest_path
    source = history_dir / state.recovery_manifest_path
    target = publication_dir / state.publication_manifest_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != source.read_bytes():
            raise ValueError("existing operator publication diverges from recovery evidence")
        status = "already_published"
    else:
        shutil.copyfile(source, target)
        status = "staged"
    return {"status": status, "radar_run_id": state.radar_run_id or "", "publication_manifest_path": state.publication_manifest_path}


def _write_json_output(payload: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit operator Radar acquisition guardrails")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--history-dir", required=True)
    inspect_parser.add_argument("--publication-dir", required=True)
    inspect_parser.add_argument("--date", required=True)
    inspect_parser.add_argument("--request-id", required=True)
    inspect_parser.add_argument("--output")
    claim_parser = sub.add_parser("claim")
    claim_parser.add_argument("--history-dir", required=True)
    claim_parser.add_argument("--date", required=True)
    claim_parser.add_argument("--request-id", required=True)
    claim_parser.add_argument("--claimed-at", required=True)
    claim_parser.add_argument("--workflow-run-id", required=True)
    claim_parser.add_argument("--workflow-run-url", required=True)
    claim_parser.add_argument("--trigger-sha", required=True)
    stage_parser = sub.add_parser("stage-success")
    stage_parser.add_argument("--output-dir", required=True)
    stage_parser.add_argument("--history-dir", required=True)
    stage_parser.add_argument("--date", required=True)
    stage_parser.add_argument("--request-id", required=True)
    stage_parser.add_argument("--output")
    restore_parser = sub.add_parser("restore-publication")
    restore_parser.add_argument("--history-dir", required=True)
    restore_parser.add_argument("--publication-dir", required=True)
    restore_parser.add_argument("--date", required=True)
    restore_parser.add_argument("--request-id", required=True)
    restore_parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.command == "inspect":
        state = inspect_operator_state(history_dir=Path(args.history_dir), publication_dir=Path(args.publication_dir), requested_date=args.date, request_id=args.request_id)
        _write_json_output(asdict(state), args.output)
        return 0
    if args.command == "claim":
        path = write_operator_claim(history_dir=Path(args.history_dir), requested_date=args.date, request_id=args.request_id, claimed_at=args.claimed_at, workflow_run_id=args.workflow_run_id, workflow_run_url=args.workflow_run_url, trigger_sha=args.trigger_sha)
        _write_json_output({"claim_path": path.as_posix()}, None)
        return 0
    if args.command == "stage-success":
        payload = stage_operator_success_evidence(output_dir=Path(args.output_dir), history_dir=Path(args.history_dir), requested_date=args.date, request_id=args.request_id)
        _write_json_output(payload, args.output)
        return 0
    if args.command == "restore-publication":
        payload = restore_operator_publication_manifest(history_dir=Path(args.history_dir), publication_dir=Path(args.publication_dir), requested_date=args.date, request_id=args.request_id)
        _write_json_output(payload, args.output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
