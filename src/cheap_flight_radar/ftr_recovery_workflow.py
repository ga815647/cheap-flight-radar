"""GitHub Actions control driver for explicit FTR same-day recovery.

The workflow intentionally delegates ordering to this small deterministic driver:
preflight -> immutable request claim commit -> one production acquisition ->
durable CFR evidence commit -> guarded FTR transaction commit.  There is no
publication dispatch and no automatic retry.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .ftr_handoff import FTRHandoffError
from .ftr_recovery import (
    inspect_recovery_state,
    recovery_run_prefix,
    stage_recovery_cfr_success_evidence,
    stage_recovery_process_failure,
    stage_recovery_success,
    write_recovery_claim,
)

PROJECT_TIMEZONE = ZoneInfo("Asia/Taipei")
EVIDENCE_REF = "history/price-observations"


class RecoveryWorkflowError(RuntimeError):
    def __init__(self, stage: str, message: str, *, attempt_run_id: str | None = None):
        super().__init__(message)
        self.stage = stage
        self.attempt_run_id = attempt_run_id


def _run(command: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), cwd=str(cwd) if cwd else None, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check,
    )


def _git_output(path: Path, *args: str) -> str:
    result = _run(("git", "-C", str(path), *args))
    return result.stdout.strip()


def _commit_and_push(history_dir: Path, paths: Sequence[str], message: str) -> None:
    _run(("git", "-C", str(history_dir), "config", "user.name", "github-actions[bot]"))
    _run(("git", "-C", str(history_dir), "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"))
    _run(("git", "-C", str(history_dir), "add", "--", *paths))
    status = _git_output(history_dir, "status", "--porcelain", "--", *paths)
    if not status:
        return
    _run(("git", "-C", str(history_dir), "commit", "-m", message))
    _run(("git", "-C", str(history_dir), "push", "origin", f"HEAD:{EVIDENCE_REF}"))


def _reset_to_durable_remote(history_dir: Path) -> None:
    _run(("git", "-C", str(history_dir), "fetch", "origin", EVIDENCE_REF))
    _run(("git", "-C", str(history_dir), "reset", "--hard", f"origin/{EVIDENCE_REF}"))
    _run(("git", "-C", str(history_dir), "clean", "-fd", "--", "data/ftr-feed", "data/run-evidence", "data/price-history"))


def _write_debug(debug_dir: Path, name: str, payload: Mapping[str, object]) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / name).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(PROJECT_TIMEZONE).isoformat()


def run_recovery_workflow(
    *,
    app_dir: Path,
    history_dir: Path,
    output_dir: Path,
    request_date: str,
    request_id: str,
    workflow_run_id: str,
    workflow_run_url: str,
    trigger_sha: str,
    debug_dir: Path,
    current_date: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = _run,
) -> Mapping[str, object]:
    """Execute exactly one explicitly claimed recovery acquisition.

    ``command_runner`` exists only for deterministic tests; production uses
    ``_run`` and invokes the existing ``production_runtime`` exactly once.
    """
    app_dir, history_dir, output_dir = Path(app_dir), Path(history_dir), Path(output_dir)
    debug_dir = Path(debug_dir)
    application_sha = _git_output(app_dir, "rev-parse", "HEAD")
    today = current_date or datetime.now(PROJECT_TIMEZONE).date().isoformat()

    # 1. Preflight before any acquisition-start claim or provider process.
    state = inspect_recovery_state(
        history_dir=history_dir,
        requested_date=request_date,
        request_id=request_id,
        application_sha=application_sha,
        current_date=today,
    )
    _write_debug(debug_dir, "preflight.json", state.__dict__)
    if state.status != "acquire":
        raise RecoveryWorkflowError("preflight", f"same-day recovery refused in state {state.status}")

    claimed = False
    cfr_persisted = False
    attempt_run_id: str | None = None
    try:
        # 2. The unique recovery claim is durable before provider acquisition.
        write_recovery_claim(
            history_dir=history_dir,
            requested_date=request_date,
            request_id=request_id,
            application_sha=application_sha,
            claimed_at=_now(),
            workflow_run_id=workflow_run_id,
            workflow_run_url=workflow_run_url,
            trigger_sha=trigger_sha,
            current_date=today,
        )
        _commit_and_push(
            history_dir,
            ("data/ftr-recovery-attempts",),
            f"Claim FTR same-day recovery {request_id}",
        )
        claimed = True

        # 3. Exactly one call into the existing CFR production acquisition engine.
        acquisition = command_runner((
            sys.executable, "-m", "cheap_flight_radar.production_runtime",
            "--policy", str(app_dir / "flight-radar.yaml"),
            "--history-dir", str(history_dir),
            "--output-dir", str(output_dir),
            "--run-id-prefix", f"ftr-recovery-{request_id}",
            "--execution-mode", "same_day_recovery",
        ), check=False)
        _write_debug(debug_dir, "acquisition.json", {
            "returncode": acquisition.returncode,
            "stdout": acquisition.stdout,
            "semantics": "single_explicit_provider_acquisition_no_hidden_retry",
        })
        if acquisition.returncode != 0:
            raise RecoveryWorkflowError(
                "same_day_recovery_acquisition_process",
                "same-day recovery production acquisition failed",
                attempt_run_id=f"{recovery_run_prefix(request_id)}workflow-{workflow_run_id}",
            )

        # 4. Legitimate CFR recovery evidence is durable before any FTR mutation.
        cfr = stage_recovery_cfr_success_evidence(
            output_dir=output_dir,
            history_dir=history_dir,
            requested_date=request_date,
            request_id=request_id,
            application_sha=application_sha,
        )
        attempt_run_id = str(cfr["radar_run_id"])
        _write_debug(debug_dir, "cfr.json", cfr)
        _commit_and_push(
            history_dir,
            ("data/price-history", "data/run-evidence"),
            f"Persist CFR same-day recovery evidence {attempt_run_id}",
        )
        cfr_persisted = True

        # 5. Reload the durable ref, then perform the guarded FTR transaction.
        _run(("git", "-C", str(history_dir), "pull", "--ff-only", "origin", EVIDENCE_REF))
        ftr = stage_recovery_success(
            history_dir=history_dir,
            run_result_path=history_dir / str(cfr["run_result_path"]),
            requested_date=request_date,
            request_id=request_id,
            application_sha=application_sha,
            generated_at=_now(),
            failed_at=_now(),
        )
        _write_debug(debug_dir, "ftr.json", ftr)
        _commit_and_push(
            history_dir,
            ("data/ftr-feed", "data/run-evidence"),
            f"Record FTR same-day recovery transaction {request_id}",
        )
        if str(ftr.get("status")) != "success":
            raise RecoveryWorkflowError(
                "same_day_recovery_ftr_transaction",
                str(ftr.get("failure_reason") or "guarded FTR recovery transaction failed"),
                attempt_run_id=attempt_run_id,
            )
        return {
            "status": "success",
            "request_id": request_id,
            "radar_run_id": attempt_run_id,
            "application_sha": application_sha,
            "cfr_evidence_persisted_before_ftr": True,
            "publication_dispatched": False,
        }
    except Exception as exc:
        if not claimed:
            raise
        # stage_recovery_success already persisted/committed its own fail-closed
        # result when it returned status=failed.  Do not create a second attempt.
        if isinstance(exc, RecoveryWorkflowError) and exc.stage == "same_day_recovery_ftr_transaction":
            raise

        # Restore exactly the latest durable Git-backed truth.  If CFR evidence
        # was already pushed it survives this reset; if it was not, partial local
        # staging is discarded.  Then record one failure for the claimed request.
        _reset_to_durable_remote(history_dir)
        failure_stage = exc.stage if isinstance(exc, RecoveryWorkflowError) else (
            "same_day_recovery_ftr_process" if cfr_persisted else "same_day_recovery_cfr_persistence"
        )
        failure_run_id = (
            exc.attempt_run_id if isinstance(exc, RecoveryWorkflowError) and exc.attempt_run_id
            else attempt_run_id
            or f"{recovery_run_prefix(request_id)}workflow-{workflow_run_id}"
        )
        failed = stage_recovery_process_failure(
            history_dir=history_dir,
            requested_date=request_date,
            request_id=request_id,
            application_sha=application_sha,
            attempt_run_id=failure_run_id,
            failed_at=_now(),
            failure_stage=failure_stage,
            reason=f"{type(exc).__name__}: {exc}",
        )
        _write_debug(debug_dir, "failure.json", failed)
        _commit_and_push(
            history_dir,
            ("data/ftr-feed", "data/run-evidence"),
            f"Record failed FTR same-day recovery {request_id}",
        )
        raise RecoveryWorkflowError(failure_stage, str(exc), attempt_run_id=failure_run_id) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit unscheduled FTR same-day recovery workflow driver")
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--request-date", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-url", required=True)
    parser.add_argument("--trigger-sha", required=True)
    parser.add_argument("--debug-dir", default="_recovery_debug")
    args = parser.parse_args(argv)
    try:
        result = run_recovery_workflow(
            app_dir=Path(args.app_dir), history_dir=Path(args.history_dir), output_dir=Path(args.output_dir),
            request_date=args.request_date, request_id=args.request_id,
            workflow_run_id=args.workflow_run_id, workflow_run_url=args.workflow_run_url,
            trigger_sha=args.trigger_sha, debug_dir=Path(args.debug_dir),
        )
    except (FTRHandoffError, RecoveryWorkflowError, subprocess.SubprocessError, OSError) as exc:
        print(f"same-day recovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
