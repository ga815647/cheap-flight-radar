import json
from pathlib import Path
from unittest import mock

from cheap_flight_radar.canonical_ftr_runtime import stage_canonical_process_failure, stage_canonical_success
from cheap_flight_radar.ftr_recovery import (
    recovery_run_prefix,
    stage_recovery_cfr_success_evidence,
    stage_recovery_success,
    write_recovery_claim,
)

DAY = "2026-08-20"
APP_SHA = "b" * 40
CANONICAL_SHA = "a" * 40
REQUEST_ID = "repair-20260820-a"


def execution_row(attempts=0, records=0, successes=0, failures=0):
    return {"attempts": attempts, "provider_calls": attempts, "records": records,
            "successes": successes, "empty": 0, "failures": failures,
            "suppressed": 0, "unsupported": 0}


def healthy_execution():
    return {
        "flight_deals": execution_row(4, 4, 4), "explore": execution_row(4, 4, 4),
        "conventional_exact": execution_row(1, 1, 1), "flexible_dates": execution_row(),
        "mixed_taiwan_return": execution_row(), "open_jaw": execution_row(),
    }


def healthy_origins():
    return {a: {"status": "attempted", "returned_flight_deals": 1, "explore_seeds": 1, "errors": []}
            for a in ("TPE", "TSA", "RMQ", "KHH")}


def run_result(run_id, *, mode=None, health="healthy", origins=None, execution=None):
    record = {
        "record_id": "deal-kix", "provider": "gflights", "surface": "exact",
        "origin": {"iata": "TPE", "city": "Taoyuan", "country": "Taiwan"},
        "destination": {"iata": "KIX", "city": "Osaka", "country": "Japan"},
        "legs": [{"origin": "TPE", "destination": "KIX", "date": "2026-10-05",
                  "departure_time": "08:00+08:00", "arrival_time": "12:00+09:00"}],
        "reproducible_search": {"return_date": "2026-10-09"},
        "current_price_twd": 5000, "observed_at": f"{DAY}T10:00:00+08:00",
        "verification_state": "revalidated", "evidence_class": "qualified_round_trip_deal",
        "complete_airfare": True, "airlines": ["Example Air"], "evidence_url": "https://example.invalid/evidence",
    }
    reasons = [] if health == "healthy" else ["fixture degradation"]
    payload = {
        "radar_run_id": run_id, "run_at": f"{DAY}T10:00:00+08:00",
        "deals": [{"classification": "Deal", "state": "deal", "observation_id": "obs-deal-kix",
                   "current_complete_airfare_twd": 5000, "discovery": record, "exact": record}],
        "signals": [], "ftr_absolute_low_non_deals": [],
        "coverage": {
            "origins": origins or healthy_origins(),
            "markets": {name: {"discovered": 1, "qualified": 0, "revalidated": 0, "deals": 0}
                        for name in ("japan", "korea", "china", "other_asia_oceania")},
            "execution": execution or healthy_execution(), "all_origins_attempted": True,
            "destination_scope": "asia_oceania",
            "provider_health": {"status": health, "technical_failure_count": 0 if health == "healthy" else 1,
                                "reasons": reasons}},
        "provider_health": {"status": health, "technical_failure_count": 0 if health == "healthy" else 1,
                            "reasons": reasons},
        "provider_failures": [],
    }
    if mode: payload["execution_mode"] = mode
    return payload


class RecoveryFixtureMixin:
    def canonical_success(self):
        payload = run_result("production-radar-20260820T080000+0800")
        path = self.history / "data/run-evidence/2026/08/20" / payload["radar_run_id"] / "run-result.json"
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        result = stage_canonical_success(
            history_dir=self.history, run_result_path=path, producer_commit_sha=CANONICAL_SHA,
            attempt_run_id=payload["radar_run_id"], requested_date=DAY,
            generated_at=f"{DAY}T08:05:00+08:00", failed_at=f"{DAY}T08:05:00+08:00")
        self.assertEqual(result["status"], "success"); return result

    def activate_repair(self, with_last_good=True):
        baseline = self.canonical_success() if with_last_good else None
        failure = stage_canonical_process_failure(
            history_dir=self.history, requested_date=DAY, attempt_run_id="canonical-attempt-20260820-failed",
            producer_commit_sha=CANONICAL_SHA, failed_at=f"{DAY}T09:00:00+08:00", reason="fixture canonical failure")
        return baseline, failure

    def claim(self, request_id=REQUEST_ID):
        return write_recovery_claim(
            history_dir=self.history, requested_date=DAY, request_id=request_id, application_sha=APP_SHA,
            claimed_at=f"{DAY}T09:30:00+08:00", workflow_run_id="9001",
            workflow_run_url="https://example.invalid/runs/9001", trigger_sha="control-sha", current_date=DAY)

    def recovery_output(self, request_id=REQUEST_ID, payload=None):
        run_id = f"{recovery_run_prefix(request_id)}20260820T100000+0800"
        payload = payload or run_result(run_id, mode="same_day_recovery"); run_id = payload["radar_run_id"]
        history_rel = f"data/price-history/2026/08/20/{run_id.replace('+', '-')}.json"
        snap = self.output / "history" / history_rel; snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({"schema_version": 1, "radar_run_id": run_id, "run_at": payload["run_at"], "observations": []}) + "\n", encoding="utf-8")
        manifest = self.output / "publication/runs" / f"{run_id}.json"; manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"schema_version": 2, "radar_run_id": run_id, "run_at": payload["run_at"],
                                        "history_snapshot_path": history_rel, "execution_mode": "same_day_recovery",
                                        "deals": [], "signals": [], "coverage": payload["coverage"],
                                        "provider_failures": payload["provider_failures"]}) + "\n", encoding="utf-8")
        (self.output / "run-result.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def stage_cfr(self, request_id=REQUEST_ID, payload=None):
        self.recovery_output(request_id, payload)
        return stage_recovery_cfr_success_evidence(
            output_dir=self.output, history_dir=self.history, requested_date=DAY,
            request_id=request_id, application_sha=APP_SHA)

    def stage_ftr(self, staged, request_id=REQUEST_ID):
        with mock.patch("cheap_flight_radar.ftr_recovery._today_local", return_value=DAY):
            return stage_recovery_success(
                history_dir=self.history, run_result_path=self.history / staged["run_result_path"],
                requested_date=DAY, request_id=request_id, application_sha=APP_SHA,
                generated_at=f"{DAY}T10:05:00+08:00", failed_at=f"{DAY}T10:05:00+08:00")
