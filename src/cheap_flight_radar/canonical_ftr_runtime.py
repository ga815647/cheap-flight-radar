"""Canonical CFR -> FTR staging transaction for RP-04.

This module is intentionally downstream of the existing canonical CFR acquisition
and durable CFR evidence staging.  It never acquires fares and never rewrites
CFR price-history/publication evidence.  Its only durable writes are the FTR
handoff namespace plus compact failed-attempt evidence under the existing
Git-backed run-evidence namespace.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .ftr_handoff import (
    CANONICAL_LATEST_PATH,
    FTRHandoffError,
    build_snapshot,
    load_manifest_snapshot,
    mark_repair_required,
    stage_current_status_from_snapshot,
    stage_snapshot,
)


CANONICAL_RUN_PREFIX = "production-radar-"
_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FTRHandoffError(f"{label} is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise FTRHandoffError(f"{label} must be a JSON object")
    return payload


def _aware_timestamp(value: str | None, *, field: str) -> str:
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FTRHandoffError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FTRHandoffError(f"{field} must be timezone-aware")
    return text


def _producer_sha(value: str) -> str:
    sha = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(sha):
        raise FTRHandoffError("producer_commit_sha must be the full 40-hex application checkout SHA")
    return sha


def _safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    if not safe:
        raise FTRHandoffError("attempt run id must contain a path-safe component")
    return safe


def _failure_evidence_path(requested_date: str, attempt_run_id: str) -> str:
    parsed = date.fromisoformat(requested_date)
    return (
        f"data/run-evidence/{parsed:%Y/%m/%d}/"
        f"{_safe_component(attempt_run_id)}/ftr-failed-attempt.json"
    )


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    data = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"immutable failed-attempt evidence collision: {path}")
        return
    _atomic_write_bytes(path, data)


def _restore_latest(history_dir: Path, previous_latest: bytes | None) -> None:
    latest_path = history_dir / CANONICAL_LATEST_PATH
    if previous_latest is None:
        if latest_path.exists():
            latest_path.unlink()
        return
    _atomic_write_bytes(latest_path, previous_latest)


def _relative_to_history(history_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(history_dir.resolve()).as_posix()
    except ValueError as exc:
        raise FTRHandoffError("canonical run-result evidence must live inside the durable history checkout") from exc


def _validate_terminal_canonical_run_result(
    run_result: Mapping[str, Any], *, requested_date: str | None = None
) -> tuple[str, str]:
    run_id = str(run_result.get("radar_run_id") or run_result.get("run_id") or "")
    if not run_id.startswith(CANONICAL_RUN_PREFIX):
        raise FTRHandoffError("canonical FTR staging requires a canonical production-radar run identity")
    run_at = _aware_timestamp(
        str(run_result.get("run_at") or run_result.get("observed_at") or ""),
        field="canonical_run_result.run_at",
    )
    if requested_date is not None:
        observed = datetime.fromisoformat(run_at.replace("Z", "+00:00"))
        if observed.date().isoformat() != requested_date:
            raise FTRHandoffError("canonical run-result local date does not match the claimed request date")
    # Existing CFR run-result files predate an explicit terminal_state field.  In
    # RP-04, invocation of this success transaction is itself gated on the
    # acquisition process and durable CFR stage-success completing.  If a future
    # run-result adds terminal_state, it must agree with that success gate.
    terminal = run_result.get("terminal_state")
    if terminal is not None and str(terminal) != "success":
        raise FTRHandoffError("canonical run-result terminal_state is not success")
    return run_id, run_at


def _persist_failed_attempt(
    *,
    history_dir: Path,
    requested_date: str,
    attempt_run_id: str,
    attempt_state: str,
    producer_commit_sha: str,
    failed_at: str,
    failure_stage: str,
    reason: str,
    run_result_evidence_ref: str | None,
    producer_health_status: str,
) -> Mapping[str, Any]:
    evidence_ref = _failure_evidence_path(requested_date, attempt_run_id)
    payload = {
        "schema_version": 1,
        "attempt_state": attempt_state,
        "mode": "canonical_daily",
        "run_id": attempt_run_id,
        "failed_at": failed_at,
        "failure_stage": failure_stage,
        "reason": reason[:1000],
        "producer_commit_sha": producer_commit_sha,
        "run_result_evidence_ref": run_result_evidence_ref,
        "semantics": "durable_canonical_ftr_failed_attempt_not_actions_artifact",
    }
    _write_immutable_json(history_dir / evidence_ref, payload)
    status = mark_repair_required(
        history_dir=history_dir,
        failed_attempt={
            "run_id": attempt_run_id,
            "mode": "canonical_daily",
            "attempt_state": attempt_state,
            "evidence_ref": evidence_ref,
            "producer_health_status": producer_health_status,
        },
        incident_set_at=failed_at,
    )
    return {"evidence_ref": evidence_ref, "current_status": status}


def stage_canonical_success(
    *,
    history_dir: Path,
    run_result_path: Path,
    producer_commit_sha: str,
    attempt_run_id: str | None = None,
    requested_date: str | None = None,
    generated_at: str | None = None,
    failed_at: str | None = None,
) -> Mapping[str, Any]:
    """Stage one canonical FTR handoff after durable CFR success evidence exists.

    The previous canonical latest bytes are treated as a transaction guard.  Any
    exception after a tentative manifest write restores those exact bytes (or
    removes a newly-created manifest when no last-good existed) before recording
    ``repair_required``.  Immutable snapshots already written remain immutable
    evidence and are never rewritten or deleted.
    """
    history_dir = Path(history_dir)
    run_result_path = Path(run_result_path)
    sha = _producer_sha(producer_commit_sha)
    run_result_ref = _relative_to_history(history_dir, run_result_path)
    latest_path = history_dir / CANONICAL_LATEST_PATH
    previous_latest = latest_path.read_bytes() if latest_path.exists() else None
    now = _aware_timestamp(
        failed_at or generated_at or datetime.now(timezone.utc).isoformat(),
        field="canonical_ftr.attempt_time",
    )
    fallback_run_id = str(attempt_run_id or "")
    run_id = fallback_run_id
    producer_health_status = "operational_failed"

    try:
        run_result = _read_json(run_result_path, label="canonical durable run-result")
        run_id, run_at = _validate_terminal_canonical_run_result(
            run_result,
            requested_date=requested_date,
        )
        if fallback_run_id and fallback_run_id != run_id:
            raise FTRHandoffError("attempt run identity does not match durable canonical run-result")
        provider_health = _mapping(run_result.get("provider_health"))
        producer_health_status = str(provider_health.get("status") or "unknown")

        snapshot = build_snapshot(
            run_result,
            producer_commit_sha=sha,
            mode="canonical_daily",
            generated_at=generated_at,
        )
        staged = stage_snapshot(history_dir=history_dir, snapshot=snapshot)

        # Checksum truth comes from the exact bytes that now exist on disk, not
        # from a reconstructed object after persistence.
        snapshot_path = history_dir / staged["snapshot_path"]
        exact_sha256 = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        if exact_sha256 != staged["snapshot_sha256"]:
            raise FTRHandoffError("persisted FTR snapshot checksum differs from manifest checksum")

        loaded = load_manifest_snapshot(history_dir=history_dir)
        if str(loaded.get("run_id")) != run_id:
            raise FTRHandoffError("reloaded canonical FTR manifest/snapshot run identity mismatch")
        if str(loaded.get("producer_commit_sha")) != sha:
            raise FTRHandoffError("reloaded canonical FTR snapshot producer commit mismatch")
        status = stage_current_status_from_snapshot(
            history_dir=history_dir,
            snapshot=loaded,
            updated_at=generated_at,
        )
        return {
            "status": "success",
            "radar_run_id": run_id,
            "run_at": run_at,
            "producer_commit_sha": sha,
            "snapshot_path": staged["snapshot_path"],
            "snapshot_sha256": exact_sha256,
            "manifest_path": staged["manifest_path"],
            "freshness_state": str(loaded["freshness_state"]),
            "coverage_state": str(loaded["coverage_state"]),
            "current_status_path": "data/ftr-feed/current-status.json",
            "candidate_counts": dict(_mapping(loaded.get("candidate_counts"))),
        }
    except Exception as exc:  # producer-contract failure must become durable state
        _restore_latest(history_dir, previous_latest)
        if not run_id:
            run_id = f"canonical-attempt-{requested_date or 'unknown'}"
        if requested_date is None:
            try:
                candidate = _read_json(run_result_path, label="canonical durable run-result")
                observed = _aware_timestamp(
                    str(candidate.get("run_at") or candidate.get("observed_at") or ""),
                    field="canonical_run_result.run_at",
                )
                requested_date = datetime.fromisoformat(observed.replace("Z", "+00:00")).date().isoformat()
            except Exception:
                requested_date = now[:10]
        reason = f"{type(exc).__name__}: {exc}"
        failed = _persist_failed_attempt(
            history_dir=history_dir,
            requested_date=requested_date,
            attempt_run_id=run_id,
            attempt_state="invalid",
            producer_commit_sha=sha,
            failed_at=now,
            failure_stage="canonical_ftr_staging",
            reason=reason,
            run_result_evidence_ref=run_result_ref,
            producer_health_status=producer_health_status,
        )
        return {
            "status": "failed",
            "radar_run_id": run_id,
            "producer_commit_sha": sha,
            "failure_reason": reason,
            "failure_evidence_ref": failed["evidence_ref"],
            "current_freshness_state": failed["current_status"]["current_freshness_state"],
            "repair_required": True,
        }


def stage_canonical_process_failure(
    *,
    history_dir: Path,
    requested_date: str,
    attempt_run_id: str,
    producer_commit_sha: str,
    failed_at: str | None = None,
    reason: str = "canonical acquisition process did not complete successfully",
) -> Mapping[str, Any]:
    """Persist acquisition-process failure without fabricating an FTR latest."""
    sha = _producer_sha(producer_commit_sha)
    when = _aware_timestamp(
        failed_at or datetime.now(timezone.utc).isoformat(),
        field="canonical_ftr.failed_at",
    )
    failed = _persist_failed_attempt(
        history_dir=Path(history_dir),
        requested_date=requested_date,
        attempt_run_id=attempt_run_id,
        attempt_state="failed",
        producer_commit_sha=sha,
        failed_at=when,
        failure_stage="canonical_acquisition_process",
        reason=reason,
        run_result_evidence_ref=None,
        producer_health_status="operational_failed",
    )
    return {
        "status": "failed",
        "radar_run_id": attempt_run_id,
        "producer_commit_sha": sha,
        "failure_evidence_ref": failed["evidence_ref"],
        "current_freshness_state": failed["current_status"]["current_freshness_state"],
        "repair_required": True,
    }


def _write_output(payload: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical FTR handoff staging transaction")
    sub = parser.add_subparsers(dest="command", required=True)

    success = sub.add_parser("stage-success")
    success.add_argument("--history-dir", required=True)
    success.add_argument("--run-result", required=True)
    success.add_argument("--producer-commit-sha", required=True)
    success.add_argument("--attempt-run-id")
    success.add_argument("--date")
    success.add_argument("--generated-at")
    success.add_argument("--failed-at")
    success.add_argument("--output")

    failure = sub.add_parser("stage-failure")
    failure.add_argument("--history-dir", required=True)
    failure.add_argument("--date", required=True)
    failure.add_argument("--attempt-run-id", required=True)
    failure.add_argument("--producer-commit-sha", required=True)
    failure.add_argument("--failed-at")
    failure.add_argument("--reason", default="canonical acquisition process did not complete successfully")
    failure.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "stage-success":
        payload = stage_canonical_success(
            history_dir=Path(args.history_dir),
            run_result_path=Path(args.run_result),
            producer_commit_sha=args.producer_commit_sha,
            attempt_run_id=args.attempt_run_id,
            requested_date=args.date,
            generated_at=args.generated_at,
            failed_at=args.failed_at,
        )
        _write_output(payload, args.output)
        return 0
    if args.command == "stage-failure":
        payload = stage_canonical_process_failure(
            history_dir=Path(args.history_dir),
            requested_date=args.date,
            attempt_run_id=args.attempt_run_id,
            producer_commit_sha=args.producer_commit_sha,
            failed_at=args.failed_at,
            reason=args.reason,
        )
        _write_output(payload, args.output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
