---
name: pro-dev
description: >-
  Master senior engineering lifecycle orchestrator combining /repo-onboard,
  /forensic-audit, /harden-fix, /lossless-modularize, /figma-to-prod,
  /truthful-readme, and /agile-swarm. Use whenever the user asks for an
  end-to-end build, audit-and-fix pass, architecture overhaul, or full project
  lifecycle workflow with strict quality gates and parallel execution.
---

# Pro-Dev Master Engineering Suite

Use this flagship skill as the unified entry point for structured, evidence-driven software engineering. Rather than loading massive redundant rules into every prompt, route each phase through the specialized `/slash` skill built for that job.

## Command Router (Specialized Lifecycle Suite)

| Slash Command | Mission | Deterministic Verifier / Helper |
| :--- | :--- | :--- |
| **`/repo-onboard`** | Discover unknown repo + maintain living `PROJECT_INTELLIGENCE.md` | Parallel read-only scan + 9-point preflight |
| **`/forensic-audit`** | Isolated worktree audit across 14 domains (`FACT` vs `INFERENCE`) | `forensic-audit/scripts/generate_audit_report.py` |
| **`/harden-fix`** | Triage Cat A/B/C, root-cause repair, second-pass independent audit | Git checkpoint + `/agile-swarm` slices |
| **`/lossless-modularize`** | Zero-loss SOLID split of god files while preserving behavior/APIs | `lossless-modularize/scripts/conservation_audit.py` |
| **`/figma-to-prod`** | Figma MCP to Flutter / React+TS UI, raw SVG package, state safety | `figma-to-prod/scripts/verify_figma_ui.py` |
| **`/truthful-readme`** | Evidence-verified README, Mermaid diagrams, AI navigation map | `truthful-readme/scripts/verify_readme.py` |
| **`/agile-swarm`** | Plan B `<= 3` parallel `Workspace: "share"` workers on disjoint files | `agile-swarm/scripts/worktree_team.py` |
| **`/gravity-session-doctor`** | Telemetry inspection, transcript forensic audit, harness updates | `gravity-session-doctor/scripts/inspect_logs.py` |

## Unified Engineering Axioms (Non-Negotiable)

1. **Inspect Before Assuming:** Read manifests, entrypoints, configs, tests, and active `AGENTS.md`/`README.md` before proposing changes or asking questions.
2. **Evidence Before Claims (`FACT` vs `INFERENCE`):** Never mark a build, test, lint, security check, or UI render verified unless you actually ran/inspected it after the final edit.
3. **Human Decision Gate (Option A/B Format):** Never ask open-ended "What should I do?" questions for routine engineering calls. Only escalate genuine product decisions, destructive history operations, or conflicting requirements using: `Problem -> Option A -> Option B -> Recommendation -> Impact`.
4. **Proportional Verification First:** Run fast targeted unit/static checks during implementation (`flutter test <file>`, `pytest <file>`, `vitest run <file>`), then run the full suite / analyzer before final completion.
5. **Strict File-Size & Zero-Regression Discipline:** Default source file limit `<= 400` lines (`<= 200` for icons, design tokens, and atomic UI widgets; `<= 500` ceiling during legacy refactor transitions).
6. **Tests Pass != Done:** Also verify edge cases, static analysis (`flutter analyze`, `tsc --noEmit`, `ruff`), security boundaries, and architecture fit.

## End-to-End Orchestration Workflow

When the user invokes `/pro-dev` for a complex task or new project milestone:

1. **Orient (`Step 0`):** Check `git status`, active `AGENTS.md` / `README.md`, and `.agents/memory/PROJECT_INTELLIGENCE.md` (if missing and repo has `> 10` source files, invoke **`/repo-onboard`** first).
2. **Route & Decompose:**
   - Need deep read-only health check / HTML deliverable? Run **`/forensic-audit`**.
   - Fixing findings, bugs, or security debt? Run **`/harden-fix`**.
   - Touching any file `> 400` lines or tangled monolith? Run **`/lossless-modularize`** first.
   - Converting Figma designs into Flutter or React+TS UI? Run **`/figma-to-prod`**.
   - Shipping or updating repo documentation? Run **`/truthful-readme`**.
3. **Parallelize Safely:** Whenever an implementation or Category-A repair plan splits into **2–3 disjoint module slices** with non-overlapping file ownership, launch Plan B **`/agile-swarm`** workers (`Workspace: "share"`), integrate on main branch cleanly, and re-test.
4. **Final Quality Gate & Bilingual Reporting:** Run all relevant test + script checks after final edits, update living memory if architecture shifted, and present a concise summary (matching the user's conversation language cleanly unless project conventions specify English).

