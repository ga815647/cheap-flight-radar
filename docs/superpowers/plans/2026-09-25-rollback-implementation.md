# Rollback to ChatGPT Operation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore ChatGPT-triggered GitHub Actions operation with JSON-direct history promoted to primary typical-price, in one policy-change PR.

**Architecture:** Single branch `ops/rollback-chatgpt` from `main`: validate
backfill sources read-only first, restore the 5 retired workflows verbatim,
apply the SSOT deltas, commit backfill data + revived trigger + instructions,
update the policy-guard tests, keep the gate green throughout, merge once,
prove with the first ChatGPT-triggered run.

**Tech Stack:** Python 3.12, existing `cheap_flight_radar.price_history` /
`production_radar` / `publication` modules, GitHub Actions (restored yamls),
git-committed `data/` trees, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-09-25-rollback-chatgpt-design.md`
(PR #89 — merge it first in Task 1; the plan argues from the spec, executors
read both).

## Global Constraints

- Never develop directly on `main`; all work on `ops/rollback-chatgpt`, one PR.
- Merge only with `PYTHONPATH=src python3 -m unittest discover -s tests` green
  (272 tests) on the exact head commit; never merge red.
- One canonical acquisition attempt per Taipei day: never run
  `scripts/local_daily_radar.py` or trigger workflows to "verify" (burns the
  claim); verification is read-only evidence inspection + unit tests.
- No synthetic backfill, no imputation, no new secrets, no observation-source
  changes, no Neon/SQLite.
- Do not `git checkout -- .` or switch branches casually while the loop-file
  deletion is uncommitted: checking out `main` resurrects
  `.agents/loops/daily-radar.md` on disk (observed 2026-09-25). The deletion is
  committed inside Task 2; until then stay on the work branch.

## Review Focus

- An old snapshot passes `snapshot_from_json` but carries a different
  methodology (e.g. non-complete-trip fare scope) and silently skews a window
  median → Task 1 pins the fare-scope/availability inventory per file and Task 4
  excludes anything outside `usable_complete_trip`/`available`.
- Restored workflow writes evidence to a different root than §2 readers expect
  → Task 2 pins the path-equality check between restored yamls and the §2
  contract before any other change.
- `github_actions_is_not_durable_history_service: true` survives the SSOT edit
  and contradicts the git-tree store → Task 3 flips it explicitly with the
  decision recorded in the commit message.
- `chatgpt-instructions.md` exceeds the 2000-char budget or smuggles build/SQL
  details → Task 4 counts characters and strips to the trigger contract only.
- A backfilled file duplicates a `radar_run_id` already present (local 09-18
  vs git era overlap) → Task 1 builds the run-id registry; Task 4 refuses
  duplicates (first-write-wins, second is excluded and listed).

---

### Task 1: Backfill source validation (read-only)

**Files:**
- Read: git history (`2f3e131^` trees, 27 canonical + operator evidence commits
  2026-08-15～09-10), `{CFR_LOCAL_ROOT}/history/data/price-history/**` (8 local days).
- Create: `docs/superpowers/plans/2026-09-25-rollback-implementation.md` (this file, already exists).
- Test: throwaway validation script output (not committed).

**Interfaces:**
- Consumes: spec §4 scope.
- Produces: validated file list + per-destination-bucket sample inventory
  (pasted into the Task 4 commit message and PR body; consumed by Task 4).

- [ ] **Step 1: Merge the spec PR after checking its head is docs-only**

```bash
gh pr view 89 --json headRefOid --jq .headRefOid; git checkout main && git pull --ff-only
```

Expected: PR #89 head contains only the spec file; `main` fast-forwards cleanly.
Then merge PR #89 (docs-only; run the gate once on the result in Step 2).
Do not proceed if the head contains anything else.

- [ ] **Step 2: Cut the work branch and confirm the gate is green at base**

```bash
git checkout -b ops/rollback-chatgpt && PYTHONPATH=src python3 -m unittest discover -s tests 2>&1 | grep -E "^(OK|FAILED|Ran )"
```

Expected: `Ran 272 tests` + `OK`. (The 2 known `LocalRunnerPolicyTest` errors
appear only after the loop-file deletion lands in Task 2; at base the file is
present on disk, so the gate is green. If it is not green here, stop and report.)

- [ ] **Step 3: Inventory old evidence commits**

```bash
git log --format="%h %ad" --date=short --all --grep="Persist canonical Radar evidence" | wc -l
git log --format="%h %ad %s" --date=short --all --grep="Persist .* Radar evidence" | sort -k2 | head -40
```

Expected: ~27 canonical lines 2026-08-15～09-10 plus operator lines in the same
span. Record the exact SHAs; any commit outside the span is out of scope.

- [ ] **Step 4: Validate every candidate snapshot through the real loader**

```bash
PYTHONPATH=src python3 -c "
import subprocess, json
from cheap_flight_radar.price_history import snapshot_from_json
files = subprocess.check_output(['git','log','--format=%H','--all','--grep=Persist .* Radar evidence'],text=True).split()
names = set(); bad = []; scopes = set(); states = set()
for sha in files:
    lst = subprocess.check_output(['git','show',sha,'--name-only','--format='],text=True).split()
    for f in lst:
        if 'price-history' in f and f.endswith('.json') and f not in names:
            names.add(f)
            try:
                s = snapshot_from_json(subprocess.check_output(['git','show',sha+':'+f],text=True))
                assert s.schema_version == 1 and len(s.observations) > 0
                for o in s.observations:
                    scopes.add(o.fare_scope); states.add(o.availability_state)
            except Exception as e:
                bad.append((f, repr(e)))
print('candidate snapshots:', len(names)); print('rejected:', bad)
print('fare_scopes:', sorted(scopes)); print('availability_states:', sorted(states))
"
```

Expected: a count (≈27+operator) and an explicit rejected list. Every rejected
file stays out of Task 4; the list goes into the PR body.

- [ ] **Step 5: Commit nothing; report the inventory**

Reply: validated count, rejected list (or "none"), and the run-id registry
(`radar_run_id` per file, proving no duplicates yet). This task changes no
tracked files.

### Task 2: Restore the 5 retired workflows + record the loop deletion

**Files:**
- Restore: `.github/workflows/canonical-production-radar.yml`,
  `.github/workflows/canonical-production-radar-test.yml`,
  `.github/workflows/operator-production-radar.yml`,
  `.github/workflows/radar-pages.yml`,
  `.github/workflows/radar-pages-isolated-test.yml` (from `2f3e131^`).
- Delete (record): `.agents/loops/daily-radar.md` (already absent on disk).
- Test: `python3 -c "import yaml,..."` parse check per restored file + gate.

**Interfaces:**
- Consumes: work branch from Task 1.
- Produces: restored workflows + committed loop deletion (consumed by Tasks 3-5
  as the branch base).

- [ ] **Step 1: Restore verbatim and prove the history root matches §2**

```bash
git checkout 2f3e131^ -- .github/workflows/canonical-production-radar.yml .github/workflows/canonical-production-radar-test.yml .github/workflows/operator-production-radar.yml .github/workflows/radar-pages.yml .github/workflows/radar-pages-isolated-test.yml
grep -h -E "data/(price-history|run-evidence)|history" .github/workflows/canonical-production-radar.yml .github/workflows/operator-production-radar.yml | sort -u
```

Expected: 5 files restored; grep shows repo-root `data/` trees (the evidence
commits prove this layout). If any workflow points elsewhere, adapt that line
to §2 and call it out in the commit message; otherwise restore-verbatim stands.

- [ ] **Step 2: Commit the loop-file deletion (supersedes PR #90)**

```bash
git rm .agents/loops/daily-radar.md 2>/dev/null || true; git status --short | grep -v "^??"; ls .agents/loops/ 2>/dev/null || echo "loops dir empty/absent"
```

Expected: the deletion is staged (file already absent on disk). If the file
reappeared (branch switch side effect), `git rm` stages the removal and the
disk stays clean — do not restore it.

- [ ] **Step 3: Commit Task 2 as one commit**

```bash
git add .github/workflows && git commit -m "Restore retired production workflows; record loop-file deletion
Workflows restored verbatim from 2f3e131^; history root verified as
repo-root data/ trees per spec section 2. Loop file deletion records the
scheduler-UI card removal (supersedes PR #88 follow-up)."
```

Expected: one commit, only workflow files + the deletion. Then close PR #90
as superseded with `gh pr close 90 --comment "Superseded: deletion lands in the rollback PR."`

- [ ] **Step 4: Run the gate, expect exactly the 2 known errors**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `Ran 272`, `FAILED (errors=2)`, both in `LocalRunnerPolicyTest`
(loop-file guards). Any other failure → stop and report; Task 3 fixes these two.

### Task 3: SSOT deltas + policy-guard test updates (gate back to green)

**Files:**
- Modify: `flight-radar.yaml` (`price_history.role`, new
  `primary_typical_price_source` rule, `persistence.durable_store`,
  `history_root_absent_action`, `github_actions_is_not_durable_history_service`,
  `orchestration.primary_scheduler` + restored orchestration blocks from
  `2f3e131^:flight-radar.yaml`).
- Modify: `tests/test_local_daily_radar.py` (`LocalRunnerPolicyTest` loop-file
  assertions → new-contract assertions; `test_production_github_workflows_are_retired`
  → assert the 5 restored workflows exist).
- Test: full gate must be green.

**Interfaces:**
- Consumes: Task 2 branch state.
- Produces: coherent SSOT + green gate (consumed by Task 5 merge).

- [ ] **Step 1: Diff the pre-decoupling SSOT blocks for reference (read-only)**

```bash
git show 2f3e131^:flight-radar.yaml | grep -n -A12 "primary_scheduler\|durable_store\|history_root_absent_action" | head -60
```

Expected: the old values to restore (record them in the commit message).

- [ ] **Step 2: Edit `flight-radar.yaml`**

Replace `price_history.role` with
`primary_history_baseline_with_external_fallback`; add the
`primary_typical_price_source` rule exactly as spec §3 (history baseline when
`selected_baseline_twd` non-null and confidence in low/medium/high, else
external priority order); restore the pre-decoupling `persistence`/`orchestration`
values; set the durable-store/history-root flags for the git-tree store with the
decision recorded. Keep `required_for_formal_deal: false`,
`synthetic_backfill: forbidden`, `never_impute_missing_window` untouched.

- [ ] **Step 3: Update the two guard tests to the new contract**

In `tests/test_local_daily_radar.py`: replace loop-file reads with assertions
that (a) `.agents/loops/daily-radar.md` does not exist, (b) SSOT
`primary_scheduler` is the restored trigger value, (c) the 5 workflow files
exist. Keep all behavior tests (`LocalRunnerBehaviorTest`) untouched.

- [ ] **Step 4: Run the gate, expect green**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests 2>&1 | grep -E "^(OK|FAILED|Ran )"
```

Expected: `Ran 272 tests` + `OK`. If red, fix forward on this branch; never
merge red.

- [ ] **Step 5: Commit Task 3 as one commit**

```bash
git add flight-radar.yaml tests/test_local_daily_radar.py && git commit -m "Repoint SSOT to GitHub trigger; promote history baseline; update guard tests
<old→new values from Step 1>; promotion rule per spec section 3; guard tests
now assert absence of the local loop and presence of the 5 workflows. Gate: 272 OK."
```

### Task 4: Backfill data + trigger revival + instructions

**Files:**
- Add: validated snapshots → `data/price-history/**`, `data/run-evidence/**`
  (canonical 27 + operator span + 8 local, byte-identical copies).
- Modify: `docs/daily-flight-radar-automation-prompt.md` (lift retirement for
  the restored flow: control branch `ops/radar-request`, `requests/daily.json`
  `schema_version: 1`, one claim per day, submission-is-not-completion).
- Create: `chatgpt-instructions.md` (repo root, ≤2000 Unicode chars, trigger
  contract only).
- Test: re-run Task 1 Step 4 loader over the committed trees + `wc -m` the
  instructions file.

**Interfaces:**
- Consumes: Task 1 validated list + run-id registry; Task 3 branch state.
- Produces: complete data + docs (consumed by Task 5 PR/merge).

- [ ] **Step 1: Commit the backfill, duplicates refused**

Copy each validated file to its identical repo-root path; skip any
`radar_run_id` already present (first-write-wins; list skips in the commit
message). Then:

```bash
PYTHONPATH=src python3 -c "
from pathlib import Path
from cheap_flight_radar.price_history import snapshot_from_json
files = sorted(Path('data/price-history').rglob('*.json'))
ids = set(); dup = []
for f in files:
    s = snapshot_from_json(f.read_text(encoding='utf-8'))
    if s.radar_run_id in ids: dup.append(s.radar_run_id)
    ids.add(s.radar_run_id)
print('snapshots:', len(files), 'unique runs:', len(ids), 'dupes:', dup)
"
```

Expected: snapshots ≈ validated count + 8 local, dupes `[]`. Commit with the
per-destination sample note from Task 1.

- [ ] **Step 2: Revive the trigger prompt doc and write instructions**

Un-retire `docs/daily-flight-radar-automation-prompt.md` for the restored flow
(keep the history section, replace the retirement notice with the restored
contract). Write `chatgpt-instructions.md` (repo root): trigger steps, claim
discipline, read-back-before-notify rule, notification policy; no build
commands, no SQL, no deploy todos. Then:

```bash
python3 -c "print(len(open('chatgpt-instructions.md',encoding='utf-8').read()))"
```

Expected: number printed ≤ 2000. If over, cut scope (never the claim/read-back
rules) until it fits. Commit docs + instructions as one commit.

- [ ] **Step 3: Run the gate again, expect green**

Same command as Task 3 Step 4. Data files must not affect unit tests; if red,
the cause is unrelated to data — investigate, do not delete data to force green.

### Task 5: PR, merge, proof, closeout

**Files:**
- None (process task; reads run evidence).

**Interfaces:**
- Consumes: Tasks 1-4 branch state.
- Produces: merged rollback + proof summary reply.

- [ ] **Step 1: Push and open the PR with the exact head**

```bash
git push -u origin ops/rollback-chatgpt && git rev-parse HEAD
```

Then `gh pr create` with body containing: head SHA, Task 1 inventory
(validated/rejected counts), SSOT old→new table, gate result, backfill scope.
Expected: PR URL.

- [ ] **Step 2: Verify head == tested head, then merge**

```bash
gh pr view <N> --json headRefOid --jq .headRefOid; git rev-parse HEAD
```

Expected: identical SHAs and green gate from Task 4 Step 3 on that SHA. Then
`gh pr merge <N> --merge`, `git checkout main`, `git pull --ff-only`.
(Note: switching branches may resurrect the loop file on disk if any ref still
tracks it — after merge no ref tracks it; verify with `ls .agents/loops/`.)

- [ ] **Step 3: Hand the trigger to the owner (no verification run by agent)**

Reply: merge SHA, backfill totals, and the handoff — owner pastes
`chatgpt-instructions.md` into ChatGPT Project settings, confirms "installed",
and lets the next scheduled ChatGPT automation fire the first canonical run.
The agent runs no acquisition and triggers no workflow.

- [ ] **Step 4: Confirm the first canonical run from evidence (next day)**

After the owner reports the first ChatGPT-triggered run, inspect read-only:
new `data/price-history/<date>/` snapshot + `data/run-evidence/<date>/` chain
in the repo. Report date, provider health, deal count per the notification
policy. If the run is missing or the chain incomplete, report operational
failure; never trigger a rerun.
