---
name: lossless-modularize
description: >-
  Autonomous lossless code modularization and SOLID refactoring workflow for
  breaking down oversized monolithic files without dropping logic, breaking
  public APIs, or creating import cycles. Uses scripts/conservation_audit.py
  for deterministic line, symbol, cycle, and file-size verification.
---

# Lossless Code Modularization & SOLID Refactoring

Use this skill whenever a source file exceeds clean maintainability bounds (`> 400` lines, or a legacy 1,000–10,000 line monolith) and must be decomposed cleanly **without rewriting from scratch or losing a single edge case**.

## Unified File-Size Contract

- **Standard modules / services / screens:** `<= 400` lines (absolute ceiling `<= 500` during transitional refactors via `--max-lines 500`).
- **UI atoms / icon registries / design tokens:** `<= 200` lines (`--ui-max-lines 200`).
- **Golden Rule:** Never split arbitrarily into meaningless 20-line fragments just to game line counts; every module must own one cohesive responsibility, clear state boundaries, and explicit dependencies.

## Strict Safety Invariants

1. **You Are Restructuring, NOT Rewriting:** Preserve existing behavior, subtle/unusual validation guards, error semantics, initialization order, and edge branches. Keep suspicious legacy branches unless proven dead and regression-tested.
2. **Preserve Public APIs via Barrels/Re-Exports:**
   - **Dart/Flutter:** keep existing public entrypoint exporting extracted modules (`export 'src/...';`).
   - **TypeScript/JS:** re-export public symbols cleanly from original entrypoint or `index.ts`.
   - **Python:** maintain backward-compatible imports and `__all__` in original module or `__init__.py`.
3. **One Cohesive Extraction Per Step (No Big-Bang Rewrite):** Extract -> Rewire -> Run tests/analyzer -> Commit/verify BEFORE extracting the next module.
4. **SOLID Without Over-Engineering:** Apply Single Responsibility, clean boundaries, and Dependency Inversion naturally; NEVER invent factory-of-factories or abstract interfaces with a single implementation unless testing/extensibility demands it.

## Execution Sequence

1. **Capture Deterministic Baseline (Mandatory Before Editing):**

   ```sh
   python -X utf8 scripts/conservation_audit.py baseline --out <scratch>/baseline.json <target_file_or_dir>
   ```

   Also run existing unit tests, build, and typecheck/static analyzer to establish a green starting gate.

2. **Analyze Before Splitting:**
   - Map all responsibilities, shared mutable state, side effects (`IO`, DB, timers, network), initialization order constraints, and internal call graph.
   - Design an acyclic DAG target layout (`entrypoint -> orchestrator -> cohesive domain modules -> shared types/utils`).

3. **Incremental Extraction Loop:**
   - Move leaf pure helpers and data models first, then stateful engines/controllers, leaving a clean thin coordinator/barrel at the original entrypoint.
   - Fix imports immediately and verify **tests + analyzer** after each slice.

4. **Deterministic Conservation & Size Gate (Mandatory After Final Edit):**

   ```sh
   python -X utf8 scripts/conservation_audit.py verify --baseline <scratch>/baseline.json --max-lines 400 --ui-max-lines 200 <target_dir_or_files>
   ```

   Do NOT declare completion until `"status": "PASS"` (`missing_symbols == []`, `oversized_files == []`, `import_cycles == []`, `retention_ratio >= 0.90`) and all project tests/analyzers pass.

## Final Traceability Report

Provide concisely: Original vs Final file metrics, Symbol Migration Table (`Original -> New Module`), SOLID/OOP boundaries established, Conservation Script Output (`PASS`), and test/analyzer proof.

