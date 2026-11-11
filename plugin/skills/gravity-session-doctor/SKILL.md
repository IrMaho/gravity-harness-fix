---
name: gravity-session-doctor
description: >-
  Always-available diagnostic and harness maintenance workflow for reviewing live
  session-issue telemetry logs, auditing past Antigravity transcripts for speed
  and error bottlenecks, and updating gravity-harness-fix guardrails.
  Use whenever the user asks to inspect harness logs, check why a session slowed
  down or failed, audit conversations, or add a new harness fix.
---

# Gravity Session Doctor

The `gravity-harness-fix` lifecycle hooks continuously record runtime friction,
blocked anti-patterns, tool failures, read thrashing, and premature stops into
the configured telemetry log directory (`harness_config.json` -> `logsDir`, with
fallback to `~/.gemini/gravity-harness-logs/`).

## When to Run This Skill

1. **Log review:** The user asks to inspect recent session problems or see what
   the harness prevented/caught.
2. **Retrospective audit:** The user wants to audit past Antigravity
   conversations for speed bottlenecks or recurring command/edit errors.
3. **Rule/hook refinement:** A new failure pattern keeps showing up in live logs
   and needs a deterministic guard added to `gravity_harnes_fix`.

## Steps

1. **Inspect live telemetry logs** via [inspect_logs.py](./scripts/inspect_logs.py):

   ```sh
   python -X utf8 scripts/inspect_logs.py --tail 40
   ```

   If `harness_config.json` sits in the plugin root (`../../..` relative to this
   skill), `inspect_logs.py` resolves `logsDir` automatically.

2. **Run full transcript forensic audit** when checking historical conversations:

   Locate `sourceRepoDir` from `harness_config.json` and run:

   ```sh
   python -X utf8 "<sourceRepoDir>/scripts/audit_transcripts.py"
   ```

3. **Propose or implement a harness fix in the source repo (`sourceRepoDir`)**:
   - Add a `PreToolUse` deterministic check in `plugin/hooks/guard_and_log.py` if
     the error can be blocked or redirected before running.
   - Add an execution rule in `plugin/rules/AGENTS.md` if it is a workflow
     discipline rule.
   - Add a regression test in `tests/test_harness_guards.py`, run tests, and
     re-run `install.bat` (or `python scripts/install_harness.py`) so all
     `.gemini` homes receive the updated plugin.

