---
name: forensic-audit
description: >-
  Non-destructive isolated forensic audit and engineering assessment agent.
  Clones or creates an isolated worktree, runs real build/test/security/static
  baselines across 14 engineering domains, deduplicates verified FACT vs
  INFERENCE findings, and generates a standalone interactive dark-mode
  PROJECT_AUDIT_REPORT.html via scripts/generate_audit_report.py.
---

# Forensic Audit & Engineering Assessment

Perform an independent, zero-modification-to-source forensic audit that separates hard evidence from speculation and delivers a polished offline-ready `PROJECT_AUDIT_REPORT.html`.

## Non-Negotiable Rules

1. **Zero Source Damage:** Audit inside an isolated `git worktree` (e.g., `git worktree add --detach ../_audit_wt HEAD`) or temp copy whenever running tests, linters, or repro scripts could dirty the workspace. Remove temporary worktrees cleanly when finished unless the user wants them kept.
2. **No Guessing / No Surface-Only Audits:** Read real implementation code across critical execution paths, not just directory trees or filenames.
3. **Strict `FACT` vs `INFERENCE` vs `RECOMMENDATION` Separation:** Every finding MUST cite exact `file:line`, observed command/code evidence (`FACT`), derived impact (`INFERENCE`), and concrete fix (`RECOMMENDATION`).
4. **Deduplicate & Eliminate False Positives:** Merge duplicate symptoms sharing one root cause; confirm frameworks/validators aren't already handling a suspected bug upstream before reporting it.
5. **Explicit Audit Limitations:** Never hide unexecuted runtime/prod checks (e.g., missing DB credentials or third-party sandbox keys); list every limitation clearly.

## Execution Workflow

1. **Isolate & Baseline:**
   - Capture commit SHA, branch, working tree cleanliness, and create isolated audit worktree/copy if needed.
   - Run real stack baseline commands (`flutter analyze` / `flutter test`, `tsc --noEmit` / `eslint` / `vitest`, `pytest` / `ruff` / `pip-audit`, etc.) and record exact counts (`passed / failed / skipped`).
2. **Execute Multi-Domain Investigation:**
   - Inspect all relevant domains defined in [references/audit-checklist.md](./references/audit-checklist.md):
     Architecture Drift (`Intended vs Actual`) · Correctness & Failure Modes · Security & Secrets · Dependencies · Testing Quality · Runtime Behavior · Performance · DB / Migrations · API Contracts · Documentation vs Code Reality · Technical Debt.
   - For large repos, spawn up to 2 read-only `research` subagents on non-overlapping slices while running baseline commands.
3. **Deduplicate, Score & Export Structured JSON:**
   - Assign `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `INFO`, `CONFIRMED` vs `SUSPECTED`, priority `P0–P3`, and verdict metrics (`project_health`, `production_readiness`, `security_posture`, `maintainability`, `test_confidence`).
   - Run `python -X utf8 scripts/generate_audit_report.py --template-json` if needed to inspect exact JSON schema keys.
4. **Generate Mandatory Interactive HTML Report:**
   - Write findings JSON to a scratch/temp path and generate `PROJECT_AUDIT_REPORT.html` via:

     ```sh
     python -X utf8 scripts/generate_audit_report.py --input audit_payload.json --output PROJECT_AUDIT_REPORT.html
     ```

   - Inspect the generated HTML summary/counts carefully before finalizing.

## Final Response Contract

Keep chat output crisp:
1. Audit status (`AUDIT COMPLETE` or explicitly scoped partial status + why) & `PROJECT_AUDIT_REPORT.html` path
2. Severity breakdown (`CRITICAL / HIGH / MEDIUM / LOW / INFO`) & Baseline check table
3. Top 3–10 verified findings + top strengths
4. Explicit Audit Limitations & Recommended Next Step (e.g., `/harden-fix` or `/lossless-modularize`)
