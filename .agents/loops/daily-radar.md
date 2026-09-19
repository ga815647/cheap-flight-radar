---
name: daily-radar
schedule: "0 9 * * *"
enabled: true
model: opencode/muse-spark-1.3-contributor-free
timezone: Asia/Taipei
---
Run the canonical Daily Radar for Cheap Flight Radar on this machine (no GitHub Actions; see flight-radar.yaml orchestration.local_runtime).

Rules: never ask the user any question and never wait for approval — decide everything yourself from policy and finish with a summary. Never touch main. Never retry a killed or timed-out acquisition by rerunning the script blindly: check state first (a claim without a snapshot means today is burned; report it and finish).

1. Run from /home/chatdev-oc/projects/cheap-flight-radar, DETACHED in background (the acquisition runs up to 90 minutes; a foreground call will be killed by the tool timeout and burn today's claim):
   nohup python3 scripts/local_daily_radar.py > ~/.local/share/cheap-flight-radar/runs/cfr-daily-$(date +%Y%m%d).log 2>&1 & echo "launcher pid=$!"
   (uses CFR_LOCAL_ROOT or ~/.local/share/cheap-flight-radar for history,
   publication, runs and the single-flight lock. Keep the launcher log inside
   that allowlisted root — do NOT use /tmp, which triggers a manual
   external_directory approval and breaks unattended runs.)
2. Poll about once a minute, preferring the read/glob tools over bash (e.g. check whether
   summary.json appeared under the newest runs/<today>/ directory, or whether
   the launcher pid is still alive via `ps -p <pid>` or `kill -0 <pid>`). If bash
   is needed, use only the allowlisted read-only commands (ls, cat, tail, head,
   ps, date, echo, test, kill -0). Do not run the script a second time:
   exit 2 means another run holds the lock (report and finish); a repeat run
   the same day is recovery/no-op only and never reacquires.
3. When summary.json appears, read the run-result JSON at its run_result_path
   and decide notification per PRODUCT_INTENT.md: notify on meaningful new
   Deals or on operational/provider/coverage failure; stay silent on a healthy
   run with no meaningful change.
4. Reply with a short summary: date, provider health, Deal count, and either
   the Deal table (route, dates, fare, anomaly vs typical) or one line saying
   the market is ordinary. An explicit same-day refresh needs a new
   --request-id: python3 scripts/local_daily_radar.py --request-id <id>.
