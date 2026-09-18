#!/usr/bin/env python3
"""Local-machine Daily Radar runner (replaces GitHub Actions production path).

Mirrors the retired canonical-production-radar workflow step-for-step, but
against local directories instead of git refs:

  inspect -> claim -> production_runtime acquisition -> stage-success
  -> restore-publication -> local static-site build -> JSON summary on stdout

Concurrency is enforced with a non-blocking flock: a second overlapping run
exits without touching provider state. One canonical live acquisition attempt
per Asia/Taipei day is enforced by the immutable claim file; a repeat run on
the same day is recovery/no-op only and never reacquires.

Operator mode (--request-id) mirrors the retired operator workflow via
operator_operations with an explicit per-intent request identity.

Exit codes: 0 terminal success (fresh acquisition or recovery/no-op),
1 fail-closed operational state, 2 another local run holds the lock.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import io
import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from cheap_flight_radar import operator_operations, production_operations
from cheap_flight_radar import production_publication, production_runtime

TAIPEI = ZoneInfo("Asia/Taipei")
ACQUISITION_TIMEOUT_SECONDS = 5400


def default_local_root() -> Path:
    return Path(os.environ.get("CFR_LOCAL_ROOT", Path.home() / ".local" / "share" / "cheap-flight-radar"))


def today_taipei() -> str:
    return datetime.now(TAIPEI).date().isoformat()


def repo_head_sha() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def run_acquisition_with_timeout(argv: list[str], timeout: int) -> int:
    """Run production_runtime.main in a worker; timeout consumes the claim (fail-closed)."""
    result: dict[str, int] = {}

    def target() -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            result["code"] = production_runtime.main(argv)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return 124
    return result.get("code", 1)


def summarize_run_result(run_result_path: Path) -> dict:
    payload = json.loads(run_result_path.read_text(encoding="utf-8"))
    return {
        "radar_run_id": payload.get("radar_run_id"),
        "run_at": payload.get("run_at"),
        "execution_mode": payload.get("execution_mode", "canonical_daily"),
        "deal_count": payload.get("deal_count"),
        "signal_count": payload.get("signal_count"),
        "provider_health": payload.get("provider_health"),
        "provider_failures": payload.get("provider_failures", []),
        "run_result_path": run_result_path.as_posix(),
    }


def build_site(summary: dict, *, policy: Path, history_dir: Path, publication_dir: Path) -> str:
    manifest_dir = publication_dir / "publication" / "runs"
    site_dir = publication_dir.parent / "site"
    code = production_publication.main([
        "--policy", str(policy),
        "--history-dir", str(history_dir),
        "--manifest-dir", str(manifest_dir),
        "--site-dir", str(site_dir),
    ])
    if code != 0:
        raise RuntimeError("local static-site build failed")
    summary["site_dir"] = site_dir.as_posix()
    return site_dir.as_posix()


def run_canonical(*, args: argparse.Namespace, root: Path, history_dir: Path,
                  publication_dir: Path, run_dir: Path, requested_date: str) -> int:
    state = production_operations.inspect_daily_state(
        history_dir=history_dir, publication_dir=publication_dir, requested_date=requested_date,
    )
    if state.status in ("recover_publication", "published"):
        restored = production_operations.restore_publication_manifest(
            history_dir=history_dir, publication_dir=publication_dir, requested_date=requested_date,
        )
        summary = {
            "mode": "canonical_daily", "requested_date": requested_date,
            "outcome": "recovery_noop_no_reacquisition", "state": asdict(state),
            "restored": restored,
        }
        if state.status == "recover_publication":
            build_site(summary, policy=args.policy, history_dir=history_dir, publication_dir=publication_dir)
        emit(summary)
        return 0
    if state.status != "acquire":
        emit({"mode": "canonical_daily", "requested_date": requested_date,
              "outcome": "fail_closed", "state": asdict(state)})
        return 1

    claimed_at = datetime.now(timezone.utc).isoformat()
    local_run_id = f"local-{os.getpid()}-{datetime.now(TAIPEI).strftime('%Y%m%dT%H%M%S%z')}"
    log_path = run_dir / "local-run.log"
    production_operations.write_daily_claim(
        history_dir=history_dir, requested_date=requested_date, claimed_at=claimed_at,
        workflow_run_id=local_run_id, workflow_run_url=f"file://{log_path}",
        trigger_sha=repo_head_sha(),
    )
    code = run_acquisition_with_timeout([
        "--policy", str(args.policy), "--history-dir", str(history_dir),
        "--output-dir", str(run_dir),
    ], args.timeout)
    if code == 124:
        emit({"mode": "canonical_daily", "requested_date": requested_date,
              "outcome": "acquisition_timeout_claim_consumed_no_retry",
              "timeout_seconds": args.timeout})
        return 1
    if code != 0:
        emit({"mode": "canonical_daily", "requested_date": requested_date,
              "outcome": "acquisition_failed_claim_consumed_no_retry"})
        return 1
    staged = production_operations.stage_success_evidence(
        output_dir=run_dir, history_dir=history_dir, requested_date=requested_date,
    )
    restored = production_operations.restore_publication_manifest(
        history_dir=history_dir, publication_dir=publication_dir, requested_date=requested_date,
    )
    run_result_path = history_dir / staged["run_result_path"]
    summary = {"mode": "canonical_daily", "requested_date": requested_date,
               "outcome": "fresh_acquisition", "staged": staged, "restored": restored,
               **summarize_run_result(run_result_path)}
    build_site(summary, policy=args.policy, history_dir=history_dir, publication_dir=publication_dir)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    emit(summary)
    return 0


def run_operator(*, args: argparse.Namespace, root: Path, history_dir: Path,
                 publication_dir: Path, run_dir: Path, requested_date: str) -> int:
    request_id = args.request_id or ""
    state = operator_operations.inspect_operator_state(
        history_dir=history_dir, publication_dir=publication_dir,
        requested_date=requested_date, request_id=request_id,
    )
    status = state.status if is_dataclass(state) else state["status"]
    if status != "acquire":
        emit({"mode": "operator_reacquisition", "requested_date": requested_date,
              "request_id": request_id, "outcome": "recovery_noop_no_reacquisition",
              "state": asdict(state) if is_dataclass(state) else state})
        return 0
    claimed_at = datetime.now(timezone.utc).isoformat()
    local_run_id = f"local-operator-{os.getpid()}-{datetime.now(TAIPEI).strftime('%Y%m%dT%H%M%S%z')}"
    log_path = run_dir / "local-run.log"
    operator_operations.write_operator_claim(
        history_dir=history_dir, requested_date=requested_date, request_id=request_id,
        claimed_at=claimed_at, workflow_run_id=local_run_id,
        workflow_run_url=f"file://{log_path}", trigger_sha=repo_head_sha(),
    )
    prefix = operator_operations.operator_run_prefix(request_id)
    code = run_acquisition_with_timeout([
        "--policy", str(args.policy), "--history-dir", str(history_dir),
        "--output-dir", str(run_dir), "--run-id-prefix", prefix,
        "--execution-mode", "operator_reacquisition",
    ], args.timeout)
    if code == 124:
        emit({"mode": "operator_reacquisition", "requested_date": requested_date,
              "request_id": request_id, "outcome": "acquisition_timeout_claim_consumed_no_retry",
              "timeout_seconds": args.timeout})
        return 1
    if code != 0:
        emit({"mode": "operator_reacquisition", "requested_date": requested_date,
              "request_id": request_id, "outcome": "acquisition_failed_claim_consumed_no_retry"})
        return 1
    staged = operator_operations.stage_operator_success_evidence(
        output_dir=run_dir, history_dir=history_dir,
        requested_date=requested_date, request_id=request_id,
    )
    restored = operator_operations.restore_operator_publication_manifest(
        history_dir=history_dir, publication_dir=publication_dir,
        requested_date=requested_date, request_id=request_id,
    )
    run_result_path = history_dir / staged["run_result_path"]
    summary = {"mode": "operator_reacquisition", "requested_date": requested_date,
               "request_id": request_id, "outcome": "fresh_acquisition",
               "staged": staged, "restored": restored,
               **summarize_run_result(run_result_path)}
    build_site(summary, policy=args.policy, history_dir=history_dir, publication_dir=publication_dir)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    emit(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-machine Daily Radar runner")
    parser.add_argument("--policy", type=Path, default=REPO_ROOT / "flight-radar.yaml")
    parser.add_argument("--local-root", type=Path, default=default_local_root())
    parser.add_argument("--date", default=None, help="Asia/Taipei date; defaults to today")
    parser.add_argument("--request-id", default=None, help="operator reacquisition identity")
    parser.add_argument("--timeout", type=int, default=ACQUISITION_TIMEOUT_SECONDS)
    parser.add_argument("--history-dir", type=Path, default=None)
    parser.add_argument("--publication-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    requested_date = args.date or today_taipei()
    if requested_date != today_taipei():
        emit({"outcome": "refused_stale_or_future_date",
              "requested_date": requested_date, "today_taipei": today_taipei()})
        return 1

    root = args.local_root
    history_dir = args.history_dir or root / "history"
    publication_dir = args.publication_dir or root / "publication"
    stamp = datetime.now(TAIPEI).strftime("%Y%m%dT%H%M%S%z")
    mode = "operator" if args.request_id else "canonical"
    run_dir = root / "runs" / requested_date / f"{stamp}-{mode}"
    run_dir.mkdir(parents=True, exist_ok=True)

    lock_path = root / "locks" / "daily.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_file = lock_path.open("w")
    except OSError as exc:
        emit({"outcome": "lock_unavailable", "error": str(exc)})
        return 1
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        emit({"outcome": "another_local_run_active_no_overlap"})
        return 2
    try:
        if args.request_id:
            return run_operator(args=args, root=root, history_dir=history_dir,
                                publication_dir=publication_dir, run_dir=run_dir,
                                requested_date=requested_date)
        return run_canonical(args=args, root=root, history_dir=history_dir,
                             publication_dir=publication_dir, run_dir=run_dir,
                             requested_date=requested_date)
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
