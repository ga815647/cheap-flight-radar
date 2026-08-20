"""Persistent, isolated same-day FTR recovery orchestration primitives.

RP-05 deliberately reuses the existing CFR production acquisition substrate while
keeping recovery request/claim/run identity separate from canonical daily,
operator reacquisition, and scoped search.  This module never calls an airfare
provider itself.  Callers must persist a recovery claim before invoking the
existing production runtime, persist legitimate CFR evidence before entering the
FTR transaction, and share the production acquisition concurrency guard.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .ftr_handoff import (
    CANONICAL_LATEST_PATH,
    CURRENT_STATUS_PATH,
    FTRHandoffError,
    build_snapshot,
    clear_repair_required,
    load_current_status,
    load_manifest_snapshot,
    mark_repair_required,
    stage_snapshot,
)

PROJECT_TIMEZONE = ZoneInfo("Asia/Taipei")
RECOVERY_RUN_PREFIX = "ftr-recovery-"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class RecoveryOperationState:
    requested_date: str
    request_id: str
    status: str
    claim_path: str
    run_prefix: str
    repair_trigger_run_id: str | None = None
    repair_trigger_evidence_ref: str | None = None
    last_good_run_id: str | None = None
    reason: str | None = None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_request_id(request_id: str) -> str:
    value = str(request_id or "")
    if not REQUEST_ID_RE.fullmatch(value):
        raise FTRHandoffError("recovery request_id must be 1-64 path-safe characters")
    return value


def _validate_sha(value: str) -> str:
    sha = str(value or "").strip().lower()
    if not SHA_RE.fullmatch(sha):
        raise FTRHandoffError("application_sha must be the actual 40-hex current-main checkout SHA")
    return sha


def _day_parts(requested_date: str) -> tuple[str, str, str]:
    parsed = date.fromisoformat(requested_date)
    return f"{parsed.year:04d}", f"{parsed.month:02d}", f"{parsed.day:02d}"


def recovery_claim_repository_path(requested_date: str, request_id: str) -> str:
    request_id = _validate_request_id(request_id)
    year, month, day = _day_parts(requested_date)
    return f"data/ftr-recovery-attempts/{year}/{month}/{day}/{request_id}.json"


def recovery_run_prefix(request_id: str) -> str:
    return f"{RECOVERY_RUN_PREFIX}{_validate_request_id(request_id)}-"


def run_evidence_repository_dir(requested_date: str, run_id: str) -> str:
    year, month, day = _day_parts(requested_date)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(run_id)).strip("-.")
    if not safe:
        raise FTRHandoffError("recovery run id must contain a path-safe component")
    return f"data/run-evidence/{year}/{month}/{day}/{safe}"


def _read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FTRHandoffError(f"{label} is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise FTRHandoffError(f"{label} must be a JSON object")
    return payload


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
            raise FileExistsError(f"immutable recovery evidence collision: {path}")
        return
    _atomic_write_bytes(path, data)


def _copy_immutable(source: Path, target: Path, *, label: str) -> None:
    data = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise FileExistsError(f"immutable {label} collision: {target}")
        return
    _atomic_write_bytes(target, data)


def _aware_timestamp(value: str, *, field: str) -> str:
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FTRHandoffError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FTRHandoffError(f"{field} must be timezone-aware")
    return text


def _today_local(current_date: str | None = None) -> str:
    if current_date is not None:
        date.fromisoformat(current_date)
        return current_date
    return datetime.now(PROJECT_TIMEZONE).date().isoformat()


def _validate_same_day(requested_date: str, *, current_date: str | None = None) -> None:
    date.fromisoformat(requested_date)
    today = _today_local(current_date)
    if requested_date != today:
        raise FTRHandoffError(
            f"same_day_recovery request date must equal Asia/Taipei current day: request={requested_date} today={today}"
        )


def _read_repair_evidence(history_dir: Path, attempt: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
    run_id = str(attempt.get("run_id") or "")
    evidence_ref = str(attempt.get("evidence_ref") or "")
    if not run_id or not evidence_ref:
        raise FTRHandoffError(f"{label} is missing run_id/evidence_ref")
    evidence = _read_json(history_dir / evidence_ref, label=f"{label} evidence")
    evidence_run_id = str(evidence.get("run_id") or evidence.get("radar_run_id") or "")
    if evidence_run_id and evidence_run_id != run_id:
        raise FTRHandoffError(f"{label} evidence run identity mismatch")
    return evidence


def _validate_active_repair(history_dir: Path) -> Mapping[str, Any]:
    status = load_current_status(history_dir=history_dir)
    if not bool(status.get("repair_required")):
        return status
    incident = _mapping(status.get("repair_incident"))
    trigger = _mapping(incident.get("trigger_attempt"))
    latest_failed = _mapping(incident.get("latest_failed_attempt"))
    _read_repair_evidence(history_dir, trigger, label="repair trigger attempt")
    _read_repair_evidence(history_dir, latest_failed, label="latest failed attempt")
    return status


def _canonical_last_good_guard(history_dir: Path, status: Mapping[str, Any]) -> Mapping[str, Any] | None:
    latest_path = history_dir / CANONICAL_LATEST_PATH
    last_good = _mapping(status.get("last_good"))
    if not last_good:
        if latest_path.exists():
            raise FTRHandoffError("repair state has no last_good but canonical latest exists")
        return None
    if not latest_path.exists():
        raise FTRHandoffError("repair state last_good exists but canonical latest is missing")
    manifest = _read_json(latest_path, label="canonical latest manifest")
    snapshot = load_manifest_snapshot(history_dir=history_dir)
    expected = {
        "run_id": str(snapshot.get("run_id") or ""),
        "snapshot_path": str(manifest.get("snapshot_path") or ""),
        "snapshot_sha256": str(manifest.get("snapshot_sha256") or ""),
    }
    for field, value in expected.items():
        if str(last_good.get(field) or "") != value:
            raise FTRHandoffError(f"repair last_good does not match guarded canonical latest: {field}")
    return expected


def _snapshot_files(history_dir: Path, requested_date: str, request_id: str) -> list[Path]:
    year, month, day = _day_parts(requested_date)
    root = history_dir / "data" / "price-history" / year / month / day
    if not root.exists():
        return []
    prefix = recovery_run_prefix(request_id)
    return sorted(path for path in root.glob(f"{prefix}*.json") if path.is_file())


def inspect_recovery_state(
    *,
    history_dir: Path,
    requested_date: str,
    request_id: str,
    application_sha: str,
    current_date: str | None = None,
) -> RecoveryOperationState:
    """Fail-closed recovery preflight with no acquisition-start side effect."""
    history_dir = Path(history_dir)
    request_id = _validate_request_id(request_id)
    _validate_sha(application_sha)
    _validate_same_day(requested_date, current_date=current_date)
    claim_rel = recovery_claim_repository_path(requested_date, request_id)
    prefix = recovery_run_prefix(request_id)

    status = _validate_active_repair(history_dir)
    if not bool(status.get("repair_required")):
        return RecoveryOperationState(
            requested_date=requested_date,
            request_id=request_id,
            status="no_active_repair",
            claim_path=claim_rel,
            run_prefix=prefix,
            reason="same_day_recovery requires an already-durable active repair incident",
        )

    incident = _mapping(status.get("repair_incident"))
    trigger = _mapping(incident.get("trigger_attempt"))
    _canonical_last_good_guard(history_dir, status)

    claim_path = history_dir / claim_rel
    if claim_path.exists():
        return RecoveryOperationState(
            requested_date=requested_date,
            request_id=request_id,
            status="duplicate_request_claimed",
            claim_path=claim_rel,
            run_prefix=prefix,
            repair_trigger_run_id=str(trigger.get("run_id") or ""),
            repair_trigger_evidence_ref=str(trigger.get("evidence_ref") or ""),
            last_good_run_id=str(_mapping(status.get("last_good")).get("run_id") or "") or None,
            reason="recovery request id is already claimed; the same id may never reacquire",
        )

    snapshots = _snapshot_files(history_dir, requested_date, request_id)
    if snapshots:
        return RecoveryOperationState(
            requested_date=requested_date,
            request_id=request_id,
            status="blocked_recovery_namespace_collision",
            claim_path=claim_rel,
            run_prefix=prefix,
            repair_trigger_run_id=str(trigger.get("run_id") or ""),
            repair_trigger_evidence_ref=str(trigger.get("evidence_ref") or ""),
            last_good_run_id=str(_mapping(status.get("last_good")).get("run_id") or "") or None,
            reason="recovery-specific CFR snapshot exists without its immutable pre-acquisition claim",
        )

    return RecoveryOperationState(
        requested_date=requested_date,
        request_id=request_id,
        status="acquire",
        claim_path=claim_rel,
        run_prefix=prefix,
        repair_trigger_run_id=str(trigger.get("run_id") or ""),
        repair_trigger_evidence_ref=str(trigger.get("evidence_ref") or ""),
        last_good_run_id=str(_mapping(status.get("last_good")).get("run_id") or "") or None,
        reason="active repair is valid and this explicit recovery request id is unclaimed",
    )


def write_recovery_claim(
    *,
    history_dir: Path,
    requested_date: str,
    request_id: str,
    application_sha: str,
    claimed_at: str,
    workflow_run_id: str,
    workflow_run_url: str,
    trigger_sha: str,
    current_date: str | None = None,
) -> Path:
    """Persist the one-attempt recovery claim before any provider acquisition."""
    state = inspect_recovery_state(
        history_dir=history_dir,
        requested_date=requested_date,
        request_id=request_id,
        application_sha=application_sha,
        current_date=current_date,
    )
    if state.status != "acquire":
        raise FTRHandoffError(f"recovery claim refused in state {state.status}: {state.reason}")
    claimed_at = _aware_timestamp(claimed_at, field="recovery_claim.claimed_at")
    status = load_current_status(history_dir=history_dir)
    incident = _mapping(status.get("repair_incident"))
    target = Path(history_dir) / state.claim_path
    payload = {
        "schema_version": 1,
        "mode": "same_day_recovery",
        "requested_date": requested_date,
        "request_id": request_id,
        "claimed_at": claimed_at,
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_url": str(workflow_run_url),
        "control_trigger_sha": str(trigger_sha),
        "application_sha": _validate_sha(application_sha),
        "run_prefix": state.run_prefix,
        "repair_incident": {
            "set_at": incident.get("set_at"),
            "trigger_attempt": dict(_mapping(incident.get("trigger_attempt"))),
            "latest_failed_attempt_at_claim": dict(_mapping(incident.get("latest_failed_attempt"))),
        },
        "prior_last_good": dict(_mapping(status.get("last_good"))) or None,
        "semantics": "one_explicit_same_day_recovery_acquisition_per_request_id",
    }
    _write_immutable_json(target, payload)
    return target


def _load_claim(
    *,
    history_dir: Path,
    requested_date: str,
    request_id: str,
    application_sha: str,
) -> Mapping[str, Any]:
    path = Path(history_dir) / recovery_claim_repository_path(requested_date, request_id)
    if not path.exists():
        raise FTRHandoffError("recovery acquisition claim is missing")
    claim = _read_json(path, label="recovery acquisition claim")
    expected = {
        "mode": "same_day_recovery",
        "requested_date": requested_date,
        "request_id": request_id,
        "application_sha": _validate_sha(application_sha),
        "run_prefix": recovery_run_prefix(request_id),
    }
    for field, value in expected.items():
        if str(claim.get(field) or "") != value:
            raise FTRHandoffError(f"recovery claim identity mismatch: {field}")
    _aware_timestamp(str(claim.get("claimed_at") or ""), field="recovery_claim.claimed_at")
    return claim


def _validate_claim_against_active_repair(
    *, history_dir: Path, claim: Mapping[str, Any]
) -> Mapping[str, Any]:
    status = _validate_active_repair(history_dir)
    if not bool(status.get("repair_required")):
        raise FTRHandoffError("recovery transaction cannot continue after repair incident is no longer active")
    incident = _mapping(status.get("repair_incident"))
    claimed_incident = _mapping(claim.get("repair_incident"))
    claimed_trigger = _mapping(claimed_incident.get("trigger_attempt"))
    active_trigger = _mapping(incident.get("trigger_attempt"))
    if dict(claimed_trigger) != dict(active_trigger):
        raise FTRHandoffError("active repair trigger no longer matches the claimed recovery incident")
    if str(claimed_incident.get("set_at") or "") != str(incident.get("set_at") or ""):
        raise FTRHandoffError("active repair incident chronology no longer matches recovery claim")
    _canonical_last_good_guard(history_dir, status)
    return status


def _validate_terminal_recovery_result(
    result: Mapping[str, Any], *, requested_date: str, request_id: str
) -> tuple[str, str]:
    run_id = str(result.get("radar_run_id") or result.get("run_id") or "")
    if not run_id.startswith(recovery_run_prefix(request_id)):
        raise FTRHandoffError("CFR run-result does not match recovery request run namespace")
    if str(result.get("execution_mode") or "") != "same_day_recovery":
        raise FTRHandoffError("CFR run-result execution_mode is not same_day_recovery")
    run_at = _aware_timestamp(
        str(result.get("run_at") or result.get("observed_at") or ""),
        field="recovery_run_result.run_at",
    )
    observed = datetime.fromisoformat(run_at.replace("Z", "+00:00")).astimezone(PROJECT_TIMEZONE)
    if observed.date().isoformat() != requested_date:
        raise FTRHandoffError("recovery run-result Asia/Taipei local date does not match request")
    terminal = result.get("terminal_state")
    if terminal is not None and str(terminal) != "success":
        raise FTRHandoffError("recovery run-result terminal_state is not success")
    return run_id, run_at


def stage_recovery_cfr_success_evidence(
    *,
    output_dir: Path,
    history_dir: Path,
    requested_date: str,
    request_id: str,
    application_sha: str,
) -> Mapping[str, str]:
    """Persist legitimate CFR recovery evidence before any FTR latest mutation."""
    output_dir = Path(output_dir)
    history_dir = Path(history_dir)
    claim = _load_claim(
        history_dir=history_dir,
        requested_date=requested_date,
        request_id=request_id,
        application_sha=application_sha,
    )
    status = _validate_claim_against_active_repair(history_dir=history_dir, claim=claim)

    result_path = output_dir / "run-result.json"
    result = _read_json(result_path, label="recovery runtime run-result")
    run_id, _ = _validate_terminal_recovery_result(
        result, requested_date=requested_date, request_id=request_id
    )

    manifest_source = output_dir / "publication" / "runs" / f"{run_id}.json"
    manifest = _read_json(manifest_source, label="recovery runtime publication manifest")
    if str(manifest.get("radar_run_id") or "") != run_id:
        raise FTRHandoffError("recovery CFR manifest run identity mismatch")
    if str(manifest.get("execution_mode") or "") != "same_day_recovery":
        raise FTRHandoffError("recovery CFR manifest execution_mode mismatch")
    history_rel = str(manifest.get("history_snapshot_path") or "")
    if not history_rel:
        raise FTRHandoffError("recovery CFR manifest missing history_snapshot_path")
    snapshot_source = output_dir / "history" / history_rel
    snapshot = _read_json(snapshot_source, label="recovery CFR price-history snapshot")
    if str(snapshot.get("radar_run_id") or "") != run_id:
        raise FTRHandoffError("recovery CFR price-history run identity mismatch")

    snapshot_target = history_dir / history_rel
    _copy_immutable(snapshot_source, snapshot_target, label="recovery CFR price-history snapshot")
    evidence_dir = history_dir / run_evidence_repository_dir(requested_date, run_id)
    recovery_result = evidence_dir / "run-result.json"
    recovery_manifest = evidence_dir / "publication-manifest.json"
    _copy_immutable(result_path, recovery_result, label="recovery run-result")
    _copy_immutable(manifest_source, recovery_manifest, label="recovery publication-manifest evidence")
    acquisition_meta = evidence_dir / "recovery-acquisition.json"
    _write_immutable_json(acquisition_meta, {
        "schema_version": 1,
        "mode": "same_day_recovery",
        "requested_date": requested_date,
        "request_id": request_id,
        "run_id": run_id,
        "application_sha": _validate_sha(application_sha),
        "claim_path": recovery_claim_repository_path(requested_date, request_id),
        "repair_trigger_attempt": dict(_mapping(_mapping(status.get("repair_incident")).get("trigger_attempt"))),
        "run_result_path": recovery_result.relative_to(history_dir).as_posix(),
        "price_history_path": snapshot_target.relative_to(history_dir).as_posix(),
        "publication_manifest_evidence_path": recovery_manifest.relative_to(history_dir).as_posix(),
        "terminal_acquisition_truth": "success",
        "semantics": "durable_cfr_recovery_evidence_precedes_ftr_recovery_transaction",
    })
    return {
        "radar_run_id": run_id,
        "history_snapshot_path": snapshot_target.relative_to(history_dir).as_posix(),
        "run_result_path": recovery_result.relative_to(history_dir).as_posix(),
        "recovery_manifest_path": recovery_manifest.relative_to(history_dir).as_posix(),
        "recovery_acquisition_path": acquisition_meta.relative_to(history_dir).as_posix(),
    }


def _relative_to_history(history_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(history_dir.resolve()).as_posix()
    except ValueError as exc:
        raise FTRHandoffError("recovery run-result evidence must live inside durable history checkout") from exc


def _restore_guard(path: Path, previous: bytes | None) -> None:
    if previous is None:
        if path.exists():
            path.unlink()
        return
    _atomic_write_bytes(path, previous)


def _failure_evidence_path(requested_date: str, run_id: str) -> str:
    return f"{run_evidence_repository_dir(requested_date, run_id)}/ftr-recovery-failed-attempt.json"


def _persist_failed_recovery_attempt(
    *,
    history_dir: Path,
    requested_date: str,
    request_id: str,
    run_id: str,
    application_sha: str,
    failed_at: str,
    failure_stage: str,
    reason: str,
    run_result_evidence_ref: str | None,
    producer_health_status: str,
) -> Mapping[str, Any]:
    claim = _load_claim(
        history_dir=history_dir,
        requested_date=requested_date,
        request_id=request_id,
        application_sha=application_sha,
    )
    status = _validate_claim_against_active_repair(history_dir=history_dir, claim=claim)
    evidence_ref = _failure_evidence_path(requested_date, run_id)
    incident = _mapping(status.get("repair_incident"))
    payload = {
        "schema_version": 1,
        "attempt_state": "failed",
        "mode": "same_day_recovery",
        "requested_date": requested_date,
        "request_id": request_id,
        "run_id": run_id,
        "failed_at": failed_at,
        "failure_stage": failure_stage,
        "reason": reason[:1000],
        "application_sha": _validate_sha(application_sha),
        "claim_path": recovery_claim_repository_path(requested_date, request_id),
        "repair_trigger_attempt": dict(_mapping(incident.get("trigger_attempt"))),
        "run_result_evidence_ref": run_result_evidence_ref,
        "semantics": "durable_same_day_recovery_failure_preserves_original_repair_trigger",
    }
    _write_immutable_json(history_dir / evidence_ref, payload)
    current = mark_repair_required(
        history_dir=history_dir,
        failed_attempt={
            "run_id": run_id,
            "mode": "same_day_recovery",
            "attempt_state": "failed",
            "evidence_ref": evidence_ref,
            "producer_health_status": producer_health_status,
        },
        incident_set_at=failed_at,
    )
    return {"evidence_ref": evidence_ref, "current_status": current}


def stage_recovery_success(
    *,
    history_dir: Path,
    run_result_path: Path,
    requested_date: str,
    request_id: str,
    application_sha: str,
    generated_at: str | None = None,
    failed_at: str | None = None,
) -> Mapping[str, Any]:
    """Advance canonical FTR latest and clear repair only as one guarded transaction."""
    history_dir = Path(history_dir)
    run_result_path = Path(run_result_path)
    sha = _validate_sha(application_sha)
    _validate_same_day(requested_date)
    claim = _load_claim(
        history_dir=history_dir,
        requested_date=requested_date,
        request_id=request_id,
        application_sha=sha,
    )
    prior_status = _validate_claim_against_active_repair(history_dir=history_dir, claim=claim)
    run_result_ref = _relative_to_history(history_dir, run_result_path)
    latest_path = history_dir / CANONICAL_LATEST_PATH
    status_path = history_dir / CURRENT_STATUS_PATH
    previous_latest = latest_path.read_bytes() if latest_path.exists() else None
    previous_status = status_path.read_bytes()
    now = _aware_timestamp(
        failed_at or generated_at or datetime.now(PROJECT_TIMEZONE).isoformat(),
        field="ftr_recovery.attempt_time",
    )
    fallback_run_id = f"{recovery_run_prefix(request_id)}transaction"
    run_id = fallback_run_id
    producer_health_status = "operational_failed"

    try:
        # Reload immediately before consuming the claimed incident so a stale
        # in-memory preflight can never clear a different repair chronology.
        _validate_claim_against_active_repair(history_dir=history_dir, claim=claim)
        run_result = _read_json(run_result_path, label="durable recovery run-result")
        run_id, run_at = _validate_terminal_recovery_result(
            run_result, requested_date=requested_date, request_id=request_id
        )
        provider_health = _mapping(run_result.get("provider_health"))
        producer_health_status = str(provider_health.get("status") or "unknown")

        snapshot = build_snapshot(
            run_result,
            producer_commit_sha=sha,
            mode="same_day_recovery",
            generated_at=generated_at,
        )
        if str(snapshot.get("coverage_state")) != "complete" or str(snapshot.get("freshness_state")) != "fresh":
            raise FTRHandoffError("same_day_recovery must be complete and fresh before canonical latest advancement")
        health = str(_mapping(_mapping(snapshot.get("coverage")).get("provider_health")).get("status") or "")
        if health != "healthy":
            raise FTRHandoffError("same_day_recovery provider health must be healthy")

        staged = stage_snapshot(history_dir=history_dir, snapshot=snapshot)
        snapshot_path = history_dir / staged["snapshot_path"]
        exact_sha256 = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        if exact_sha256 != staged["snapshot_sha256"]:
            raise FTRHandoffError("persisted recovery snapshot checksum differs from canonical manifest")

        loaded = load_manifest_snapshot(history_dir=history_dir)
        if str(loaded.get("run_id")) != run_id:
            raise FTRHandoffError("reloaded recovery run identity mismatch")
        if str(loaded.get("mode")) != "same_day_recovery":
            raise FTRHandoffError("reloaded canonical latest mode is not same_day_recovery")
        if str(loaded.get("producer_commit_sha")) != sha:
            raise FTRHandoffError("reloaded recovery producer application SHA mismatch")
        if str(loaded.get("coverage_state")) != "complete" or str(loaded.get("freshness_state")) != "fresh":
            raise FTRHandoffError("reloaded recovery is not complete/fresh")
        loaded_health = str(_mapping(_mapping(loaded.get("coverage")).get("provider_health")).get("status") or "")
        if loaded_health != "healthy":
            raise FTRHandoffError("reloaded recovery provider health is not healthy")

        cleared = clear_repair_required(
            history_dir=history_dir,
            recovery_run_id=run_id,
            attempt_mode="same_day_recovery",
            cleared_at=generated_at or now,
        )
        transition_ref = f"{run_evidence_repository_dir(requested_date, run_id)}/ftr-recovery-transition.json"
        _write_immutable_json(history_dir / transition_ref, {
            "schema_version": 1,
            "state": "cleared",
            "mode": "same_day_recovery",
            "requested_date": requested_date,
            "request_id": request_id,
            "run_id": run_id,
            "run_at": run_at,
            "application_sha": sha,
            "claim_path": recovery_claim_repository_path(requested_date, request_id),
            "original_repair_trigger": dict(_mapping(_mapping(prior_status.get("repair_incident")).get("trigger_attempt"))),
            "snapshot_path": staged["snapshot_path"],
            "snapshot_sha256": exact_sha256,
            "manifest_path": staged["manifest_path"],
            "cleared_at": str(_mapping(cleared.get("repair_incident")).get("cleared_at") or generated_at or now),
            "semantics": "validated_recovery_latest_then_repair_clear",
        })
        return {
            "status": "success",
            "radar_run_id": run_id,
            "run_at": run_at,
            "request_id": request_id,
            "producer_commit_sha": sha,
            "snapshot_path": staged["snapshot_path"],
            "snapshot_sha256": exact_sha256,
            "manifest_path": staged["manifest_path"],
            "transition_evidence_ref": transition_ref,
            "current_status_path": CURRENT_STATUS_PATH,
            "repair_required": False,
            "freshness_state": "fresh",
        }
    except Exception as exc:
        # A tentative recovery latest or even a just-written clear must never
        # survive a later verification/transition failure.
        _restore_guard(latest_path, previous_latest)
        _restore_guard(status_path, previous_status)
        reason = f"{type(exc).__name__}: {exc}"
        failed = _persist_failed_recovery_attempt(
            history_dir=history_dir,
            requested_date=requested_date,
            request_id=request_id,
            run_id=run_id,
            application_sha=sha,
            failed_at=now,
            failure_stage="same_day_recovery_ftr_transaction",
            reason=reason,
            run_result_evidence_ref=run_result_ref,
            producer_health_status=producer_health_status,
        )
        return {
            "status": "failed",
            "radar_run_id": run_id,
            "request_id": request_id,
            "producer_commit_sha": sha,
            "failure_reason": reason,
            "failure_evidence_ref": failed["evidence_ref"],
            "repair_required": True,
            "current_freshness_state": failed["current_status"]["current_freshness_state"],
        }


def stage_recovery_process_failure(
    *,
    history_dir: Path,
    requested_date: str,
    request_id: str,
    application_sha: str,
    attempt_run_id: str,
    failed_at: str | None = None,
    failure_stage: str = "same_day_recovery_acquisition_process",
    reason: str = "same-day recovery acquisition did not complete successfully",
) -> Mapping[str, Any]:
    """Persist a claimed recovery failure without inventing a second attempt."""
    sha = _validate_sha(application_sha)
    when = _aware_timestamp(
        failed_at or datetime.now(PROJECT_TIMEZONE).isoformat(),
        field="ftr_recovery.failed_at",
    )
    failed = _persist_failed_recovery_attempt(
        history_dir=Path(history_dir),
        requested_date=requested_date,
        request_id=request_id,
        run_id=str(attempt_run_id),
        application_sha=sha,
        failed_at=when,
        failure_stage=failure_stage,
        reason=reason,
        run_result_evidence_ref=None,
        producer_health_status="operational_failed",
    )
    return {
        "status": "failed",
        "radar_run_id": str(attempt_run_id),
        "request_id": request_id,
        "producer_commit_sha": sha,
        "failure_evidence_ref": failed["evidence_ref"],
        "repair_required": True,
        "current_freshness_state": failed["current_status"]["current_freshness_state"],
    }


def _write_output(payload: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent FTR same-day recovery orchestration")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--history-dir", required=True)
    inspect.add_argument("--date", required=True)
    inspect.add_argument("--request-id", required=True)
    inspect.add_argument("--application-sha", required=True)
    inspect.add_argument("--current-date")
    inspect.add_argument("--output")

    claim = sub.add_parser("claim")
    claim.add_argument("--history-dir", required=True)
    claim.add_argument("--date", required=True)
    claim.add_argument("--request-id", required=True)
    claim.add_argument("--application-sha", required=True)
    claim.add_argument("--claimed-at", required=True)
    claim.add_argument("--workflow-run-id", required=True)
    claim.add_argument("--workflow-run-url", required=True)
    claim.add_argument("--trigger-sha", required=True)
    claim.add_argument("--current-date")
    claim.add_argument("--output")

    cfr = sub.add_parser("stage-cfr-success")
    cfr.add_argument("--output-dir", required=True)
    cfr.add_argument("--history-dir", required=True)
    cfr.add_argument("--date", required=True)
    cfr.add_argument("--request-id", required=True)
    cfr.add_argument("--application-sha", required=True)
    cfr.add_argument("--output")

    success = sub.add_parser("stage-success")
    success.add_argument("--history-dir", required=True)
    success.add_argument("--run-result", required=True)
    success.add_argument("--date", required=True)
    success.add_argument("--request-id", required=True)
    success.add_argument("--application-sha", required=True)
    success.add_argument("--generated-at")
    success.add_argument("--failed-at")
    success.add_argument("--output")

    failure = sub.add_parser("stage-failure")
    failure.add_argument("--history-dir", required=True)
    failure.add_argument("--date", required=True)
    failure.add_argument("--request-id", required=True)
    failure.add_argument("--application-sha", required=True)
    failure.add_argument("--attempt-run-id", required=True)
    failure.add_argument("--failed-at")
    failure.add_argument("--failure-stage", default="same_day_recovery_acquisition_process")
    failure.add_argument("--reason", default="same-day recovery acquisition did not complete successfully")
    failure.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        state = inspect_recovery_state(
            history_dir=Path(args.history_dir),
            requested_date=args.date,
            request_id=args.request_id,
            application_sha=args.application_sha,
            current_date=args.current_date,
        )
        _write_output(asdict(state), args.output)
        return 0
    if args.command == "claim":
        path = write_recovery_claim(
            history_dir=Path(args.history_dir),
            requested_date=args.date,
            request_id=args.request_id,
            application_sha=args.application_sha,
            claimed_at=args.claimed_at,
            workflow_run_id=args.workflow_run_id,
            workflow_run_url=args.workflow_run_url,
            trigger_sha=args.trigger_sha,
            current_date=args.current_date,
        )
        _write_output({"claim_path": path.as_posix()}, args.output)
        return 0
    if args.command == "stage-cfr-success":
        payload = stage_recovery_cfr_success_evidence(
            output_dir=Path(args.output_dir),
            history_dir=Path(args.history_dir),
            requested_date=args.date,
            request_id=args.request_id,
            application_sha=args.application_sha,
        )
        _write_output(payload, args.output)
        return 0
    if args.command == "stage-success":
        payload = stage_recovery_success(
            history_dir=Path(args.history_dir),
            run_result_path=Path(args.run_result),
            requested_date=args.date,
            request_id=args.request_id,
            application_sha=args.application_sha,
            generated_at=args.generated_at,
            failed_at=args.failed_at,
        )
        _write_output(payload, args.output)
        return 0
    if args.command == "stage-failure":
        payload = stage_recovery_process_failure(
            history_dir=Path(args.history_dir),
            requested_date=args.date,
            request_id=args.request_id,
            application_sha=args.application_sha,
            attempt_run_id=args.attempt_run_id,
            failed_at=args.failed_at,
            failure_stage=args.failure_stage,
            reason=args.reason,
        )
        _write_output(payload, args.output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
