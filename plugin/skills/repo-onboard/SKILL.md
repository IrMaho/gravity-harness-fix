---
name: repo-onboard
description: >-
  Structured repository onboarding and continuous project intelligence protocol.
  Use when starting work on an unfamiliar codebase, reconstructing architecture,
  establishing a validation baseline, or creating and maintaining a living
  PROJECT_INTELLIGENCE.md memory document.
---

# Repo Onboard & Continuous Project Intelligence

Turn any unfamiliar repository into a verified working technical model quickly without superficial skimming, unnecessary user questions, or stale assumptions.

## Operating Modes (Auto-Scaled)

- **Express Mode (`<= 40` source files):** Direct targeted inspection + manifest/test/baseline run in one clean pass.
- **Deep Mode (`> 40` source files or monorepo):** Spawn **1–2 read-only `research` subagents** in parallel across disjoint slices (e.g., Core/Backend vs UI/Infra+Tests) and synthesize results into [the Intelligence Template](./references/intelligence-template.md).

## Phase Pipeline

1. **Read-Only Discovery & Baseline (Phases 0–2):**
   - Inspect repo tree, git state, README/AGENTS docs, package manifests (`pubspec.yaml`, `package.json`, `pyproject.toml`, etc.), lockfiles, CI configs, and entrypoints.
   - Run available read-only baseline checks (unit tests, linter, type check) without mutating source files during initial discovery. Record exact pass/fail counts or explicit blocker reasons.
2. **Architecture & Critical Flow Reconstruction (Phases 3–4):**
   - Trace the actual dependency graph, state ownership, persistence/API boundaries, external integrations, and top 1–3 critical runtime flows from entrypoints down to data/IO.
   - Separate **Confirmed Facts** (inspected files/outputs) from **Inferences** (structural hypotheses needing verification).
3. **Risk, Security, Performance & Debt Scan (Phases 5–9):**
   - Check auth/validation boundaries, hardcoded secrets/unsafe deserialization, N+1/blocking IO hotspots, brittle error swallowing, test gaps, and oversized monolith files (`> 400` lines).
   - Run meaningful system/smoke execution where safe; never invent bugs or fake runtime passes.
4. **Write Living Intelligence Memory:**
   - Persist `.agents/memory/PROJECT_INTELLIGENCE.md` using [references/intelligence-template.md](./references/intelligence-template.md) (or write to the conversation Artifact directory if the repository must remain clean/read-only).
   - Rank remediation items strictly as `P0` (Critical/Blocker), `P1` (High), `P2` (Medium), `P3` (Low Debt).

## Continuous Memory & Future-Task Preflight

- **Before Every Follow-Up Task**, resolve internally in 10 seconds before coding:
  1. Target intent & exact scope
  2. Involved modules & owners
  3. Downstream consumers & dependencies
  4. Behavior/contracts that MUST remain preserved
  5. Existing tests & required new verification
- **Keep Memory Honest:** Whenever later code edits prove an earlier assumption wrong, update `.agents/memory/PROJECT_INTELLIGENCE.md` immediately and mark what changed.
- **Option A/B Decision Gate:** Never ask open-ended questions when code inspection answers them. Only escalate genuine product or irreversible decisions using concrete `Option A` vs `Option B` + your recommendation + impact.

## Output Summary Format

Respond concisely in the user's conversation language (or repo convention) with:
- Executive Summary & Stack
- Reconstructed Architecture
- Key Strengths vs Verified Weaknesses (`P0`–`P3`)
- Exact Test / Baseline Evidence
- Decisions Needed (only if genuine) & Recommended Next Step

