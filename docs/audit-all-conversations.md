# Empirical Audit of 444 Antigravity Transcripts & `/agile-swarm` Benchmark

Generated empirically across **13 isolated Antigravity `.gemini` roots** using [`scripts/audit_transcripts.py`](../scripts/audit_transcripts.py) *(all client repository names, local usernames, and prompt texts anonymized for public release)*.

---

## 1. Machine-Wide Aggregate Metrics (444 Transcripts / 106,004 Steps)

| Metric | Measured Total Across All Chats & Subagents |
|---|---:|
| **Discovered `.gemini` homes** | **13** (Primary profile + 12 isolated IDE profiles) |
| **Non-empty transcripts scanned** | **444** (**16** primary user chats + **428** subagents) |
| **Total logged steps** | **106,004** |
| **Context compactions (`CHECKPOINT`)** | **110** |
| **`run_command` total / sync failures** | **16,329** / **2,057** (`12.6%` failure rate), plus **229** failed & **309** canceled background tasks |
| **`read_file` / `view_file` calls** | **16,746** total (**5,693** = **`34.0%`** redundant `>2x` re-reads of identical files) |
| **`manage_task(status)` polling loops** | **2,888** |
| **`edit_file` / replace calls / errors** | **2,611** / **535** (**`20.5%`** edit mismatch failures) |
| **API / stream `ERROR_MESSAGE` stalls** | **1,066** steps (**672.4 minutes = 11.2 hours** backoff), hitting **211 / 428 (`49.3%`)** of subagents |

### Failure Breakdown Across All 2,057 Failed Commands

| Failure Category | Count | Share of Failures |
|---|---:|---:|
| `test_or_runtime_failure` | 677 | 32.9% |
| `shell_or_syntax_quoting` | 657 | 31.9% |
| `nonzero_exit_other` | 288 | 14.0% |
| `missing_binary_or_path` | 142 | 6.9% |
| `encoding_cp1252` | 111 | 5.4% |
| `missing_file_or_wrong_path` | 83 | 4.0% |
| `git_error` | 67 | 3.3% |
| `docker_or_service_unavailable` | 32 | 1.6% |

---

## 2. Anonymized Summary of All 16 Primary Conversations

| Session | Steps | Checkpoints | Cmds (Fail / Canceled) | Reads (`>2x` Repeat) | Polls | Edits (Err) | API Err (Min) | Stops | Workload Profile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Session #01 | 6,921 | 15 | 1,822 (181 / 26) | 582 (314) | 291 | 149 (59) | 67 (58.0m) | 11 | Electron + Python multi-profile app |
| Session #02 | 6,623 | 15 | 1,995 (165 / 26) | 464 (193) | 147 | 116 (45) | 89 (89.9m) | 5 | TypeScript CLI & report compiler |
| Session #03 | 3,646 | 16 | 713 (139 / 6) | 910 (477) | 231 | 284 (14) | 69 (69.6m) | 6 | Python ETL + PostgreSQL Docker CI + Harness build |
| Session #04 | 3,142 | 6 | 371 (39 / 6) | 620 (417) | 160 | 267 (62) | 80 (43.2m) | 1 | Flutter multi-screen UI sprint |
| Session #05 | 2,875 | 6 | 557 (51 / 16) | 510 (420) | 71 | 140 (4) | 16 (9.9m) | 2 | Python migration & web dashboard |
| Session #06 | 2,513 | 5 | 570 (69 / 25) | 265 (161) | 63 | 146 (6) | 18 (9.7m) | 4 | Built-in `/teamwork` Python codebase audit |
| Session #07 | 2,492 | 5 | 801 (76 / 14) | 174 (72) | 66 | 20 (7) | 20 (9.7m) | 2 | Python GUI tool `/boost` audit |
| Session #08 | 2,307 | 5 | 676 (69 / 22) | 162 (51) | 54 | 11 (1) | 11 (8.1m) | 1 | Cross-platform launcher debugging |
| Session #09 | 1,836 | 3 | 503 (78 / 10) | 140 (92) | 69 | 65 (13) | 29 (12.8m) | 1 | Flutter + Python mobile helper |
| Session #10 | 1,817 | 5 | 328 (15 / 1) | 222 (76) | 73 | 42 (6) | 22 (22.7m) | 1 | Built-in `/teamwork` Flutter feature sprint (400 setup steps before code; 7 workers in `inherit`) |
| Session #11 | 1,239 | 2 | 248 (35 / 7) | 238 (128) | 50 | 33 (0) | 5 (1.0m) | 0 | Flutter desktop UI bugfix |
| Session #12 | 328 | 0 | 88 (8 / 2) | 19 (1) | 19 | 5 (0) | 1 (2.5m) | 0 | Python ML repo analysis |
| Session #13 | 253 | 0 | 15 (0 / 0) | 34 (1) | 0 | 3 (2) | 5 (4.2m) | 2 | Flutter UI component slice |
| Session #14 | 110 | 0 | 24 (2 / 2) | 20 (3) | 21 | 0 (0) | 0 (0.0m) | 0 | Git sync & architecture review |
| Session #15–#16 | 2 each | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Minimal greeting sessions |

---

## 3. Problem-to-Fix Mapping Implemented in `gravity-harness-fix`

| Recurring Failure Observed | Frequency | Deterministic / Harness Fix Applied |
|---|---:|---|
| **`manage_task(status)` polling loops** | **2,888** polls | `PreToolUse` hard-blocks repeat polls (`polling_loop_blocked`) |
| **Multiline `python -c` / `node -e` / quoting crashes** | **657** failures | `PreToolUse` blocks multiline inline scripts and PowerShell->WSL quote bombs (`inline_quoting_blocked`) |
| **Windows `cp1252` `UnicodeEncodeError`** | **111** failures | `install.bat` sets User `PYTHONIOENCODING=utf-8` & `PYTHONUTF8=1` + hooks run `python -X utf8` |
| **Blind `edit_file` target-mismatch retries** | **535** errors | `PostToolUse` tracks failed edit targets; `PreToolUse` hard-blocks retry until file is re-read (`blind_edit_retry_blocked`) |
| **Redundant `read_file` thrashing** | **5,693** extra reads | `PreToolUse` blocks identical `(path, start, end)` re-reads `<90s` (`duplicate_read_blocked`) + logs `read_thrash` warnings |
| **Parallel write subagents colliding in `inherit`** | **7** workers/run in `/teamwork` | `PreToolUse` blocks concurrent non-`research` subagents with `Workspace='inherit'`, requiring `Workspace='share'` (`parallel_inherit_subagent_blocked`) |
| **Built-in `/teamwork` slow ceremony** | **400** zero-code setup steps (Session #10) | `/agile-swarm` Plan B skill (`<= 3` concurrent `Workspace="share"` workers, disjoint file ownership, fast targeted tests) + `worktree_team.py` |
| **Missing `uv` PATH in WSL2 & blind env probing** | **142** missing binaries | `install_harness.py` updates WSL `~/.bashrc` + `~/.profile`; `SessionStart` injects OS/Docker/`uv` state |
| **High subagent API error death rate (`49.3%`)** | **211 / 428** subagents | `PreToolUse` prompts on 4th subagent inside 2 min (`subagent_flood_prompt`) |
| **Heavy 3,000+ step bloated chats** | **110** checkpoints | `PostToolUse` flags `long_session_bloat` every 300 steps + `rules/AGENTS.md` enforces short per-PR slices |

---

## 4. Operational Benchmark: `/agile-swarm` 10-Page Flutter App (`PulseHub`)

Measured live on a clean greenfield **10-screen Flutter Material 3 application** (Dashboard, Projects, Project Detail, Kanban Tasks Board, Analytics, Team Chat, Notifications, Editable Profile, Wallet & Invoices, Settings & Security) built on a single Antigravity account:

| Benchmark Metric | Result |
|---|---:|
| **Total wall-clock time (`flutter create` -> E2E merge & verified)** | **`12.3` minutes** |
| **Parallel worker burst duration (3 concurrent `agile-worker`s on `Workspace="share"` + separate `git worktree`s)** | **`4.38m` / `4.75m` / `5.95m`** |
| **Total Dart code produced across 19 files** | **`5,804` lines** (`5,054` `lib/` + `750` `test/`) |
| **Worker diff merged into `main` across 13 slice files** | **`+4,645 / -26` lines**, **`0` merge conflicts** |
| **Worker step efficiency (`Worker-1 / Worker-2 / Worker-3`)** | **`51` / `53` / `64` steps** (`0` polling loops, `1` total redundant read, `0.0` min API backoff) |
| **Final static analysis & test suite (`flutter analyze` + `flutter test`)** | **`No issues found! (1.4s)`**, **`11/11` widget & E2E tests pass (`3s`)** |
