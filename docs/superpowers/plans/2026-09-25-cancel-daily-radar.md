# Cancel Daily-Radar Local Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully decommission the on-box OpenChamber `daily-radar` loop so no local acquisition ever triggers again, with `main` left clean.

**Architecture:** Disable already merged (PR #88, `enabled: false` on `main`); remaining work is verify-disabled, user deletes the scheduler card via UI trash (only deletion path the scheduler honors), then box-side cleanup of any resurrected sync branches and final verification.

**Tech Stack:** OpenChamber loop file (`.agents/loops/daily-radar.md`), git, GitHub (`gh`), read-only shell allowlist for polling.

**Spec:** User direction 2026-09-25 ("回去 chatgpt, 操作排程, 取消本機排程") + authoritative loop definition in `.agents/loops/daily-radar.md` + deletion constraint from the `local-scheduling` skill (disk `rm` is resurrected by scheduler two-way sync; deletion only via UI card trash).

## Global Constraints

- Never develop directly on `main`; behavior changes go through branch/PR and merge only on green gates at the exact head commit.
- Never re-run `scripts/local_daily_radar.py` for verification (burns the daily claim; exit 2 / same-day rerun is recovery/no-op only).
- Never `rm` the loop file from disk as the deletion method.
- Box identity is `chatdev-oc`; no `sudo`, no production/trading systems, no secrets in output.

## Review Focus

- Scheduler ignores the file edit and fires 09:00 anyway → Task 1 pins the disabled state on `main`, Task 4 re-checks no new run directory appears after the next 09:00 Asia/Taipei boundary.
- UI deletion resurrects the file plus `test/daily-radar` / `loop/daily-radar` sync branches → Task 3 deletes exactly those if present and verifies `main` contains no other loop files.
- A stale acquisition process is still running during decommission → Task 1 asserts no `local_daily_radar` process exists before declaring done.
- ChatGPT-side schedule double-fires alongside a resurrected local run → Task 4 records the single-owner statement (ChatGPT owns scheduling after this plan).

---

### Task 1: Verify disabled state on main

**Files:**
- Read: `.agents/loops/daily-radar.md:1-7`
- Read: `~/.local/share/cheap-flight-radar/runs/` (run-output root, not the repo)

**Interfaces:**
- Consumes: PR #88 merge commit on `main` (9cd5c8c).
- Produces: Confirmed `enabled: false` on `main`; confirmed no live acquisition process (consumed by Tasks 3-4 as preconditions).

- [ ] **Step 1: Confirm the toggle is on main**

```bash
git checkout main && git pull --ff-only && head -7 .agents/loops/daily-radar.md && git status --short
```

Expected: frontmatter shows `enabled: false`; `git status` shows no modifications to tracked files (untracked `__pycache__`/` .omo/` noise is acceptable).

- [ ] **Step 2: Confirm no acquisition is running and only one loop file exists**

```bash
ps aux | grep -E "local_daily_radar" | grep -v grep || echo "no radar process running"; ls .agents/loops/
```

Expected: prints `no radar process running`; `ls` prints only `daily-radar.md`.

- [ ] **Step 3: Record checkpoint**

Reply one line: "Task 1 done: disabled on main, no live run." Do not commit anything (read-only task).

### Task 2: User deletes the scheduler card via UI trash

**Files:**
- None (human action in the OpenChamber scheduler UI).

**Interfaces:**
- Consumes: Task 1 checkpoint (loop already disabled, so a missed UI step cannot cause a 09:00 fire).
- Produces: User confirmation message "UI card deleted" (consumed by Task 3 as its start trigger).

- [ ] **Step 1 (user): Open the scheduler UI, find the `daily-radar` card, click trash/delete, confirm**

Expected: the `daily-radar` card no longer appears in the UI.

- [ ] **Step 2 (user): Reply with the exact text "UI card deleted"**

Expected: agent proceeds to Task 3 only after this message. If the card cannot be deleted, reply with the UI error text instead and stop (do not attempt disk `rm`).

### Task 3: Box-side cleanup after UI deletion

**Files:**
- Modify (delete only if scheduler resurrected them): `test/daily-radar`, `loop/daily-radar` branches, if present.
- Read: `.agents/loops/` on `main`.

**Interfaces:**
- Consumes: "UI card deleted" confirmation from Task 2.
- Produces: Clean `main` (no loop files, no residual sync branches), branch-deletion log (consumed by Task 4 verification).

- [ ] **Step 1: Sync main and inspect for resurrected state**

```bash
git checkout main && git pull --ff-only && git fetch origin && ls .agents/loops/; echo ---; git branch -a | grep -E "test/daily-radar|loop/daily-radar" || echo "no residual sync branches"
```

Expected: either `.agents/loops/` is empty (clean delete synced) or `daily-radar.md` reappeared (scheduler resurrected it — proceed to Step 2 only for branch cleanup; never `rm` a resurrected file, report it instead).

- [ ] **Step 2: Delete residual sync branches if and only if they exist**

```bash
git push origin --delete test/daily-radar loop/daily-radar 2>/dev/null; git branch -D test/daily-radar loop/daily-radar 2>/dev/null; git branch -a | grep -E "test/|loop/" || echo "sync branches clean"
```

Expected: prints `sync branches clean`. If the push-delete fails with "remote ref does not exist", that is the acceptable clean outcome.

- [ ] **Step 3: Verify main is clean**

```bash
git status --short; echo ---; git log --oneline -3; echo ---; ls .agents/loops/
```

Expected: no modified tracked files; log top is the merge of PR #88 (or a later legitimate commit); loop dir empty or, if resurrected, exactly one reported file.

- [ ] **Step 4: Report the cleanup result**

Reply with: the Step 1 `ls` output, the Step 2 outcome, and either "main clean, decommission complete" or "file resurrected after UI delete, needs owner decision". No commit is made in this task (deletions of remote sync branches are the change; log the commands + output in the reply).

### Task 4: Confirm single-owner scheduling (ChatGPT) and close out

**Files:**
- Read: `~/.local/share/cheap-flight-radar/runs/` (check no post-decommission run appears).

**Interfaces:**
- Consumes: Task 3 "main clean" statement.
- Produces: Final summary reply to the owner; no repo changes.

- [ ] **Step 1: Confirm no new local run fired after decommission**

```bash
ls ~/.local/share/cheap-flight-radar/runs/ | tail -5; date -u
```

Expected: newest entry is `2026-09-25` (today's already-completed canonical run). If run after the next 09:00 Asia/Taipei boundary, also expect no directory newer than 2026-09-25.

- [ ] **Step 2: Send the closing summary**

Reply with exactly: decommission date, "local loop disabled + card deleted + main clean", newest local run date observed, and the single-owner statement "Scheduling is now owned by ChatGPT; the box runs nothing on a timer." If Step 1 shows a newer run directory, do not send the clean summary; report "unexpected post-decommission run on <date>" instead and stop.
