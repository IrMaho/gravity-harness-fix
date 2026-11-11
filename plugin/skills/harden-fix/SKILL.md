---
name: harden-fix
description: >-
  Zero-regression project hardening and root-cause repair workflow. Triages audit
  or discovered weaknesses into Category A (fix now), Category B (investigate
  first), and Category C (human decision), fixes root causes atomically with
  Git safety checkpoints, runs an independent second-pass audit, and quantifies
  before/after metrics.
---

# Zero-Regression Hardening & Root-Cause Repair

Use this skill after `/repo-onboard` or `/forensic-audit` (or whenever fixing a multi-issue backlog) to repair weaknesses methodically without introducing regressions.

## Triage Categories (Before Touching Code)

Classify every item in a structured **Repair Registry** (see [references/repair-registry-template.md](./references/repair-registry-template.md)):

- **Category A (`Fix Now`):** Confirmed bugs, missing input/boundary checks, silent error swallowing, leaked secrets/paths, broken invariants, dead/fragile branches with deterministic root causes.
- **Category B (`Investigate First`):** Flaky tests, intermittent hangs, unclear ownership, suspected security/race bugs — reproduce or inspect full flow before editing.
- **Category C (`HUMAN_DECISION`):** Breaking public API/schema changes, product UX/pricing policy, irreversible data cleanup, or conflicting requirements. Document with `Option A vs Option B + Recommendation`, mark `HUMAN_DECISION`, and keep fixing independent Category A/B work!

Order repairs cleanly: **`P0` (Security/Crash/Data Loss) -> `P1` (Broken Flow/Contract) -> `P2` (Quality/Perf/Errors) -> `P3` (Safe Cleanup)**.

## Execution Protocol

1. **Baseline & Git Safety Checkpoint:**
   - Ensure a clean rollback boundary (`git branch` / commit checkpoint) and run the current test/build/analyzer suite BEFORE fixing anything. Record baseline counts.
2. **Test-First & Root-Cause Discipline:**
   - Write or tighten a reproducing failing test whenever practical BEFORE applying the fix.
   - Fix root causes at the responsible layer — NEVER suppress linter warnings, loosen assertions, skip tests, or patch symptoms downstream.
   - Keep **One Responsibility Per Fix** (avoid mixing opportunistic refactors with security/bug patches).
3. **Parallel Execution for Independent Category A Fixes:**
   - When `>= 2` verified Category A items touch completely disjoint modules/files, execute them in parallel via **`/agile-swarm`** (`Workspace: "share"`, `<= 3` workers) and integrate cleanly.
4. **Targeted Verify -> Failure/Regression Stop Rule:**
   - Run targeted tests + static analyzer after each fix or cohesive batch. If a regression appears, **STOP stacking changes**, diagnose, fix, and re-verify immediately.
5. **Mandatory Second-Pass Independent Audit:**
   - `"Tests pass" != Done.` After repairing known `P0/P1` (and safe `P2/P3`) items, run a dedicated second-pass check across: Correctness edge cases, Error paths, Security boundaries, Static analysis, Full test suite, and Actual runtime execution.
   - If the second pass discovers new issues, loop back cleanly until stabilized.

## Final Quantified Report

Provide a concise report covering:
- **Repaired Items:** Bug -> Root Cause -> Fix -> Modified File -> Test Proof (`PASS`)
- **Before vs After Metrics Table:** Real measured numbers (tests passed/failed, analyzer errors, build status, coverage/file counts)
- **Remaining / Blocked Items (`Category C`):** Exact blocker, risk, and Option A/B choice needed

