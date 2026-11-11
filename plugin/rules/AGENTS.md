# Gravity Harness Fix — Always-On Execution & Speed Rules

These global guardrails are active across all conversations via the `gravity-harness-fix` plugin to maximize output velocity, stop wasted steps, and keep live telemetry on recurring agent/environment failures.

## 1. Zero Wasted Steps & Tool Discipline

- **NEVER poll `manage_task(Action="status")` in a loop.** After starting a background task, wait for `<SYSTEM_MESSAGE>` completion (or finish the turn cleanly if idle), or schedule a single timer via `schedule`.
- **No multiline inline quoting bombs.** Any Python or shell logic over 3 lines—especially PowerShell-to-WSL bridges—must be written to a clean `.py`/`.sh` scratch file first and executed as a script file. Never chain fragile nested quotes across `pwsh` -> `wsl bash -c`.
- **UTF-8 by default on Windows.** Assume Windows console defaults to `cp1252`. Ensure `PYTHONIOENCODING=utf-8` or `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` on scripts that touch Unicode/Persian logs or file paths.
- **Batch targeted reads.** Locate symbols/lines with `rg -n` or targeted searches first, then read exact ranges cleanly in parallel batches. Do not repeatedly re-read unchanged files chunk-by-chunk across turns.
- **Match `edit_file` target whitespace cleanly.** If an `edit_file` fails once, inspect exact lines around the target before retrying—never blindly retry the same broken target string.

## 2. Fast Feedback & Safe Heavy Operations

- **Fast targeted tests first, heavy CI gates last.** While iterating on code, run only the targeted test file/case (`5–30s`). Run slow full CI / Docker / PostgreSQL gates only once per milestone or PR checkpoint.
- **Run POSIX/Linux/Docker tools in native WSL2/Linux.** Do not waste minutes running POSIX-dependent test suites on Windows where they fail slowly. Verify Docker/DB readiness before starting long runs.
- **Protect live data & exports.** Never trigger unbounded full-table exports, large directory hashing, or destructive operations on live/production DBs without explicit `--run-id`, `--limit`, dry-run validation, or prior confirmation.
- **Right-size conversations & use Plan B `agile-swarm` for parallel work.** Long multi-hour single chats cause frequent context compactions and repeated file reads. Do not invoke built-in `/teamwork` coordinator/interview loops or concurrent `Workspace: "inherit"` writers; use the `agile-swarm` skill (`<= 3` concurrent workers via `Workspace: "share"`, disjoint file ownership, fast targeted tests, commit per slice branch).

## 3. Continuous Problem Telemetry & Reporting

- Lifecycle hooks in this plugin automatically record tool errors, quoting crashes, polling attempts, read thrashing, `edit_file` mismatches, slow commands, API retries, and premature stops into the shared `gravity-harness-fix` log directory.
- When an unrecognized recurring friction occurs during a session—or when the user asks to inspect problems, audit past transcripts, or update harness fixes—activate the `gravity-session-doctor` skill to inspect the logs and propose a permanent fix in the harness repo.

## 4. Pro Engineering Lifecycle Slash Commands (`/pro-dev` Suite)

- Use **`/pro-dev`** as the unified orchestrator across complex tasks, or invoke focused slash skills directly on demand (loaded lazily via progressive disclosure):
  - **`/repo-onboard`**: Discover unknown repos & maintain `.agents/memory/PROJECT_INTELLIGENCE.md`.
  - **`/forensic-audit`**: Isolated worktree audit across 14 domains + standalone interactive `PROJECT_AUDIT_REPORT.html`.
  - **`/harden-fix`**: Category A/B/C triage, root-cause fixes, `/agile-swarm` parallel slices, second-pass audit.
  - **`/lossless-modularize`**: Zero-loss SOLID split of large files verified by `conservation_audit.py` (`<= 400` lines).
  - **`/figma-to-prod`**: Figma MCP -> Flutter or React+TS UI, centralized raw `.svg` preservation, state safety (`verify_figma_ui.py`).
  - **`/truthful-readme`**: Evidence-verified README, Mermaid diagrams, AI map & broken-link gate (`verify_readme.py`).
  - **`/agile-swarm`**: Fast Plan B parallel execution (`<= 3` `Workspace: "share"` workers on disjoint slices).

