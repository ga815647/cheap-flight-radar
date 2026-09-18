---
name: daily-radar
schedule: "0 9 * * *"
enabled: true
model: opencode/muse-spark-1.3-contributor-free
timezone: Asia/Taipei
---
Run the canonical Daily Radar for Cheap Flight Radar on this machine (no GitHub Actions; see flight-radar.yaml orchestration.local_runtime).

1. Run from /home/chatdev-oc/projects/cheap-flight-radar:
   python3 scripts/local_daily_radar.py
   (uses CFR_LOCAL_ROOT or ~/.local/share/cheap-flight-radar for history,
   publication, runs and the single-flight lock; never touch main.)
2. The script prints a JSON summary and exits 0 on terminal success
   (fresh acquisition or recovery/no-op), 1 on fail-closed, 2 when another
   local run holds the lock. A repeat run the same day is recovery/no-op
   only and never reacquires.
3. On success, read the run-result JSON at the printed run_result_path and
   decide notification per PRODUCT_INTENT.md: notify on meaningful new Deals
   or on operational/provider/coverage failure; stay silent on a healthy run
   with no meaningful change.
4. Reply with a short summary: date, provider health, Deal count, and either
   the Deal table (route, dates, fare, anomaly vs typical) or one line saying
   the market is ordinary. An explicit same-day refresh needs a new
   --request-id: python3 scripts/local_daily_radar.py --request-id <id>.
