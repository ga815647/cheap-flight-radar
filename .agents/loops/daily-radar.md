---
name: daily-radar
schedule: "0 9 * * *"
enabled: true
model: opencode/muse-spark-1.3-contributor-free
timezone: Asia/Taipei
---
Run the canonical Daily Radar for Cheap Flight Radar. Work in /home/chatdev-oc/projects/cheap-flight-radar on branch ops/radar-request (force-reset from current main first; a reset with no request file means no acquisition is due).

1. Compute today's Asia/Taipei date (YYYY-MM-DD) and write requests/daily.json:
   {"schema_version": 1, "mode": "canonical_daily", "requested_date": "<today>"}.
   Push the control branch (SSH remote is configured; never touch main).
2. Wait for the triggered Canonical production Radar workflow to reach a terminal state.
3. Read the final immutable evidence: pre-acquisition claim, price-history snapshot,
   run-result, recovery manifest, and the active publication manifest.
4. Decide notification per PRODUCT_INTENT.md: notify on meaningful new Deals or on
   operational/provider/coverage failure; stay silent on a healthy run with no
   meaningful change. A retry of today's request is recovery/no-op only and must
   never start a second automatic canonical acquisition.
5. Reply with a short summary: date, provider health, Deal count, and either the
   Deal table (route, dates, fare, anomaly vs typical) or one line saying the
   market is ordinary. Never merge anything; orchestration only.
