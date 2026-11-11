---
name: agile-swarm
description: >-
  Fast single-account (Plan B) agile parallel execution workflow inspired by multi-worktree engineering velocity without coordinator or interviewer overhead. Use when the user invokes /agile-swarm, asks to work in parallel / agile / like the employer, or gives a multi-part feature, bugfix wave, or refactor that can split cleanly into 2-3 independent slices and small PRs.
---

# Agile Swarm — Fast Single-Account Parallel Execution (Plan B)

Ship like a parallel engineering team from a **single Antigravity account** without `/teamwork`'s 400-step coordinator/interviewer bottleneck or `Workspace="inherit"` file collisions.

## Rules of Engagement

1. **Zero Coordinator / Interviewer Overhead:** Do NOT invoke built-in `/teamwork`. You (the main agent) act as the lean Tech Lead: split the work in `<2` minutes and launch workers immediately. Only ask the user if an owner-reserved requirement is genuinely blocked.
2. **Respect Plan B API Quota (`<= 3` concurrent workers):** Never spawn `>= 4` coding workers simultaneously on one account (transcript telemetry shows high concurrent bursts cause ~49% subagent stream/API errors). Sweet spot: **2–3 concurrent workers**.
3. **Strict Isolation (`Workspace="share"`):** Every parallel coding subagent MUST run with `Workspace="share"` (Antigravity's native git-worktree mode) on its own branch `agile/<slice-slug>`. NEVER launch parallel code writers with `Workspace="inherit"`. Use `TypeName="research"` + `Model="flash"` for read-only parallel searches.
4. **WS1 vs WS3 Concurrency Gate:**
   - **Disjoint modules/files/screens/tests:** Launch **2–3 parallel Code Workers** (`Workspace="share"`).
   - **Single shared core file or live database/state lock:** Keep **1 Code Writer**, and run **1 parallel Support Worker** (unit test writer, diff reviewer, or research audit) on `Workspace="share"`.
5. **Fast Targeted Tests Inside Slices, Heavy CI Once at Integration:** Slices run `5–30s` unit/widget tests before committing; heavy multi-minute Docker/Postgres gates run once after integration (or in a separate sibling worktree via `./scripts/worktree_team.py`).

---

## Execution Protocol

### Step 1: 60-Second Triage & Slice Contract

Run one quick inspection (`git status --short`, current branch, test runner, changed/target file map) and define a crisp contract for each slice before calling any subagent:

- **Slice Slug & Branch:** `agile/<slice-slug>`
- **Strict File Ownership:** Exact files/directories this worker may create or edit (disjoint across all concurrent workers!).
- **Shared Interface Contract:** Exact function signatures, schemas, CLI flags, route names, or file formats shared across slices.
- **Fast Verification Command:** Exact `5–30s` test command the worker must pass before finishing.

### Step 2: Define Lean Worker & Fan Out (`Workspace="share"`)

Define a minimal custom subagent once per session (so workers do NOT recursively spawn subagents or waste context on unrelated workflows):

- `Name`: `"agile-worker"`
- `EnableWriteTools`: `True`
- `EnableSubagentTools`: `False`
- `SystemPrompt`: Instruct the worker to (a) inspect only target files with `rg -n` / ranged reads, (b) edit strictly within its File Ownership, (c) run only its assigned fast test command, (d) commit cleanly on branch `agile/<slice-slug>` (if in a Git repo), and (e) reply concisely with: **branch name, commit SHA, changed files, and exact test command + observed result**.

Launch **2–3** `invoke_subagent` calls in a **single parallel turn** (`TypeName="agile-worker"`, `Workspace="share"`, `Model="inherit"` — or `Model="flash"` + `TypeName="research"` for parallel diff review / discovery).

**Immediately stop calling tools** after spawning the batch so Antigravity wakes you automatically via `<SYSTEM_MESSAGE>` (never poll `manage_task` or spam `send_message`).

### Step 3: Fast Diff Review & Small-PR Integration

As workers finish:

1. Verify scope & diff from the parent workspace (since `Workspace="share"` shares `.git`, all worker branches exist right in local Git):
   ```sh
   git diff --stat HEAD...agile/<slice-slug>
   ```
2. Spot-check diffs (or launch one `flash` review pass) for regressions, duplicate helpers, broken imports, or out-of-scope edits.
3. **Deliver in Employer Style (choose per user intent):**
   - **Independent Small PRs:** Push each verified slice branch (`git push -u origin agile/<slice-slug>`) and open focused small PRs one by one so the client/reviewer sees rapid progress.
   - **Integrated Feature Branch:** Cleanly `git merge --no-ff agile/<slice-slug>` (or `cherry-pick`) into the main feature branch, resolve interface wiring once, run the integration test suite once, and clean up temporary `agile/*` branches.

---

## Optional Multi-Window / Offloaded-CI Helper

When offloading a slow 15-minute CI gate or opening separate IDE chat tabs manually on clean sibling worktrees, use [worktree_team.py](./scripts/worktree_team.py) (or `agile-worktree.bat` from the `gravity_harnes_fix` root):

```bat
python plugin/skills/agile-swarm/scripts/worktree_team.py create <repo_path> slice-a slice-b wt-ci
python plugin/skills/agile-swarm/scripts/worktree_team.py list <repo_path>
python plugin/skills/agile-swarm/scripts/worktree_team.py cleanup <repo_path>
```

